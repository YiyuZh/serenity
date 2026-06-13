from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.infrastructure.models import SourceAccount


def ensure_default_account(session: Session) -> SourceAccount:
    settings = get_settings()
    account = session.scalar(
        select(SourceAccount).where(SourceAccount.source == "x", SourceAccount.handle == settings.x_account_handle)
    )
    if account:
        return account
    account = SourceAccount(
        source="x",
        handle=settings.x_account_handle,
        active=True,
        poll_interval_seconds=settings.poll_interval_seconds,
    )
    session.add(account)
    session.flush()
    return account


def list_accounts(session: Session) -> list[SourceAccount]:
    ensure_default_account(session)
    return list(session.scalars(select(SourceAccount).order_by(SourceAccount.id.asc())))
