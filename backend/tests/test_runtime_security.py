from __future__ import annotations

import pytest

from app.config import get_settings


def test_production_rejects_default_admin_and_jwt_secrets(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "change-me")
    monkeypatch.setenv("JWT_SECRET", "replace-with-a-long-random-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://serenity:serenity@postgres:5432/serenity")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="Unsafe production configuration"):
        get_settings().validate_runtime_security()


def test_production_accepts_randomized_runtime_secrets(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "random-admin-password-123456")
    monkeypatch.setenv("JWT_SECRET", "random-jwt-secret-value-with-more-than-32-characters")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://serenity:random-db-password@postgres:5432/serenity")
    monkeypatch.setenv("CORS_ORIGINS", "https://serenity.zenithy.art")
    get_settings.cache_clear()

    get_settings().validate_runtime_security()
