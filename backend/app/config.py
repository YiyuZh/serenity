from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int_env(name: str, default: int) -> int:
    value = _env(name)
    return int(value) if value else default


def _bool_env(name: str, default: bool = False) -> bool:
    value = _env(name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, _int_env(name, default)))


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: str
    redis_url: str
    admin_username: str
    admin_password: str
    jwt_secret: str
    jwt_algorithm: str
    jwt_expires_minutes: int
    cors_origins: tuple[str, ...]
    x_account_handle: str
    x_api_base_url: str
    x_bearer_token: str
    x_max_results: int
    x_max_pages: int
    deepseek_base_url: str
    deepseek_api_key: str
    deepseek_model: str
    feishu_webhook_url: str
    feishu_webhook_secret: str
    cos_endpoint: str
    cos_bucket: str
    cos_region: str
    cos_secret_id: str
    cos_secret_key: str
    cos_public_base_url: str
    poll_interval_seconds: int
    enable_task_enqueue: bool

    @property
    def celery_broker_url(self) -> str:
        return self.redis_url

    @property
    def celery_result_backend(self) -> str:
        return self.redis_url

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"prod", "production"}

    def validate_runtime_security(self) -> None:
        if not self.is_production:
            return

        problems: list[str] = []
        weak_passwords = {"", "admin", "password", "secret", "change-me"}
        weak_jwt_secrets = {"", "change-me", "change-me-in-production", "replace-with-a-long-random-secret", "test-secret"}

        if self.admin_username.strip() == "":
            problems.append("ADMIN_USERNAME must not be empty")
        if self.admin_password in weak_passwords or len(self.admin_password) < 16:
            problems.append("ADMIN_PASSWORD must be changed to a random value with at least 16 characters")
        if self.jwt_secret in weak_jwt_secrets or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET must be changed to a random value with at least 32 characters")
        if "*" in self.cors_origins:
            problems.append("CORS_ORIGINS must not contain '*' in production")
        if "replace-with" in self.database_url or "serenity:serenity@" in self.database_url:
            problems.append("DATABASE_URL/POSTGRES_PASSWORD must use a random production database password")
        if self.jwt_expires_minutes <= 0:
            problems.append("JWT_EXPIRES_MINUTES must be positive")

        if problems:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    origins = tuple(origin.strip() for origin in _env("CORS_ORIGINS", "http://localhost:5173").split(",") if origin.strip())
    return Settings(
        app_env=_env("APP_ENV", "development"),
        database_url=_env("DATABASE_URL", "postgresql+psycopg2://serenity:serenity@postgres:5432/serenity"),
        redis_url=_env("REDIS_URL", "redis://redis:6379/0"),
        admin_username=_env("ADMIN_USERNAME", "admin"),
        admin_password=_env("ADMIN_PASSWORD", "change-me"),
        jwt_secret=_env("JWT_SECRET", "change-me-in-production"),
        jwt_algorithm=_env("JWT_ALGORITHM", "HS256"),
        jwt_expires_minutes=_int_env("JWT_EXPIRES_MINUTES", 720),
        cors_origins=origins,
        x_account_handle=_env("X_ACCOUNT_HANDLE", "aleabitoreddit").lstrip("@"),
        x_api_base_url=_env("X_API_BASE_URL", "https://api.x.com/2").rstrip("/"),
        x_bearer_token=_env("X_BEARER_TOKEN"),
        x_max_results=_bounded_int_env("X_MAX_RESULTS", 10, 5, 100),
        x_max_pages=_bounded_int_env("X_MAX_PAGES", 3, 1, 20),
        deepseek_base_url=_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        deepseek_api_key=_env("DEEPSEEK_API_KEY"),
        deepseek_model=_env("DEEPSEEK_MODEL", "deepseek-v4-pro"),
        feishu_webhook_url=_env("FEISHU_WEBHOOK_URL"),
        feishu_webhook_secret=_env("FEISHU_WEBHOOK_SECRET"),
        cos_endpoint=_env("COS_ENDPOINT"),
        cos_bucket=_env("COS_BUCKET"),
        cos_region=_env("COS_REGION", "ap-guangzhou"),
        cos_secret_id=_env("COS_SECRET_ID"),
        cos_secret_key=_env("COS_SECRET_KEY"),
        cos_public_base_url=_env("COS_PUBLIC_BASE_URL").rstrip("/"),
        poll_interval_seconds=_int_env("POLL_INTERVAL_SECONDS", 180),
        enable_task_enqueue=_bool_env("ENABLE_TASK_ENQUEUE", False),
    )
