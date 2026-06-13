from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import AdminUser, DbSession
from app.api.schemas import AccountOut, SyncRunOut
from app.application.account_service import list_accounts
from app.application.sync_service import create_manual_sync_run
from app.config import get_settings
from app.infrastructure.models import SourceAccount
from app.worker.tasks import process_sync_run

router = APIRouter(prefix="/accounts", tags=["accounts"])
logger = logging.getLogger(__name__)


@router.get("", response_model=list[AccountOut])
def accounts(session: DbSession, _: AdminUser) -> list[SourceAccount]:
    return list_accounts(session)


@router.post("/{account_id}/sync", response_model=SyncRunOut)
def trigger_sync(account_id: int, session: DbSession, _: AdminUser):
    account = session.scalar(select(SourceAccount).where(SourceAccount.id == account_id))
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    run = create_manual_sync_run(session, account)
    session.commit()
    session.refresh(run)
    if get_settings().enable_task_enqueue:
        try:
            process_sync_run.delay(run.id)
        except Exception as exc:
            logger.warning("Failed to enqueue sync run %s: %s", run.id, exc)
    return run
