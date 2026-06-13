from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import or_, select

from app.application.account_service import ensure_default_account
from app.application.processing_service import process_media_assets, process_post_lifecycle, process_translation, push_post
from app.application.sync_pipeline import SyncPipeline
from app.domain.status import LifecycleStatus
from app.infrastructure.db import session_scope
from app.infrastructure.models import Post, SourceAccount, SyncRun
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.worker.tasks.poll_accounts")
def poll_accounts() -> list[int]:
    run_ids: list[int] = []
    with session_scope() as session:
        ensure_default_account(session)
        accounts = list(session.scalars(select(SourceAccount).where(SourceAccount.active.is_(True))))
        for account in accounts:
            run = SyncRun(
                account_id=account.id,
                triggered_by="scheduler",
                status=LifecycleStatus.PENDING.value,
                started_at=datetime.now(timezone.utc),
            )
            session.add(run)
            session.flush()
            run_ids.append(run.id)
    for run_id in run_ids:
        process_sync_run.delay(run_id)
    return run_ids


@celery_app.task(name="app.worker.tasks.process_sync_run")
def process_sync_run(run_id: int) -> int:
    new_post_ids: list[int]
    with session_scope() as session:
        pipeline = SyncPipeline()
        pipeline.process_run(session, run_id)
        new_post_ids = list(pipeline.last_new_post_ids)
    for post_id in new_post_ids:
        try:
            process_post.delay(post_id)
        except Exception as exc:
            logger.warning("Failed to enqueue post processing %s: %s", post_id, exc)
    return run_id


@celery_app.task(name="app.worker.tasks.process_post")
def process_post(post_id: int) -> int:
    with session_scope() as session:
        process_post_lifecycle(session, post_id)
    return post_id


@celery_app.task(name="app.worker.tasks.process_media")
def process_media(post_id: int) -> int:
    with session_scope() as session:
        process_media_assets(session, post_id)
    return post_id


@celery_app.task(name="app.worker.tasks.process_translation")
def translate_post(post_id: int) -> int:
    with session_scope() as session:
        process_translation(session, post_id)
    return post_id


@celery_app.task(name="app.worker.tasks.push_post")
def push_ready_post(post_id: int) -> int:
    with session_scope() as session:
        push_post(session, post_id)
    return post_id


@celery_app.task(name="app.worker.tasks.retry_failed_posts")
def retry_failed_posts(limit: int = 50) -> list[int]:
    failed_statuses = {LifecycleStatus.FAILED.value, LifecycleStatus.RETRYING.value}
    with session_scope() as session:
        post_ids = list(
            session.scalars(
                select(Post.id)
                .where(
                    or_(
                        Post.media_status.in_(failed_statuses),
                        Post.translation_status.in_(failed_statuses),
                        Post.push_status.in_(failed_statuses),
                    )
                )
                .order_by(Post.updated_at.asc())
                .limit(limit)
            )
        )
    for post_id in post_ids:
        try:
            process_post.delay(post_id)
        except Exception as exc:
            logger.warning("Failed to enqueue failed post retry %s: %s", post_id, exc)
    return post_ids
