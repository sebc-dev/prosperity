"""Unit tests for `backend.config.Settings` validation (story S02.2 review)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.config import (
    _DEV_JWT_SECRET,
    _MIN_JWT_SECRET_BYTES,
    DEV_DEFAULT_DATABASE_URL,
    Settings,
)

_REAL_DSN = "postgresql+asyncpg://app:secret@db.internal:5432/prosperity"
_REAL_JWT_SECRET = "a-real-production-secret-32-chars!!"


def test_dev_defaults_accepted_in_dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    settings = Settings()
    assert settings.app_env == "dev"
    assert settings.database_url == DEV_DEFAULT_DATABASE_URL
    assert settings.jwt_secret.get_secret_value() == "dev-secret-change-me-min-32-bytes-please"


def test_dev_defaults_accepted_in_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # The guard fires on `prod` only — `test` (used by CI/integration) keeps
    # the convenience of dev defaults so no env setup is required.
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    settings = Settings()
    assert settings.app_env == "test"


def test_dev_dsn_rejected_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("JWT_SECRET", _REAL_JWT_SECRET)
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings()


def test_dev_jwt_secret_rejected_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    # DSN is set explicitly so we reach the JWT guard rather than tripping
    # the DSN guard first.
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("DATABASE_URL", _REAL_DSN)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings()


def test_explicit_secrets_accepted_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("DATABASE_URL", _REAL_DSN)
    monkeypatch.setenv("JWT_SECRET", _REAL_JWT_SECRET)
    settings = Settings()
    assert settings.database_url == _REAL_DSN
    assert settings.jwt_secret.get_secret_value() == _REAL_JWT_SECRET


def test_short_jwt_secret_rejected_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    # A non-dev but <32-byte secret is a weak HS256 key (RFC 7518 §3.2). DSN is
    # set so we reach the JWT length guard rather than the DSN guard first.
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("DATABASE_URL", _REAL_DSN)
    monkeypatch.setenv("JWT_SECRET", "too-short-secret")  # 16 bytes
    # `match` pins the length guard specifically (not the dev-default guard,
    # which shares the "JWT_SECRET" prefix).
    with pytest.raises(ValidationError, match="at least 32 bytes"):
        Settings()


def test_short_jwt_secret_allowed_outside_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    # The length guard is prod-only: dev/test stay permissive so fixtures can
    # use short throwaway secrets without ceremony.
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("JWT_SECRET", "too-short-secret")  # 16 bytes
    settings = Settings()
    assert settings.jwt_secret.get_secret_value() == "too-short-secret"


def test_dev_default_secret_meets_min_length() -> None:
    # Invariant: the dev/test default must stay >= 32 bytes so it neither trips
    # PyJWT's InsecureKeyLengthWarning nor the prod length guard above.
    assert len(_DEV_JWT_SECRET.encode("utf-8")) >= _MIN_JWT_SECRET_BYTES


def test_jwt_secret_is_not_leaked_by_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    # `SecretStr` keeps the value out of `repr()` — a defense against accidental
    # logging of the signing key.
    monkeypatch.setenv("JWT_SECRET", "super-secret-do-not-leak")
    settings = Settings()
    assert "super-secret-do-not-leak" not in repr(settings)


# ---------------------------------------------------------------------------
# S03.3 — INITIAL_ADMIN_* env-var bootstrap settings
# ---------------------------------------------------------------------------


def _clear_initial_admin_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "INITIAL_ADMIN_EMAIL",
        "INITIAL_ADMIN_PASSWORD_HASH",
        "INITIAL_ADMIN_DISPLAY_NAME",
        "INITIAL_HOUSEHOLD_NAME",
    ):
        monkeypatch.delenv(key, raising=False)


def test_initial_admin_defaults_when_env_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Normal mode: env vars absent → both `None` / sensible defaults.

    The orchestrator relies on `None` for the email/hash pair to
    distinguish "no bootstrap requested" from "partial config".
    """
    _clear_initial_admin_env(monkeypatch)
    settings = Settings()
    assert settings.initial_admin_email is None
    assert settings.initial_admin_password_hash is None
    assert settings.initial_admin_display_name == "Admin"
    assert settings.initial_household_name == "Foyer"


def test_initial_admin_email_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Partial config: only EMAIL set — the orchestrator will skip + warn."""
    _clear_initial_admin_env(monkeypatch)
    monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "admin@example.com")
    settings = Settings()
    assert settings.initial_admin_email == "admin@example.com"
    assert settings.initial_admin_password_hash is None


def test_initial_admin_hash_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Partial config: only PASSWORD_HASH set."""
    _clear_initial_admin_env(monkeypatch)
    monkeypatch.setenv(
        "INITIAL_ADMIN_PASSWORD_HASH",
        "$argon2id$v=19$m=65536,t=3,p=4$AAA$BBB",
    )
    settings = Settings()
    assert settings.initial_admin_email is None
    assert settings.initial_admin_password_hash is not None


def test_initial_admin_password_hash_uses_secret_str(monkeypatch: pytest.MonkeyPatch) -> None:
    """SecretStr keeps the hash out of `repr()` — parity with `jwt_secret`.

    A hash isn't a plaintext password, but exposing it via Sentry frames
    or SQLAlchemy debug logs would give an attacker free brute-force
    material. Defense in depth.
    """
    sensitive_hash = "$argon2id$v=19$m=65536,t=3,p=4$AAAAAA$BBBBBB-do-not-leak"
    _clear_initial_admin_env(monkeypatch)
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD_HASH", sensitive_hash)
    settings = Settings()
    assert sensitive_hash not in repr(settings)


def test_initial_admin_custom_display_and_household(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_initial_admin_env(monkeypatch)
    monkeypatch.setenv("INITIAL_ADMIN_DISPLAY_NAME", "Alice")
    monkeypatch.setenv("INITIAL_HOUSEHOLD_NAME", "Foyer Dupont")
    settings = Settings()
    assert settings.initial_admin_display_name == "Alice"
    assert settings.initial_household_name == "Foyer Dupont"


def test_initial_admin_email_validates_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """`EmailStr` parity with `SetupRequest.email` rejects malformed values."""
    _clear_initial_admin_env(monkeypatch)
    monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "not-an-email")
    with pytest.raises(ValidationError):
        Settings()
