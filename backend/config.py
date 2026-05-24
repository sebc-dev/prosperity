"""Process configuration loaded from environment variables via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Top-level settings.

    All fields are populated from process env vars (case-insensitive) with
    optional `.env` overlay for local dev. Defaults target the local
    testcontainers-style Postgres image (postgres:17-alpine).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+asyncpg://prosperity:prosperity@localhost:5432/prosperity",
        description="Async SQLAlchemy DSN. Override via DATABASE_URL.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
