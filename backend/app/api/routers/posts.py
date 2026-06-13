from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AdminUser, DbSession
from app.api.schemas import ActionResponse, PostDetail, PostEventOut, PostListItem
from app.application.post_service import get_post_detail, list_posts, retry_post, skip_post
from app.config import get_settings
from app.worker.tasks import process_post

router = APIRouter(prefix="/posts", tags=["posts"])
logger = logging.getLogger(__name__)


@router.get("", response_model=list[PostListItem])
def posts(
    session: DbSession,
    _: AdminUser,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return list_posts(session, status_filter=status_filter, limit=limit, offset=offset)


@router.get("/{post_id}", response_model=PostDetail)
def post_detail(post_id: int, session: DbSession, _: AdminUser):
    try:
        return get_post_detail(session, post_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{post_id}/events", response_model=list[PostEventOut])
def post_events(post_id: int, session: DbSession, _: AdminUser) -> list[PostEventOut]:
    try:
        post = get_post_detail(session, post_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    events: list[PostEventOut] = [
        PostEventOut(event_type="fetch", status=post.fetch_status, message=post.error_message, created_at=post.fetched_at)
    ]
    for asset in post.media_assets:
        events.append(
            PostEventOut(
                event_type="media",
                status=asset.status,
                message=asset.error_message or asset.storage_url,
                created_at=asset.updated_at,
            )
        )
    for job in post.translation_jobs:
        events.append(
            PostEventOut(
                event_type="translation",
                status=job.status,
                message=job.error_message,
                created_at=job.completed_at or job.created_at,
            )
        )
    for log in post.push_logs:
        events.append(
            PostEventOut(
                event_type="push",
                status=log.status,
                message=log.error_message,
                created_at=log.pushed_at or log.created_at,
            )
        )
    for attempt in post.task_attempts:
        events.append(
            PostEventOut(
                event_type=f"task:{attempt.task_type}",
                status=attempt.status,
                message=attempt.error_message,
                created_at=attempt.finished_at or attempt.started_at,
            )
        )
    return sorted(events, key=lambda event: event.created_at)


@router.post("/{post_id}/retry", response_model=ActionResponse)
def retry(post_id: int, session: DbSession, _: AdminUser) -> ActionResponse:
    try:
        retry_post(session, post_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    session.commit()
    if get_settings().enable_task_enqueue:
        try:
            process_post.delay(post_id)
        except Exception as exc:
            logger.warning("Failed to enqueue post retry %s: %s", post_id, exc)
    return ActionResponse(status="retrying", message="Post retry requested")


@router.post("/{post_id}/skip", response_model=ActionResponse)
def skip(post_id: int, session: DbSession, _: AdminUser) -> ActionResponse:
    try:
        skip_post(session, post_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    session.commit()
    return ActionResponse(status="skipped", message="Post skipped")
