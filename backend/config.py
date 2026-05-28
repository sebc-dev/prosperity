"""Process configuration loaded from environment variables via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from ipaddress import IPv4Network, IPv6Network
from typing import Annotated, Any, Final, Literal

from pydantic import EmailStr, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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

    # --- INITIAL_ADMIN_* env-var bootstrap (S03.3 — see roadmap E03) ---
    # Optional escape hatch for automated restore / provisioning: if both
    # `initial_admin_email` and `initial_admin_password_hash` are set at
    # boot AND the DB is empty, the FastAPI lifespan creates the first
    # admin before `/setup` becomes reachable. The XOR / partial / format
    # validations live in the orchestrator (`accounts.service.setup.
    # bootstrap_initial_admin_from_env`) so a bad env-var value logs a
    # warning rather than crashing startup — the operator must always be
    # able to `/setup` manually if env-var bootstrap fails.
    initial_admin_email: EmailStr | None = Field(
        default=None,
        description=(
            "Email of the auto-bootstrapped admin (S03.3). Must be paired with "
            "INITIAL_ADMIN_PASSWORD_HASH; lone value triggers a warning + skip."
        ),
    )
    # `SecretStr` keeps the hash out of `repr()` / logs / Sentry frames.
    # An Argon2id hash is not equivalent to a plaintext password, but it
    # is still a secret (an attacker who exfiltrates it can mount offline
    # brute-force) — defense in depth.
    initial_admin_password_hash: SecretStr | None = Field(
        default=None,
        description=(
            "Pre-computed Argon2id hash (NEVER a plaintext password). Generate via "
            "scripts/hash_password.py. Stored AS-IS in users.password_hash so "
            "pwdlib.verify(plaintext, stored) matches at /auth/login."
        ),
    )
    initial_admin_display_name: str = Field(
        default="Admin",
        max_length=120,
        description=(
            "Display name for the env-var-bootstrapped admin. Defaults to 'Admin' — "
            "renameable post-bootstrap. Matches SetupRequest.display_name max_length."
        ),
    )
    initial_household_name: str = Field(
        default="Foyer",
        max_length=120,
        description=(
            "Household name applied to the env-var-bootstrapped foyer. Defaults to "
            "'Foyer'. Matches SetupRequest.household_name max_length."
        ),
    )

    # --- Trusted reverse-proxy CIDRs (follow-up to S03.3 — issue #69 part 1) ---
    # CSV of CIDR networks whose `X-Forwarded-For` header
    # `backend.shared.http.client_ip_for` will honour. Empty by default:
    # XFF is ignored, `request.client.host` wins (any direct client can
    # set XFF to anything, so consulting it unconditionally would let
    # them forge the audit trail and any future IP-based rate limit).
    # Set to the reverse-proxy subnets (e.g. `10.0.0.0/8,192.168.0.0/16`)
    # before exposing the service WAN.
    # `NoDecode` opts out of pydantic-settings' default complex-type
    # JSON parsing — without it, `TRUSTED_PROXY_IPS=10.0.0.0/8,...`
    # would be fed to `json.loads` and crash. We split the CSV
    # ourselves in `_split_trusted_proxy_csv` and let pydantic coerce
    # each item into an `IPv4Network | IPv6Network`.
    trusted_proxy_ips: Annotated[
        tuple[IPv4Network | IPv6Network, ...],
        NoDecode,
    ] = Field(
        default=(),
        description=(
            "CSV of CIDR networks whose X-Forwarded-For is honoured. Empty → XFF "
            "ignored (anti-spoofing default). Example: 10.0.0.0/8,192.168.0.0/16."
        ),
    )

    @field_validator("trusted_proxy_ips", mode="before")
    @classmethod
    def _split_trusted_proxy_csv(cls, v: Any) -> Any:
        # pydantic-settings (with NoDecode above) hands us the raw env
        # string. CSV is the universal reverse-proxy convention.
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

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
