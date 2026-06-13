from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.normalizer import NormalizedPost, normalize_x_payload
from app.domain.status import LifecycleStatus
from app.infrastructure.external_clients import XApiClient
from app.infrastructure.models import MediaAsset, Post, SourceAccount, SyncRun, TaskAttempt


class SyncPipeline:
    def __init__(self, x_client: XApiClient | None = None) -> None:
        self.x_client = x_client or XApiClient()
        self.last_new_post_ids: list[int] = []

    def process_run(self, session: Session, run_id: int) -> SyncRun:
        self.last_new_post_ids = []
        run = session.get(SyncRun, run_id)
        if not run:
            raise LookupError(f"Sync run not found: {run_id}")
        account = session.get(SourceAccount, run.account_id)
        if not account:
            raise LookupError(f"Account not found: {run.account_id}")

        run.status = LifecycleStatus.RUNNING.value
        attempt = TaskAttempt(task_type="sync", status=LifecycleStatus.RUNNING.value, attempt_no=1)
        session.add(attempt)
        session.flush()

        try:
            if not account.user_id:
                account.user_id = self.x_client.resolve_user(account.handle)
            payload = self.x_client.fetch_posts(account.user_id, account.since_id)
            posts = normalize_x_payload(payload, account.handle)
            self.last_new_post_ids = self._store_posts(session, account, posts)
            if posts:
                account.since_id = _max_post_id([post.post_id for post in posts], account.since_id)
            account.last_checked_at = datetime.now(timezone.utc)
            run.status = LifecycleStatus.SUCCEEDED.value
            run.finished_at = datetime.now(timezone.utc)
            run.fetched_count = len(posts)
            run.new_count = len(self.last_new_post_ids)
            attempt.status = LifecycleStatus.SUCCEEDED.value
            attempt.finished_at = datetime.now(timezone.utc)
            return run
        except Exception as exc:
            run.status = LifecycleStatus.FAILED.value
            run.finished_at = datetime.now(timezone.utc)
            run.error_message = str(exc)
            attempt.status = LifecycleStatus.FAILED.value
            attempt.finished_at = datetime.now(timezone.utc)
            attempt.error_message = str(exc)
            raise

    def _store_posts(self, session: Session, account: SourceAccount, posts: list[NormalizedPost]) -> list[int]:
        new_post_ids: list[int] = []
        for item in posts:
            existing = session.scalar(select(Post).where(Post.source == account.source, Post.post_id == item.post_id))
            if existing:
                continue
            post = Post(
                account_id=account.id,
                source=account.source,
                post_id=item.post_id,
                post_url=item.post_url,
                post_type=item.post_type,
                referenced_post_id=item.referenced_post_id,
                conversation_id=item.conversation_id,
                original_text=item.original_text,
                lang=item.lang,
                published_at=item.published_at,
                fetch_status=LifecycleStatus.SUCCEEDED.value,
                media_status=LifecycleStatus.PENDING.value if item.media else LifecycleStatus.SKIPPED.value,
                translation_status=LifecycleStatus.PENDING.value if item.original_text.strip() else LifecycleStatus.SKIPPED.value,
                push_status=LifecycleStatus.PENDING.value,
                raw_json=item.raw_json,
            )
            session.add(post)
            session.flush()
            for media in item.media:
                session.add(
                    MediaAsset(
                        post_id=post.id,
                        media_key=media.media_key,
                        media_type=media.media_type,
                        original_url=media.original_url,
                        preview_url=media.preview_url,
                        alt_text=media.alt_text,
                        status=LifecycleStatus.PENDING.value,
                    )
                )
            new_post_ids.append(post.id)
        return new_post_ids


def _max_post_id(post_ids: list[str], current: str | None) -> str | None:
    candidates = [post_id for post_id in post_ids if post_id]
    if current:
        candidates.append(current)
    if not candidates:
        return current
    if all(post_id.isdigit() for post_id in candidates):
        return max(candidates, key=lambda value: int(value))
    return max(candidates)
