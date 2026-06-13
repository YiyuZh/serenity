from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class NormalizedMedia:
    media_key: str | None
    media_type: str | None
    original_url: str | None
    preview_url: str | None
    alt_text: str | None


@dataclass(frozen=True)
class NormalizedPost:
    post_id: str
    post_url: str
    post_type: str
    referenced_post_id: str | None
    conversation_id: str | None
    original_text: str
    lang: str | None
    published_at: datetime | None
    media: list[NormalizedMedia]
    raw_json: dict[str, Any]


def normalize_x_payload(payload: dict[str, Any], handle: str) -> list[NormalizedPost]:
    tweets = payload.get("data") or []
    media_index = {
        item.get("media_key"): item
        for item in (payload.get("includes") or {}).get("media", [])
        if item.get("media_key")
    }
    posts: list[NormalizedPost] = []
    normalized_handle = handle.lstrip("@")
    for tweet in tweets:
        post_id = str(tweet["id"])
        media_keys = (tweet.get("attachments") or {}).get("media_keys") or []
        media = [_normalize_media(media_index[key]) for key in media_keys if key in media_index]
        post_type, referenced_post_id = _reference_type(tweet.get("referenced_tweets") or [])
        posts.append(
            NormalizedPost(
                post_id=post_id,
                post_url=f"https://x.com/{normalized_handle}/status/{post_id}",
                post_type=post_type,
                referenced_post_id=referenced_post_id,
                conversation_id=tweet.get("conversation_id"),
                original_text=tweet.get("text") or "",
                lang=tweet.get("lang"),
                published_at=_parse_datetime(tweet.get("created_at")),
                media=media,
                raw_json={"tweet": tweet, "media": [media_index[key] for key in media_keys if key in media_index]},
            )
        )
    return posts


def _normalize_media(item: dict[str, Any]) -> NormalizedMedia:
    return NormalizedMedia(
        media_key=item.get("media_key"),
        media_type=item.get("type"),
        original_url=item.get("url") or item.get("preview_image_url"),
        preview_url=item.get("preview_image_url"),
        alt_text=item.get("alt_text"),
    )


def _reference_type(referenced: list[dict[str, Any]]) -> tuple[str, str | None]:
    if not referenced:
        return "original", None
    first = referenced[0]
    return {
        "quoted": "quote",
        "replied_to": "reply",
        "retweeted": "retweet",
    }.get(first.get("type"), "quote"), first.get("id")


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
