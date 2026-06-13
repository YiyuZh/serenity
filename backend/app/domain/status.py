from __future__ import annotations

from enum import StrEnum


class LifecycleStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"


class PostType(StrEnum):
    ORIGINAL = "original"
    QUOTE = "quote"
    REPLY = "reply"
    RETWEET = "retweet"


class TriggeredBy(StrEnum):
    SCHEDULER = "scheduler"
    MANUAL = "manual"


class TaskType(StrEnum):
    SYNC = "sync"
    MEDIA = "media"
    TRANSLATION = "translation"
    PUSH = "push"


STATUS_VALUES = tuple(status.value for status in LifecycleStatus)
POST_TYPE_VALUES = tuple(post_type.value for post_type in PostType)
TRIGGER_VALUES = tuple(trigger.value for trigger in TriggeredBy)
TASK_TYPE_VALUES = tuple(task_type.value for task_type in TaskType)


def can_retry(status: str) -> bool:
    return status in {LifecycleStatus.FAILED, LifecycleStatus.RETRYING}


def next_retry_status(status: str) -> str:
    if can_retry(status):
        return LifecycleStatus.RETRYING.value
    return status
