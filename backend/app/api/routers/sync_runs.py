from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import AdminUser, DbSession
from app.api.schemas import TaskAttemptOut, SyncRunOut
from app.infrastructure.models import Post, SyncRun, TaskAttempt

router = APIRouter(tags=["runs"])


@router.get("/sync-runs", response_model=list[SyncRunOut])
def sync_runs(session: DbSession, _: AdminUser, limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)):
    return list(session.scalars(select(SyncRun).order_by(SyncRun.started_at.desc()).limit(limit).offset(offset)))


@router.get("/sync-runs/{run_id}", response_model=SyncRunOut)
def sync_run_detail(run_id: int, session: DbSession, _: AdminUser):
    run = session.get(SyncRun, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync run not found")
    return run


@router.get("/posts/{post_id}/events", response_model=list[TaskAttemptOut])
def post_events(post_id: int, session: DbSession, _: AdminUser):
    post = session.scalar(select(Post).where(Post.id == post_id).options(selectinload(Post.task_attempts)))
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return list(post.task_attempts)
