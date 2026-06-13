from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.infrastructure.db import Base, get_session
from app.infrastructure.models import Post, PushTarget, SourceAccount
from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    Base.metadata.create_all(engine)

    def override_session():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_session] = override_session

    with TestingSession() as session:
        account = SourceAccount(source="x", handle="aleabitoreddit", active=True)
        target = PushTarget(channel="feishu", name="Main Feishu", env_key="FEISHU_MAIN", active=True)
        session.add_all([account, target])
        session.flush()
        session.add(
            Post(
                account_id=account.id,
                source="x",
                post_id="1800000000000000001",
                post_url="https://x.com/aleabitoreddit/status/1800000000000000001",
                post_type="original",
                original_text="Original",
                translated_text="译文",
                fetch_status="succeeded",
                media_status="failed",
                translation_status="succeeded",
                push_status="failed",
                published_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

    return TestClient(app)


def _token(client: TestClient) -> str:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "secret"})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_auth_protects_api(client):
    assert client.get("/api/dashboard/summary").status_code == 401
    token = _token(client)
    response = client.get("/api/dashboard/summary", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["posts"] == 1


def test_posts_list_detail_retry_and_skip(client):
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}

    posts = client.get("/api/posts?status=failed", headers=headers)
    assert posts.status_code == 200
    post_id = posts.json()[0]["id"]

    detail = client.get(f"/api/posts/{post_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["post_id"] == "1800000000000000001"

    events = client.get(f"/api/posts/{post_id}/events", headers=headers)
    assert events.status_code == 200
    assert events.json()[0]["event_type"] == "fetch"

    retry = client.post(f"/api/posts/{post_id}/retry", headers=headers)
    assert retry.status_code == 200
    assert retry.json()["status"] == "retrying"

    skip = client.post(f"/api/posts/{post_id}/skip", headers=headers)
    assert skip.status_code == 200
    assert skip.json()["status"] == "skipped"


def test_accounts_manual_sync(client):
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    accounts = client.get("/api/accounts", headers=headers)
    assert accounts.status_code == 200
    account_id = accounts.json()[0]["id"]

    response = client.post(f"/api/accounts/{account_id}/sync", headers=headers)
    assert response.status_code == 200
    assert response.json()["triggered_by"] == "manual"
