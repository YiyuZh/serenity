from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domain.status import LifecycleStatus
from app.infrastructure.models import Post, SourceAccount, SyncRun


def get_dashboard_summary(session: Session) -> dict:
    failed = {LifecycleStatus.FAILED.value, LifecycleStatus.RETRYING.value}
    pending = {LifecycleStatus.PENDING.value, LifecycleStatus.RUNNING.value, LifecycleStatus.RETRYING.value}
    last_24h = datetime.now(timezone.utc) - timedelta(hours=24)

    latest_run = session.scalar(select(SyncRun).order_by(SyncRun.started_at.desc()).limit(1))
    return {
        "accounts": session.scalar(select(func.count(SourceAccount.id))) or 0,
        "posts": session.scalar(select(func.count(Post.id))) or 0,
        "failed_posts": session.scalar(
            select(func.count(Post.id)).where(
                or_(
                    Post.fetch_status.in_(failed),
                    Post.media_status.in_(failed),
                    Post.translation_status.in_(failed),
                    Post.push_status.in_(failed),
                )
            )
        )
        or 0,
        "pending_posts": session.scalar(
            select(func.count(Post.id)).where(
                or_(
                    Post.media_status.in_(pending),
                    Post.translation_status.in_(pending),
                    Post.push_status.in_(pending),
                )
            )
        )
        or 0,
        "latest_sync_status": latest_run.status if latest_run else None,
        "latest_sync_started_at": latest_run.started_at if latest_run else None,
        "sla_violations_24h": _count_sla_violations(session, last_24h),
    }


def _count_sla_violations(session: Session, since: datetime) -> int:
    posts = session.scalars(
        select(Post).where(Post.created_at >= since, Post.published_at.is_not(None), Post.pushed_at.is_not(None))
    )
    return sum(1 for post in posts if post.pushed_at and post.published_at and (post.pushed_at - post.published_at).total_seconds() > 300)
