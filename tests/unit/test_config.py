"""Unit tests for `backend.config.Settings` validation (story S02.2 review)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.config import DEV_DEFAULT_DATABASE_URL, Settings

_REAL_DSN = "postgresql+asyncpg://app:secret@db.internal:5432/prosperity"
_REAL_JWT_SECRET = "a-real-production-secret-32-chars!!"


def test_dev_defaults_accepted_in_dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    settings = Settings()
    assert settings.app_env == "dev"
    assert settings.database_url == DEV_DEFAULT_DATABASE_URL
    assert settings.jwt_secret.get_secret_value() == "dev-secret-change-me"


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


def test_jwt_secret_is_not_leaked_by_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    # `SecretStr` keeps the value out of `repr()` — a defense against accidental
    # logging of the signing key.
    monkeypatch.setenv("JWT_SECRET", "super-secret-do-not-leak")
    settings = Settings()
    assert "super-secret-do-not-leak" not in repr(settings)
