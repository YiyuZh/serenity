from __future__ import annotations

import base64
import hashlib
import hmac
import mimetypes
import time
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

import requests

from app.config import Settings, get_settings


class ExternalDependencyError(RuntimeError):
    """Raised when an external dependency call fails."""


@dataclass(frozen=True)
class ArchivedMedia:
    storage_path: str
    storage_url: str


class XApiClient:
    def __init__(self, settings: Settings | None = None, session: requests.Session | None = None) -> None:
        self.settings = settings or get_settings()
        self.session = session or requests.Session()

    def resolve_user(self, handle: str) -> str:
        if not self.settings.x_bearer_token:
            raise ExternalDependencyError("X_BEARER_TOKEN is not configured")
        response = self.session.get(
            f"{self.settings.x_api_base_url}/users/by/username/{handle.lstrip('@')}",
            headers={"Authorization": f"Bearer {self.settings.x_bearer_token}"},
            timeout=30,
        )
        if response.status_code >= 400:
            raise ExternalDependencyError(f"X user lookup failed: {response.status_code}")
        user_id = (response.json().get("data") or {}).get("id")
        if not user_id:
            raise ExternalDependencyError("X user lookup returned no id")
        return str(user_id)

    def fetch_posts(self, user_id: str, since_id: str | None, max_results: int | None = None, max_pages: int | None = None) -> dict[str, Any]:
        if not self.settings.x_bearer_token:
            raise ExternalDependencyError("X_BEARER_TOKEN is not configured")
        page_size = max(5, min(100, max_results if max_results is not None else self.settings.x_max_results))
        page_count = max(1, max_pages if max_pages is not None else self.settings.x_max_pages)
        base_params: dict[str, Any] = {
            "max_results": page_size,
            "tweet.fields": "id,text,created_at,lang,conversation_id,referenced_tweets,attachments,author_id,entities,public_metrics",
            "expansions": "attachments.media_keys,referenced_tweets.id",
            "media.fields": "media_key,type,url,preview_image_url,width,height,alt_text",
        }
        if since_id:
            base_params["since_id"] = since_id

        combined: dict[str, Any] = {"data": [], "includes": {"media": []}, "meta": {}}
        pagination_token: str | None = None
        for _ in range(page_count):
            params = dict(base_params)
            if pagination_token:
                params["pagination_token"] = pagination_token
            response = self.session.get(
                f"{self.settings.x_api_base_url}/users/{user_id}/tweets",
                headers={"Authorization": f"Bearer {self.settings.x_bearer_token}"},
                params=params,
                timeout=30,
            )
            if response.status_code == 429:
                reset_at = response.headers.get("x-rate-limit-reset")
                raise ExternalDependencyError(f"X timeline rate limited: reset_at={reset_at or 'unknown'}")
            if response.status_code >= 400:
                raise ExternalDependencyError(f"X timeline fetch failed: {response.status_code}")
            payload = response.json()
            _extend_unique(combined["data"], payload.get("data") or [], "id")
            includes = payload.get("includes") or {}
            combined_includes = combined.setdefault("includes", {})
            for include_name, key_name in {"media": "media_key", "tweets": "id", "users": "id"}.items():
                items = includes.get(include_name) or []
                if items:
                    _extend_unique(combined_includes.setdefault(include_name, []), items, key_name)
            combined["meta"] = payload.get("meta") or {}
            pagination_token = (payload.get("meta") or {}).get("next_token")
            if not pagination_token:
                break
        return combined


class DeepSeekClient:
    def __init__(self, settings: Settings | None = None, session: requests.Session | None = None) -> None:
        self.settings = settings or get_settings()
        self.session = session or requests.Session()

    def translate(self, text: str) -> tuple[str, dict[str, Any]]:
        if not self.settings.deepseek_api_key:
            raise ExternalDependencyError("DEEPSEEK_API_KEY is not configured")
        response = self.session.post(
            f"{self.settings.deepseek_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.deepseek_api_key}"},
            json={
                "model": self.settings.deepseek_model,
                "temperature": 0.2,
                "thinking": {"type": "disabled"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a professional English-to-Simplified-Chinese translator for X posts. "
                            "Translate only the user's main post faithfully and directly. Preserve numbers, "
                            "code, timestamps, percentages, URLs, product names, and all factual meaning. "
                            "Do not add explanations, summaries, opinions, or information not present in the source."
                        ),
                    },
                    {"role": "user", "content": text},
                ],
            },
            timeout=60,
        )
        if response.status_code >= 400:
            raise ExternalDependencyError(f"DeepSeek translation failed: {response.status_code}")
        payload = response.json()
        return payload["choices"][0]["message"]["content"].strip(), payload.get("usage") or {}


class FeishuWebhookClient:
    def __init__(self, settings: Settings | None = None, session: requests.Session | None = None) -> None:
        self.settings = settings or get_settings()
        self.session = session or requests.Session()

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.feishu_webhook_url:
            raise ExternalDependencyError("FEISHU_WEBHOOK_URL is not configured")
        signed_payload = self._with_signature(payload)
        response = self.session.post(self.settings.feishu_webhook_url, json=signed_payload, timeout=30)
        if response.status_code >= 400:
            raise ExternalDependencyError(f"Feishu webhook failed: {response.status_code}")
        result = response.json()
        if result.get("code", 0) not in {0, "0"}:
            raise ExternalDependencyError(f"Feishu webhook returned error: {result}")
        return result

    def _with_signature(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.feishu_webhook_secret:
            return payload
        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{self.settings.feishu_webhook_secret}"
        digest = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
        return {**payload, "timestamp": timestamp, "sign": base64.b64encode(digest).decode("utf-8")}


class CosStorageClient:
    """COS boundary. The concrete S3 SDK wiring belongs here, not in API/application code."""

    def __init__(self, settings: Settings | None = None, session: requests.Session | None = None) -> None:
        self.settings = settings or get_settings()
        self.session = session or requests.Session()

    def archive_image(self, post_id: str, media_key: str | None, source_url: str) -> ArchivedMedia:
        self._validate_config()
        response = self.session.get(source_url, timeout=30)
        if response.status_code >= 400:
            raise ExternalDependencyError(f"Image download failed: {response.status_code}")

        content_type = response.headers.get("content-type", "application/octet-stream").split(";")[0].strip()
        object_key = self.object_key_for(post_id=post_id, media_key=media_key, source_url=source_url, content_type=content_type)
        self._s3_client().put_object(
            Bucket=self.settings.cos_bucket,
            Key=object_key,
            Body=response.content,
            ContentType=content_type,
        )
        return ArchivedMedia(storage_path=object_key, storage_url=self.public_url_for_key(object_key))

    def object_key_for(self, post_id: str, media_key: str | None, source_url: str, content_type: str | None = None) -> str:
        safe_post_id = _safe_key_part(post_id)
        safe_media_key = _safe_key_part(media_key or "image")
        suffix = _guess_suffix(source_url, content_type)
        return f"x-media/{safe_post_id}/{safe_media_key}{suffix}"

    def public_url_for_key(self, object_key: str) -> str:
        if self.settings.cos_public_base_url:
            return f"{self.settings.cos_public_base_url}/{object_key}"
        return f"{self.settings.cos_endpoint.rstrip('/')}/{self.settings.cos_bucket}/{object_key}"

    def _validate_config(self) -> None:
        missing = [
            name
            for name, value in {
                "COS_ENDPOINT": self.settings.cos_endpoint,
                "COS_BUCKET": self.settings.cos_bucket,
                "COS_SECRET_ID": self.settings.cos_secret_id,
                "COS_SECRET_KEY": self.settings.cos_secret_key,
            }.items()
            if not value
        ]
        if missing:
            raise ExternalDependencyError(f"COS is not configured: {', '.join(missing)}")

    def _s3_client(self):
        try:
            import boto3
        except ImportError as exc:
            raise ExternalDependencyError("boto3 is required for COS uploads") from exc

        return boto3.client(
            "s3",
            endpoint_url=self.settings.cos_endpoint,
            region_name=self.settings.cos_region,
            aws_access_key_id=self.settings.cos_secret_id,
            aws_secret_access_key=self.settings.cos_secret_key,
        )


def _safe_key_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in str(value).strip())
    return cleaned[:160] or "unknown"


def _guess_suffix(source_url: str, content_type: str | None) -> str:
    suffix = PurePosixPath(urlparse(source_url).path).suffix.lower()
    if suffix and len(suffix) <= 10:
        return suffix
    if content_type:
        guessed = mimetypes.guess_extension(content_type)
        if guessed:
            return guessed
    return ".bin"


def _extend_unique(target: list[dict[str, Any]], items: list[dict[str, Any]], key_name: str) -> None:
    seen = {str(item.get(key_name)) for item in target if item.get(key_name) is not None}
    for item in items:
        key = item.get(key_name)
        if key is None or str(key) in seen:
            continue
        target.append(item)
        seen.add(str(key))
