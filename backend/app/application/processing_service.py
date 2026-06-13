from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.domain.status import LifecycleStatus, TaskType
from app.infrastructure.external_clients import CosStorageClient, DeepSeekClient, FeishuWebhookClient
from app.infrastructure.models import MediaAsset, Post, PushLog, PushTarget, TaskAttempt, TranslationJob


class MediaArchiver(Protocol):
    def archive_image(self, post_id: str, media_key: str | None, source_url: str): ...


class Translator(Protocol):
    def translate(self, text: str) -> tuple[str, dict[str, Any]]: ...


class PushClient(Protocol):
    def send(self, payload: dict[str, Any]) -> dict[str, Any]: ...


READY_STATUSES = {LifecycleStatus.SUCCEEDED.value, LifecycleStatus.SKIPPED.value}
PUSHABLE_MEDIA_STATUSES = READY_STATUSES | {LifecycleStatus.FAILED.value}
REPROCESS_STATUSES = {LifecycleStatus.PENDING.value, LifecycleStatus.FAILED.value, LifecycleStatus.RETRYING.value}


def process_post_lifecycle(
    session: Session,
    post_id: int,
    media_archiver: MediaArchiver | None = None,
    translator: Translator | None = None,
    push_client: PushClient | None = None,
    settings: Settings | None = None,
) -> Post:
    post = process_media_assets(session, post_id, media_archiver=media_archiver, settings=settings)
    post = process_translation(session, post_id, translator=translator, settings=settings)
    if post.media_status in READY_STATUSES and post.translation_status in READY_STATUSES:
        post.ready_event_emitted_at = post.ready_event_emitted_at or datetime.now(timezone.utc)
    return push_post(session, post_id, push_client=push_client, settings=settings)


def process_media_assets(
    session: Session,
    post_id: int,
    media_archiver: MediaArchiver | None = None,
    settings: Settings | None = None,
) -> Post:
    post = _get_post(session, post_id)
    if post.media_status in READY_STATUSES:
        return post
    if not post.media_assets:
        post.media_status = LifecycleStatus.SKIPPED.value
        post.error_message = None
        return post

    archiver = media_archiver or CosStorageClient(settings=settings)
    attempt = _start_attempt(session, post, TaskType.MEDIA.value)
    post.media_status = LifecycleStatus.RUNNING.value
    errors: list[str] = []

    for asset in post.media_assets:
        if asset.status == LifecycleStatus.SUCCEEDED.value:
            continue
        if not asset.original_url:
            asset.status = LifecycleStatus.SKIPPED.value
            asset.error_message = None
            continue

        asset.status = LifecycleStatus.RUNNING.value
        try:
            archived = archiver.archive_image(post.post_id, asset.media_key, asset.original_url)
            asset.storage_path = archived.storage_path
            asset.storage_url = archived.storage_url
            asset.status = LifecycleStatus.SUCCEEDED.value
            asset.error_message = None
        except Exception as exc:  # pragma: no cover - exact external errors vary by provider
            asset.retry_count += 1
            asset.status = LifecycleStatus.FAILED.value
            asset.error_message = str(exc)
            errors.append(f"{asset.media_key or asset.id}: {exc}")

    if errors:
        post.media_status = LifecycleStatus.FAILED.value
        post.error_message = "; ".join(errors)
        _finish_attempt(attempt, LifecycleStatus.FAILED.value, post.error_message)
        return post

    post.media_status = LifecycleStatus.SUCCEEDED.value
    post.error_message = None
    _finish_attempt(attempt, LifecycleStatus.SUCCEEDED.value)
    return post


def process_translation(
    session: Session,
    post_id: int,
    translator: Translator | None = None,
    settings: Settings | None = None,
) -> Post:
    post = _get_post(session, post_id)
    if post.translation_status == LifecycleStatus.SUCCEEDED.value and post.translated_text:
        return post
    if not (post.original_text or "").strip():
        post.translation_status = LifecycleStatus.SKIPPED.value
        post.error_message = None
        return post

    config = settings or get_settings()
    client = translator or DeepSeekClient(settings=config)
    attempt = _start_attempt(session, post, TaskType.TRANSLATION.value)
    job = TranslationJob(
        post_id=post.id,
        model_name=config.deepseek_model,
        input_text=post.original_text or "",
        status=LifecycleStatus.RUNNING.value,
    )
    session.add(job)
    session.flush()
    post.translation_status = LifecycleStatus.RUNNING.value

    try:
        translated_text, usage = client.translate(post.original_text or "")
        now = datetime.now(timezone.utc)
        job.output_text = translated_text
        job.status = LifecycleStatus.SUCCEEDED.value
        job.prompt_tokens = _int_or_none(usage.get("prompt_tokens"))
        job.completion_tokens = _int_or_none(usage.get("completion_tokens"))
        job.total_tokens = _int_or_none(usage.get("total_tokens"))
        job.completed_at = now
        post.translated_text = translated_text
        post.translated_at = now
        post.translation_status = LifecycleStatus.SUCCEEDED.value
        post.error_message = None
        _finish_attempt(attempt, LifecycleStatus.SUCCEEDED.value, metadata={"total_tokens": job.total_tokens})
    except Exception as exc:  # pragma: no cover - exact external errors vary by provider
        job.retry_count += 1
        job.status = LifecycleStatus.FAILED.value
        job.error_message = str(exc)
        job.completed_at = datetime.now(timezone.utc)
        post.translation_status = LifecycleStatus.FAILED.value
        post.error_message = str(exc)
        _finish_attempt(attempt, LifecycleStatus.FAILED.value, str(exc))
    return post


def push_post(
    session: Session,
    post_id: int,
    push_client: PushClient | None = None,
    settings: Settings | None = None,
) -> Post:
    post = _get_post(session, post_id)
    if post.push_status == LifecycleStatus.SUCCEEDED.value:
        return post

    dependency_error = _push_dependency_error(post)
    if dependency_error:
        post.push_status = LifecycleStatus.FAILED.value
        post.error_message = dependency_error
        return post

    target = ensure_default_push_target(session)
    payload = build_feishu_payload(post)
    log = PushLog(post_id=post.id, target_id=target.id, payload=payload, status=LifecycleStatus.RUNNING.value)
    session.add(log)
    session.flush()

    attempt = _start_attempt(session, post, TaskType.PUSH.value)
    client = push_client or FeishuWebhookClient(settings=settings or get_settings())
    post.push_status = LifecycleStatus.RUNNING.value

    try:
        response = client.send(payload)
        now = datetime.now(timezone.utc)
        log.status = LifecycleStatus.SUCCEEDED.value
        log.response_json = response
        log.pushed_at = now
        post.push_status = LifecycleStatus.SUCCEEDED.value
        post.pushed_at = now
        post.error_message = None
        _finish_attempt(attempt, LifecycleStatus.SUCCEEDED.value)
    except Exception as exc:  # pragma: no cover - exact external errors vary by provider
        log.retry_count += 1
        log.status = LifecycleStatus.FAILED.value
        log.error_message = str(exc)
        post.push_status = LifecycleStatus.FAILED.value
        post.error_message = str(exc)
        _finish_attempt(attempt, LifecycleStatus.FAILED.value, str(exc))
    return post


def ensure_default_push_target(session: Session) -> PushTarget:
    target = session.scalar(
        select(PushTarget).where(
            PushTarget.channel == "feishu",
            PushTarget.env_key == "FEISHU_WEBHOOK_URL",
            PushTarget.active.is_(True),
        )
    )
    if target:
        return target
    target = PushTarget(channel="feishu", name="Feishu Main Webhook", env_key="FEISHU_WEBHOOK_URL", active=True)
    session.add(target)
    session.flush()
    return target


def build_feishu_payload(post: Post) -> dict[str, Any]:
    handle = post.account.handle if post.account else "unknown"
    title = f"X new post @{handle}"
    original_text = (post.original_text or "").strip() or "(empty text)"
    translated_text = (post.translated_text or "").strip() or "(translation skipped)"
    content: list[list[dict[str, Any]]] = [
        [{"tag": "text", "text": f"Original\n{original_text}"}],
        [{"tag": "text", "text": f"Chinese translation\n{translated_text}"}],
        [{"tag": "text", "text": "Source: "}, {"tag": "a", "text": post.post_url, "href": post.post_url}],
    ]

    published_at = post.published_at.isoformat() if post.published_at else "unknown"
    content.append([{"tag": "text", "text": f"Published at: {published_at}"}])

    image_links: list[tuple[str, str]] = []
    for asset in post.media_assets:
        if asset.storage_url:
            image_links.append(("Image", asset.storage_url))
        elif asset.original_url:
            image_links.append(("Original image (not archived)", asset.original_url))

    if image_links:
        content.append([{"tag": "text", "text": "Images:"}])
        for index, (label, url) in enumerate(image_links, start=1):
            content.append([{"tag": "a", "text": f"{label} {index}", "href": url}])

    return {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": title,
                    "content": content,
                }
            }
        },
    }


def _get_post(session: Session, post_id: int) -> Post:
    post = session.scalar(
        select(Post)
        .where(Post.id == post_id)
        .options(selectinload(Post.account), selectinload(Post.media_assets), selectinload(Post.translation_jobs))
    )
    if not post:
        raise LookupError(f"Post not found: {post_id}")
    return post


def _push_dependency_error(post: Post) -> str | None:
    if post.fetch_status not in READY_STATUSES:
        return "Fetch has not succeeded"
    if post.media_status not in PUSHABLE_MEDIA_STATUSES:
        return "Media archive is not ready"
    if post.translation_status not in READY_STATUSES:
        return "Translation is not ready"
    return None


def _start_attempt(session: Session, post: Post, task_type: str) -> TaskAttempt:
    attempt_no = (
        session.scalar(select(func.max(TaskAttempt.attempt_no)).where(TaskAttempt.post_id == post.id, TaskAttempt.task_type == task_type))
        or 0
    ) + 1
    attempt = TaskAttempt(post_id=post.id, task_type=task_type, status=LifecycleStatus.RUNNING.value, attempt_no=attempt_no)
    session.add(attempt)
    session.flush()
    return attempt


def _finish_attempt(
    attempt: TaskAttempt,
    status: str,
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    attempt.status = status
    attempt.finished_at = now
    attempt.error_message = error_message
    attempt.metadata_json = metadata
    if attempt.started_at:
        started_at = attempt.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        attempt.duration_ms = max(0, int((now - started_at).total_seconds() * 1000))


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
