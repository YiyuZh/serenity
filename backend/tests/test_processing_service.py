from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import selectinload, sessionmaker

from app.application.processing_service import process_post_lifecycle
from app.infrastructure.db import Base
from app.infrastructure.external_clients import ArchivedMedia
from app.infrastructure.models import MediaAsset, Post, PushLog, SourceAccount, TranslationJob


class FakeArchiver:
    def archive_image(self, post_id: str, media_key: str | None, source_url: str) -> ArchivedMedia:
        return ArchivedMedia(storage_path=f"x-media/{post_id}/{media_key}.jpg", storage_url=f"https://cos.example/{media_key}.jpg")


class FakeTranslator:
    def translate(self, text: str) -> tuple[str, dict]:
        return "Faithful Chinese translation", {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


class FailingArchiver:
    def archive_image(self, post_id: str, media_key: str | None, source_url: str) -> ArchivedMedia:
        raise RuntimeError("COS temporarily unavailable")


class FakePushClient:
    def __init__(self) -> None:
        self.payload: dict | None = None

    def send(self, payload: dict) -> dict:
        self.payload = payload
        return {"code": 0, "msg": "success"}


def test_process_post_lifecycle_archives_translates_and_pushes(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'processing.db'}", future=True)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    Base.metadata.create_all(engine)

    with Session() as session:
        account = SourceAccount(source="x", handle="aleabitoreddit", active=True)
        session.add(account)
        session.flush()
        post = Post(
            account_id=account.id,
            source="x",
            post_id="1800000000000000001",
            post_url="https://x.com/aleabitoreddit/status/1800000000000000001",
            post_type="original",
            original_text="New post with an image",
            fetch_status="succeeded",
            media_status="pending",
            translation_status="pending",
            push_status="pending",
            published_at=datetime.now(timezone.utc),
        )
        session.add(post)
        session.flush()
        session.add(
            MediaAsset(
                post_id=post.id,
                media_key="3_abc",
                media_type="photo",
                original_url="https://pbs.twimg.com/media/abc.jpg",
                status="pending",
            )
        )
        session.commit()
        post_id = post.id

    push_client = FakePushClient()
    with Session() as session:
        process_post_lifecycle(
            session,
            post_id,
            media_archiver=FakeArchiver(),
            translator=FakeTranslator(),
            push_client=push_client,
        )
        session.commit()

    with Session() as session:
        post = (
            session.query(Post)
            .options(selectinload(Post.media_assets), selectinload(Post.translation_jobs), selectinload(Post.push_logs))
            .filter(Post.id == post_id)
            .one()
        )
        assert post.media_status == "succeeded"
        assert post.translation_status == "succeeded"
        assert post.push_status == "succeeded"
        assert post.translated_text == "Faithful Chinese translation"
        assert post.ready_event_emitted_at is not None
        assert post.pushed_at is not None
        assert post.media_assets[0].storage_url == "https://cos.example/3_abc.jpg"
        assert session.query(TranslationJob).count() == 1
        assert session.query(PushLog).count() == 1
        assert push_client.payload is not None
        assert push_client.payload["msg_type"] == "post"


def test_process_post_lifecycle_pushes_with_original_media_when_archive_fails(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'processing-fallback.db'}", future=True)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    Base.metadata.create_all(engine)

    original_url = "https://pbs.twimg.com/media/fallback.jpg"
    with Session() as session:
        account = SourceAccount(source="x", handle="aleabitoreddit", active=True)
        session.add(account)
        session.flush()
        post = Post(
            account_id=account.id,
            source="x",
            post_id="1800000000000000002",
            post_url="https://x.com/aleabitoreddit/status/1800000000000000002",
            post_type="original",
            original_text="New post with a failing image archive",
            fetch_status="succeeded",
            media_status="pending",
            translation_status="pending",
            push_status="pending",
            published_at=datetime.now(timezone.utc),
        )
        session.add(post)
        session.flush()
        session.add(
            MediaAsset(
                post_id=post.id,
                media_key="3_fail",
                media_type="photo",
                original_url=original_url,
                status="pending",
            )
        )
        session.commit()
        post_id = post.id

    push_client = FakePushClient()
    with Session() as session:
        process_post_lifecycle(
            session,
            post_id,
            media_archiver=FailingArchiver(),
            translator=FakeTranslator(),
            push_client=push_client,
        )
        session.commit()

    with Session() as session:
        post = (
            session.query(Post)
            .options(selectinload(Post.media_assets), selectinload(Post.push_logs), selectinload(Post.translation_jobs))
            .filter(Post.id == post_id)
            .one()
        )
        assert post.media_status == "failed"
        assert post.translation_status == "succeeded"
        assert post.push_status == "succeeded"
        assert post.media_assets[0].error_message == "COS temporarily unavailable"
        assert session.query(TranslationJob).count() == 1
        assert session.query(PushLog).count() == 1
        assert push_client.payload is not None
        content_rows = push_client.payload["content"]["post"]["zh_cn"]["content"]
        flattened_text = "\n".join(cell.get("text", "") + cell.get("href", "") for row in content_rows for cell in row)
        assert "Original image (not archived)" in flattened_text
        assert original_url in flattened_text
