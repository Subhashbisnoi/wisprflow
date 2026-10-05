"""Typed application settings loaded from environment variables and `.env`."""

import logging
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


def normalize_database_url(url: str) -> str:
    """Force the psycopg 3 driver for plain `postgres://` / `postgresql://` URLs."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Repo-root .env first, backend/.env overrides it.
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Ledgerline"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    business_timezone: str = "Asia/Kolkata"

    database_url: str = Field(validation_alias=AliasChoices("DATABASE_URL", "DB_URL"))

    jwt_secret: SecretStr | None = None
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = Field(default=480, ge=5, le=60 * 24 * 7)

    llm_provider: Literal["openai", "fake"] = "openai"
    openai_api_key: SecretStr | None = None
    openai_text_model: str = "gpt-4.1-mini"
    openai_vision_model: str = "gpt-4.1"
    openai_timeout_seconds: float = 60.0

    # "local" writes to STORAGE_DIR; "database" keeps documents in Postgres, which suits
    # serverless hosts (Vercel) whose filesystem is read-only and not shared (D-090).
    storage_backend: Literal["local", "database"] = "local"
    storage_dir: Path = BACKEND_DIR / "storage"
    max_upload_mb: int = Field(default=15, ge=1, le=100)
    max_files_per_upload: int = Field(default=20, ge=1, le=100)

    extraction_workers: int = Field(default=3, ge=1, le=32)
    extraction_max_attempts: int = Field(default=3, ge=1, le=10)
    extraction_backoff_base_seconds: float = 2.0
    start_job_queue: bool = True
    # "in_process" = background worker threads; "sync" = run extraction inside the upload
    # request, for serverless hosts that freeze the process after the response (D-091).
    job_queue_backend: Literal["in_process", "sync"] = "in_process"
    db_pool_size: int = Field(default=10, ge=1, le=50)

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, value: str) -> str:
        return normalize_database_url(value)

    @model_validator(mode="after")
    def _check_secrets(self) -> "Settings":
        if self.jwt_secret is None:
            if self.app_env == "production":
                raise ValueError("JWT_SECRET must be set in production")
            logger.warning("JWT_SECRET not set; generated an ephemeral development secret")
            self.jwt_secret = SecretStr(secrets.token_urlsafe(48))
        if self.llm_provider == "openai" and self.openai_api_key is None:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        return self

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def jwt_secret_value(self) -> str:
        assert self.jwt_secret is not None
        return self.jwt_secret.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()
