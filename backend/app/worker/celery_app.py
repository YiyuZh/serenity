from __future__ import annotations

from celery import Celery

from app.config import get_settings

settings = get_settings()
settings.validate_runtime_security()

celery_app = Celery(
    "serenity",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    timezone="UTC",
    worker_prefetch_multiplier=1,
    task_track_started=True,
    broker_connection_timeout=1,
    broker_connection_retry_on_startup=False,
    beat_schedule={
        "poll-x-accounts": {
            "task": "app.worker.tasks.poll_accounts",
            "schedule": settings.poll_interval_seconds,
        }
    },
)
