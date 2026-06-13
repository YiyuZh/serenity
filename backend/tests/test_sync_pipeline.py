from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.sync_pipeline import SyncPipeline
from app.infrastructure.db import Base
from app.infrastructure.models import MediaAsset, Post, SourceAccount, SyncRun


class FakeXClient:
    def resolve_user(self, handle: str) -> str:
        return "123"

    def fetch_posts(self, user_id: str, since_id: str | None, max_results: int = 10):
        return {
            "data": [
                {
                    "id": "1800000000000000001",
                    "text": "New post",
                    "created_at": "2026-06-11T10:00:00.000Z",
                    "lang": "en",
                    "attachments": {"media_keys": ["3_abc"]},
                }
            ],
            "includes": {
                "media": [
                    {
                        "media_key": "3_abc",
                        "type": "photo",
                        "url": "https://pbs.twimg.com/media/abc.jpg",
                    }
                ]
            },
        }


def test_sync_pipeline_fetches_and_stores_posts(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'pipeline.db'}", future=True)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    Base.metadata.create_all(engine)

    with Session() as session:
        account = SourceAccount(source="x", handle="aleabitoreddit", active=True)
        session.add(account)
        session.flush()
        run = SyncRun(account_id=account.id, triggered_by="manual", status="pending")
        session.add(run)
        session.commit()
        run_id = run.id

    with Session() as session:
        SyncPipeline(FakeXClient()).process_run(session, run_id)
        session.commit()

    with Session() as session:
        assert session.query(Post).count() == 1
        assert session.query(MediaAsset).count() == 1
        run = session.get(SyncRun, run_id)
        assert run.status == "succeeded"
        assert run.fetched_count == 1
        assert run.new_count == 1
