from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.domain.status import LifecycleStatus
from app.infrastructure.models import Post, TaskAttempt


def list_posts(session: Session, status_filter: str | None = None, limit: int = 50, offset: int = 0) -> list[Post]:
    stmt = select(Post).order_by(Post.published_at.desc().nulls_last(), Post.id.desc()).limit(limit).offset(offset)
    if status_filter == "failed":
        stmt = stmt.where(
            or_(
                Post.fetch_status.in_([LifecycleStatus.FAILED.value, LifecycleStatus.RETRYING.value]),
                Post.media_status.in_([LifecycleStatus.FAILED.value, LifecycleStatus.RETRYING.value]),
                Post.translation_status.in_([LifecycleStatus.FAILED.value, LifecycleStatus.RETRYING.value]),
                Post.push_status.in_([LifecycleStatus.FAILED.value, LifecycleStatus.RETRYING.value]),
            )
        )
    elif status_filter:
        stmt = stmt.where(Post.push_status == status_filter)
    return list(session.scalars(stmt))


def get_post_detail(session: Session, post_id: int) -> Post:
    post = session.scalar(
        select(Post)
        .where(Post.id == post_id)
        .options(
            selectinload(Post.media_assets),
            selectinload(Post.translation_jobs),
            selectinload(Post.push_logs),
            selectinload(Post.task_attempts),
        )
    )
    if not post:
        raise LookupError(f"Post not found: {post_id}")
    return post


def retry_post(session: Session, post_id: int) -> Post:
    post = get_post_detail(session, post_id)
    failed_statuses = {LifecycleStatus.FAILED.value, LifecycleStatus.RETRYING.value}
    if post.media_status in failed_statuses:
        post.media_status = LifecycleStatus.RETRYING.value
        for asset in post.media_assets:
            if asset.status in failed_statuses:
                asset.status = LifecycleStatus.RETRYING.value
                asset.error_message = None
    if post.translation_status in failed_statuses:
        post.translation_status = LifecycleStatus.RETRYING.value
    if post.push_status in failed_statuses:
        post.push_status = LifecycleStatus.RETRYING.value
    post.error_message = None
    session.add(TaskAttempt(post_id=post.id, task_type="push", status="retrying", attempt_no=1))
    return post


def skip_post(session: Session, post_id: int) -> Post:
    post = get_post_detail(session, post_id)
    for attr in ("media_status", "translation_status", "push_status"):
        if getattr(post, attr) not in {LifecycleStatus.SUCCEEDED.value, LifecycleStatus.SKIPPED.value}:
            setattr(post, attr, LifecycleStatus.SKIPPED.value)
    session.add(TaskAttempt(post_id=post.id, task_type="push", status="skipped", attempt_no=1))
    return post
