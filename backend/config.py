"""Process configuration loaded from environment variables via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Final, Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Dev/test convenience: matches the local Postgres image (postgres:17-alpine)
# used by docker compose and testcontainers. Explicitly named so the
# production guard below can detect a forgotten override.
DEV_DEFAULT_DATABASE_URL = "postgresql+asyncpg://prosperity:prosperity@localhost:5432/prosperity"

# Sentinel for the well-known dev JWT signing key. The production guard refuses
# this value when `APP_ENV=prod` so a missing `JWT_SECRET` in real deployments
# fails fast instead of silently accepting tokens forged from a published value.
_DEV_JWT_SECRET: Final = "dev-secret-change-me"


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
        description="Runtime environment. `prod` forbids the dev DSN and JWT secret defaults.",
    )

    database_url: str = Field(
        default=DEV_DEFAULT_DATABASE_URL,
        description="Async SQLAlchemy DSN. Override via DATABASE_URL.",
    )

    # --- JWT (auth module — see story S02.2 / docs/roadmap/E02-auth-foundations.md) ---
    # `SecretStr` keeps the value out of `repr()`/logs. The dev default is only
    # accepted when `app_env != "prod"` (see `_forbid_dev_defaults_in_prod`).
    # Doubles as the HMAC pepper for `refresh_tokens.token_hash` (see
    # `backend.modules.auth.service.refresh_tokens.hash_refresh_token`).
    # Rotating this secret therefore invalidates every persisted refresh
    # token in one shot — plan rotations as forced re-login events.
    jwt_secret: SecretStr = Field(
        default=SecretStr(_DEV_JWT_SECRET),
        description="HS256 signing key — must be overridden in prod via JWT_SECRET.",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="JWT signing algorithm. Override via JWT_ALGORITHM.",
    )
    # `aud` / `iss` pinning (ADR 0016): the same `jwt_secret` doubles as the
    # refresh-token HMAC pepper, so any other artefact signed under that key
    # would otherwise be accepted by `verify_access_token`. Pinning audience
    # and issuer distinguishes a Prosperity access token from any other
    # HS256 token under the same secret. Values are stable service constants;
    # env overrides exist for staging/multi-tenant scenarios.
    jwt_audience: str = Field(
        default="prosperity-api",
        description="Expected `aud` claim on access tokens. Override via JWT_AUDIENCE.",
    )
    jwt_issuer: str = Field(
        default="prosperity-auth",
        description="Expected `iss` claim on access tokens. Override via JWT_ISSUER.",
    )
    jwt_access_ttl_seconds: int = Field(
        default=900,
        description="Access-token lifetime in seconds (15 minutes — see roadmap E02).",
    )
    refresh_token_ttl_seconds: int = Field(
        # The DB stores `expires_at = issued_at + ttl`, so changing this at
        # runtime only affects newly-issued tokens — existing rows keep
        # their original deadline.
        default=30 * 24 * 3600,
        description="Refresh-token lifetime in seconds (30 days — see roadmap E02).",
    )

    @model_validator(mode="after")
    def _forbid_dev_defaults_in_prod(self) -> Settings:
        # Catches the two "prod instance booted without explicit secrets" footguns:
        # (1) the dev DSN points at localhost — would fail noisily or, worse,
        # succeed against an unintended local Postgres;
        # (2) the dev JWT signing key is published in the repo — accepting tokens
        # forged from it lets anyone usurp any `user_id`.
        if self.app_env != "prod":
            return self
        if self.database_url == DEV_DEFAULT_DATABASE_URL:
            raise ValueError(
                "DATABASE_URL must be set explicitly when APP_ENV=prod "
                "(refusing to start with the dev-only default DSN)."
            )
        if self.jwt_secret.get_secret_value() == _DEV_JWT_SECRET:
            raise ValueError(
                "JWT_SECRET must be set explicitly when APP_ENV=prod "
                "(refusing the well-known dev default)."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
