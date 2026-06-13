from __future__ import annotations

from app.config import get_settings
from app.infrastructure import external_clients
from app.infrastructure.external_clients import DeepSeekClient, FeishuWebhookClient, XApiClient


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200, headers: dict[str, str] | None = None) -> None:
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self) -> dict:
        return self.payload


class FakeXSession:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def get(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if "/users/by/username/" in url:
            return FakeResponse({"data": {"id": "123"}})
        return FakeResponse(
            {
                "data": [{"id": "1800000000000000001", "text": "Hello", "created_at": "2026-06-11T10:00:00.000Z"}],
                "includes": {"media": [{"media_key": "3_abc", "type": "photo", "url": "https://example.com/a.jpg"}]},
                "meta": {},
            }
        )


class FakePostSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.posts: list[dict] = []

    def post(self, url: str, **kwargs):
        self.posts.append({"url": url, **kwargs})
        return self.response


def test_x_client_resolves_user_and_fetches_posts_with_configured_limits(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "test-x-token")
    monkeypatch.setenv("X_MAX_RESULTS", "7")
    monkeypatch.setenv("X_MAX_PAGES", "1")
    get_settings.cache_clear()

    session = FakeXSession()
    client = XApiClient(session=session)

    assert client.resolve_user("@aleabitoreddit") == "123"
    payload = client.fetch_posts("123", since_id="1800000000000000000")

    assert payload["data"][0]["id"] == "1800000000000000001"
    timeline_call = session.calls[1]
    assert timeline_call["headers"]["Authorization"] == "Bearer test-x-token"
    assert timeline_call["params"]["since_id"] == "1800000000000000000"
    assert timeline_call["params"]["max_results"] == 7
    assert "attachments.media_keys" in timeline_call["params"]["expansions"]


def test_deepseek_client_requests_plain_translation(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")
    get_settings.cache_clear()
    session = FakePostSession(
        FakeResponse(
            {
                "choices": [{"message": {"content": "忠实翻译 123"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            }
        )
    )

    translated, usage = DeepSeekClient(session=session).translate("Keep 123.")

    assert translated == "忠实翻译 123"
    assert usage["total_tokens"] == 3
    request_json = session.posts[0]["json"]
    assert request_json["temperature"] == 0.2
    assert request_json["thinking"] == {"type": "disabled"}
    assert request_json["messages"][1] == {"role": "user", "content": "Keep 123."}


def test_feishu_webhook_client_signs_and_sends(monkeypatch):
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://open.feishu.cn/open-apis/bot/v2/hook/test")
    monkeypatch.setenv("FEISHU_WEBHOOK_SECRET", "test-secret")
    get_settings.cache_clear()
    monkeypatch.setattr(external_clients.time, "time", lambda: 1781278397)
    session = FakePostSession(FakeResponse({"code": 0, "msg": "success"}))

    result = FeishuWebhookClient(session=session).send({"msg_type": "text", "content": {"text": "hello"}})

    assert result["code"] == 0
    posted_json = session.posts[0]["json"]
    assert posted_json["timestamp"] == "1781278397"
    assert posted_json["sign"]
    assert posted_json["content"]["text"] == "hello"
