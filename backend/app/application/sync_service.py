from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domain.status import LifecycleStatus
from app.infrastructure.models import SourceAccount, SyncRun, TaskAttempt


def create_manual_sync_run(session: Session, account: SourceAccount) -> SyncRun:
    run = SyncRun(
        account_id=account.id,
        triggered_by="manual",
        status=LifecycleStatus.PENDING.value,
        started_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.flush()
    session.add(TaskAttempt(task_type="sync", status=LifecycleStatus.PENDING.value, attempt_no=1))
    return run
