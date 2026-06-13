from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AdminUser, DbSession
from app.api.schemas import DashboardSummary
from app.application.dashboard_service import get_dashboard_summary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def summary(session: DbSession, _: AdminUser) -> dict:
    return get_dashboard_summary(session)
