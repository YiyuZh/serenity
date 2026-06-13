from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    username: str


class HealthResponse(BaseModel):
    status: str
    database: str


class DashboardSummary(BaseModel):
    accounts: int
    posts: int
    failed_posts: int
    pending_posts: int
    latest_sync_status: str | None
    latest_sync_started_at: datetime | None
    sla_violations_24h: int


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    handle: str
    user_id: str | None
    since_id: str | None
    active: bool
    poll_interval_seconds: int
    last_checked_at: datetime | None


class SyncRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    triggered_by: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    fetched_count: int
    new_count: int
    error_message: str | None


class PostListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    post_id: str
    post_type: str
    original_text: str | None
    translated_text: str | None
    fetch_status: str
    media_status: str
    translation_status: str
    push_status: str
    published_at: datetime | None
    pushed_at: datetime | None
    error_message: str | None


class MediaAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    media_key: str | None
    media_type: str | None
    original_url: str | None
    storage_url: str | None
    status: str
    error_message: str | None


class TranslationJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model_name: str
    status: str
    retry_count: int
    total_tokens: int | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class PushLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    target_id: int
    status: str
    retry_count: int
    error_message: str | None
    created_at: datetime
    pushed_at: datetime | None


class TaskAttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_type: str
    status: str
    attempt_no: int
    duration_ms: int | None
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None
    metadata_json: dict[str, Any] | None = None


class PostEventOut(BaseModel):
    event_type: str
    status: str
    message: str | None = None
    created_at: datetime


class PostDetail(PostListItem):
    post_url: str
    referenced_post_id: str | None
    conversation_id: str | None
    lang: str | None
    raw_json: dict[str, Any] | None
    media_assets: list[MediaAssetOut]
    translation_jobs: list[TranslationJobOut]
    push_logs: list[PushLogOut]
    task_attempts: list[TaskAttemptOut]


class ActionResponse(BaseModel):
    status: str
    message: str
