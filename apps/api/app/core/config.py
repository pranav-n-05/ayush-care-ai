"""Environment-based configuration. No secrets have defaults that are usable in production."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AYUSH_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    app_name: str = "AyushCare AI API"

    # Database: async driver for the app, same URL is used by Alembic (async engine).
    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://ayushcare:ayushcare_dev_only@localhost:5432/ayushcare"
    )
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_timeout_seconds: float = 10.0
    db_connect_timeout_seconds: float = 5.0
    db_statement_timeout_ms: int = 15_000
    readiness_timeout_seconds: float = 2.0

    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    # "inline" records jobs without a broker (tests/dev); "celery" publishes after commit.
    # "inline": record jobs only (tests). "celery": publish to Redis after commit.
    # "inprocess": run jobs as asyncio tasks inside the API process (single-instance demos
    # without a worker, e.g. a free hosting tier). Jobs survive restarts via a startup sweep.
    job_dispatcher: Literal["inline", "celery", "inprocess"] = "inline"
    # Public synthetic demo: allows `seed-demo` in production and shows demo banners.
    public_demo: bool = False

    # Sessions / cookies
    session_cookie_name: str = "ayush_session"
    csrf_cookie_name: str = "ayush_csrf"
    session_absolute_ttl_minutes: int = 8 * 60
    session_idle_ttl_minutes: int = 30
    cookie_secure: bool = True
    cookie_samesite: Literal["lax", "strict"] = "lax"
    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    trusted_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Login throttling (per account + per IP, in-database counters)
    login_max_failures: int = 5
    login_lockout_minutes: int = 15

    # Documents
    storage_root: str = "./var/storage"
    max_upload_bytes: int = 10 * 1024 * 1024
    max_pdf_pages: int = 50

    # AI: only the in-process demo provider is implemented. External providers must stay
    # disabled unless an organization has documented approval (see docs/safety).
    llm_provider: Literal["demo-extractive"] = "demo-extractive"
    llm_timeout_seconds: float = 30.0
    llm_max_attempts: int = 2

    @field_validator("database_url", mode="before")
    @classmethod
    def _async_driver(cls, v: object) -> object:
        """Accept provider-style URLs (postgres://, postgresql://) and use asyncpg."""
        raw = v.get_secret_value() if isinstance(v, SecretStr) else v
        if isinstance(raw, str):
            for prefix in ("postgres://", "postgresql://"):
                if raw.startswith(prefix):
                    return "postgresql+asyncpg://" + raw[len(prefix) :]
        return v

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.environment == "production":
            url = self.database_url.get_secret_value()
            if "ayushcare_dev_only" in url:
                raise ValueError("Development database credentials are not allowed in production")
            if not self.cookie_secure:
                raise ValueError("cookie_secure must be true in production")
            if self.job_dispatcher == "inline":
                raise ValueError("production requires the celery or inprocess job dispatcher")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
