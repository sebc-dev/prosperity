"""Unit tests for `backend.modules.auth.service.jwt` (story S02.2)."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest

from backend.config import get_settings
from backend.modules.auth.service.jwt import (
    ExpiredTokenError,
    InvalidTokenError,
    issue_access_token,
    verify_access_token,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Make sure each test sees fresh env-derived settings."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_round_trip_returns_original_uuid() -> None:
    user_id = uuid4()
    token = issue_access_token(user_id)
    assert verify_access_token(token) == user_id


def test_round_trip_for_zero_uuid() -> None:
    # Edge case: nil UUID still survives a round-trip.
    user_id = UUID(int=0)
    assert verify_access_token(issue_access_token(user_id)) == user_id


def test_expired_token_raises_expired_token_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Negative TTL => token is already expired at issuance time.
    monkeypatch.setenv("JWT_ACCESS_TTL_SECONDS", "-1")
    get_settings.cache_clear()
    token = issue_access_token(uuid4())
    with pytest.raises(ExpiredTokenError):
        verify_access_token(token)


def test_expired_token_is_also_invalid_token_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # ExpiredTokenError must subclass InvalidTokenError so broad handlers work.
    monkeypatch.setenv("JWT_ACCESS_TTL_SECONDS", "-1")
    get_settings.cache_clear()
    token = issue_access_token(uuid4())
    with pytest.raises(InvalidTokenError):
        verify_access_token(token)


def test_corrupted_signature_raises_invalid_token_error() -> None:
    token = issue_access_token(uuid4())
    header, payload, signature = token.split(".")
    # Flip the first character of the signature segment to corrupt it.
    flipped = "B" if signature[0] != "B" else "C"
    corrupted = f"{header}.{payload}.{flipped}{signature[1:]}"
    with pytest.raises(InvalidTokenError):
        verify_access_token(corrupted)


def test_malformed_token_raises_invalid_token_error() -> None:
    with pytest.raises(InvalidTokenError):
        verify_access_token("not.a.jwt")


def test_wrong_secret_raises_invalid_token_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = issue_access_token(uuid4())
    # Rotate the secret after issuance: verification must reject the token.
    monkeypatch.setenv("JWT_SECRET", "some-other-secret")
    get_settings.cache_clear()
    with pytest.raises(InvalidTokenError):
        verify_access_token(token)
