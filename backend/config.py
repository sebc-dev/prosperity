"""Process configuration loaded from environment variables via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Dev/test convenience: matches the local Postgres image (postgres:17-alpine)
# used by docker compose and testcontainers. Explicitly named so the
# production guard below can detect a forgotten override.
DEV_DEFAULT_DATABASE_URL = "postgresql+asyncpg://prosperity:prosperity@localhost:5432/prosperity"


class Settings(BaseSettings):
    """Top-level settings.

    All fields are populated from process env vars (case-insensitive) with
    optional `.env` overlay for local dev.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["dev", "test", "prod"] = Field(
        default="dev",
        description="Runtime environment. `prod` forbids the dev DSN default.",
    )

    database_url: str = Field(
        default=DEV_DEFAULT_DATABASE_URL,
        description="Async SQLAlchemy DSN. Override via DATABASE_URL.",
    )

    @model_validator(mode="after")
    def _forbid_dev_default_in_prod(self) -> Settings:
        # Catches the "prod instance booted without DATABASE_URL" footgun:
        # the dev default points at localhost and would either fail noisily
        # or, worse, succeed against an unintended local Postgres.
        if self.app_env == "prod" and self.database_url == DEV_DEFAULT_DATABASE_URL:
            raise ValueError(
                "DATABASE_URL must be set explicitly when APP_ENV=prod "
                "(refusing to start with the dev-only default DSN)."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
