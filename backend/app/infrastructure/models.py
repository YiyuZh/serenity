from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.domain.status import POST_TYPE_VALUES, STATUS_VALUES, TASK_TYPE_VALUES, TRIGGER_VALUES
from app.infrastructure.db import Base

IdType = BigInteger().with_variant(Integer, "sqlite")


def _in_check(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class SourceAccount(Base):
    __tablename__ = "source_accounts"
    __table_args__ = (
        UniqueConstraint("source", "handle", name="uq_source_accounts_source_handle"),
        CheckConstraint("poll_interval_seconds >= 60", name="ck_source_accounts_poll_interval"),
        Index("idx_source_accounts_active", "active", "last_checked_at"),
    )

    id = Column(IdType, primary_key=True)
    source = Column(String(32), nullable=False, default="x")
    handle = Column(String(128), nullable=False)
    user_id = Column(String(64))
    since_id = Column(String(64))
    active = Column(Boolean, nullable=False, default=True)
    poll_interval_seconds = Column(Integer, nullable=False, default=180)
    last_checked_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    posts = relationship("Post", back_populates="account")
    sync_runs = relationship("SyncRun", back_populates="account")


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        UniqueConstraint("source", "post_id", name="uq_posts_source_post_id"),
        CheckConstraint(_in_check("post_type", POST_TYPE_VALUES), name="ck_posts_post_type"),
        CheckConstraint(_in_check("fetch_status", STATUS_VALUES), name="ck_posts_fetch_status"),
        CheckConstraint(_in_check("media_status", STATUS_VALUES), name="ck_posts_media_status"),
        CheckConstraint(_in_check("translation_status", STATUS_VALUES), name="ck_posts_translation_status"),
        CheckConstraint(_in_check("push_status", STATUS_VALUES), name="ck_posts_push_status"),
        Index("idx_posts_account_published", "account_id", "published_at"),
        Index("idx_posts_push_status_created", "push_status", "created_at"),
        Index("idx_posts_translation_status_created", "translation_status", "created_at"),
        Index(
            "idx_posts_failed_partial",
            "created_at",
            postgresql_where=text(
                "fetch_status IN ('failed','retrying') OR media_status IN ('failed','retrying') "
                "OR translation_status IN ('failed','retrying') OR push_status IN ('failed','retrying')"
            ),
        ),
    )

    id = Column(IdType, primary_key=True)
    account_id = Column(IdType, ForeignKey("source_accounts.id", ondelete="CASCADE"), nullable=False)
    source = Column(String(32), nullable=False, default="x")
    post_id = Column(String(64), nullable=False)
    post_url = Column(Text, nullable=False)
    post_type = Column(String(32), nullable=False, default="original")
    referenced_post_id = Column(String(64))
    conversation_id = Column(String(64))
    original_text = Column(Text)
    translated_text = Column(Text)
    lang = Column(String(16))
    published_at = Column(DateTime(timezone=True))
    fetched_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    translated_at = Column(DateTime(timezone=True))
    pushed_at = Column(DateTime(timezone=True))
    ready_event_emitted_at = Column(DateTime(timezone=True))
    fetch_status = Column(String(32), nullable=False, default="succeeded")
    media_status = Column(String(32), nullable=False, default="pending")
    translation_status = Column(String(32), nullable=False, default="pending")
    push_status = Column(String(32), nullable=False, default="pending")
    raw_json = Column(JSON)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    account = relationship("SourceAccount", back_populates="posts")
    media_assets = relationship("MediaAsset", back_populates="post", cascade="all, delete-orphan")
    translation_jobs = relationship("TranslationJob", back_populates="post", cascade="all, delete-orphan")
    push_logs = relationship("PushLog", back_populates="post", cascade="all, delete-orphan")
    task_attempts = relationship("TaskAttempt", back_populates="post", cascade="all, delete-orphan")


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        UniqueConstraint("post_id", "media_key", name="uq_media_assets_post_key"),
        CheckConstraint(_in_check("status", STATUS_VALUES), name="ck_media_assets_status"),
        Index("idx_media_assets_post_id", "post_id"),
        Index("idx_media_assets_status_created", "status", "created_at"),
        Index("idx_media_assets_failed_partial", "created_at", postgresql_where=text("status IN ('failed','retrying')")),
    )

    id = Column(IdType, primary_key=True)
    post_id = Column(IdType, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    media_key = Column(String(128))
    media_type = Column(String(32))
    original_url = Column(Text)
    preview_url = Column(Text)
    storage_path = Column(Text)
    storage_url = Column(Text)
    alt_text = Column(Text)
    status = Column(String(32), nullable=False, default="pending")
    retry_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    post = relationship("Post", back_populates="media_assets")


class TranslationJob(Base):
    __tablename__ = "translation_jobs"
    __table_args__ = (
        CheckConstraint(_in_check("status", STATUS_VALUES), name="ck_translation_jobs_status"),
        Index("idx_translation_jobs_post_id", "post_id"),
        Index("idx_translation_jobs_status_created", "status", "created_at"),
        Index("idx_translation_jobs_failed_partial", "created_at", postgresql_where=text("status IN ('failed','retrying')")),
    )

    id = Column(IdType, primary_key=True)
    post_id = Column(IdType, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    model_name = Column(String(64), nullable=False)
    input_text = Column(Text, nullable=False)
    output_text = Column(Text)
    status = Column(String(32), nullable=False, default="pending")
    retry_count = Column(Integer, nullable=False, default=0)
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)
    total_tokens = Column(Integer)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True))

    post = relationship("Post", back_populates="translation_jobs")


class PushTarget(Base):
    __tablename__ = "push_targets"
    __table_args__ = (
        UniqueConstraint("channel", "env_key", name="uq_push_targets_channel_env_key"),
        Index("idx_push_targets_active", "active", "channel"),
    )

    id = Column(IdType, primary_key=True)
    channel = Column(String(32), nullable=False, default="feishu")
    name = Column(String(128), nullable=False)
    env_key = Column(String(128), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    push_logs = relationship("PushLog", back_populates="target")


class PushLog(Base):
    __tablename__ = "push_logs"
    __table_args__ = (
        CheckConstraint(_in_check("status", STATUS_VALUES), name="ck_push_logs_status"),
        Index("idx_push_logs_post_id", "post_id"),
        Index("idx_push_logs_target_id", "target_id"),
        Index("idx_push_logs_status_created", "status", "created_at"),
    )

    id = Column(IdType, primary_key=True)
    post_id = Column(IdType, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    target_id = Column(IdType, ForeignKey("push_targets.id", ondelete="RESTRICT"), nullable=False)
    payload = Column(JSON)
    status = Column(String(32), nullable=False, default="pending")
    retry_count = Column(Integer, nullable=False, default=0)
    response_json = Column(JSON)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    pushed_at = Column(DateTime(timezone=True))

    post = relationship("Post", back_populates="push_logs")
    target = relationship("PushTarget", back_populates="push_logs")


class SyncRun(Base):
    __tablename__ = "sync_runs"
    __table_args__ = (
        CheckConstraint(_in_check("triggered_by", TRIGGER_VALUES), name="ck_sync_runs_triggered_by"),
        CheckConstraint(_in_check("status", STATUS_VALUES), name="ck_sync_runs_status"),
        Index("idx_sync_runs_account_started", "account_id", "started_at"),
        Index("idx_sync_runs_status_started", "status", "started_at"),
    )

    id = Column(IdType, primary_key=True)
    account_id = Column(IdType, ForeignKey("source_accounts.id", ondelete="CASCADE"), nullable=False)
    triggered_by = Column(String(32), nullable=False, default="scheduler")
    status = Column(String(32), nullable=False, default="running")
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at = Column(DateTime(timezone=True))
    fetched_count = Column(Integer, nullable=False, default=0)
    new_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text)

    account = relationship("SourceAccount", back_populates="sync_runs")


class TaskAttempt(Base):
    __tablename__ = "task_attempts"
    __table_args__ = (
        CheckConstraint(_in_check("task_type", TASK_TYPE_VALUES), name="ck_task_attempts_task_type"),
        CheckConstraint(_in_check("status", STATUS_VALUES), name="ck_task_attempts_status"),
        Index("idx_task_attempts_post_id", "post_id"),
        Index("idx_task_attempts_type_status_started", "task_type", "status", "started_at"),
        Index("idx_task_attempts_failed_partial", "started_at", postgresql_where=text("status IN ('failed','retrying')")),
    )

    id = Column(IdType, primary_key=True)
    post_id = Column(IdType, ForeignKey("posts.id", ondelete="CASCADE"))
    task_type = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False)
    attempt_no = Column(Integer, nullable=False, default=1)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at = Column(DateTime(timezone=True))
    duration_ms = Column(Integer)
    error_message = Column(Text)
    metadata_json = Column("metadata", JSON)

    post = relationship("Post", back_populates="task_attempts")
