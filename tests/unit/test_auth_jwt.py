"""Unit tests for `backend.modules.auth.service.jwt` (story S02.2)."""

from __future__ import annotations

import base64
import json
import secrets
from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from jose import jwt as jose_jwt

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


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _forge_token_with_claims(claims: dict[str, object]) -> str:
    """Encode a JWT signed with the current secret/algo but arbitrary claims.

    Used to drive `verify_access_token`'s payload-validation branches without
    going through `issue_access_token` (which enforces a well-formed `sub`).
    """
    settings = get_settings()
    return jose_jwt.encode(
        claims,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def test_round_trip_returns_original_uuid() -> None:
    user_id = uuid4()
    token = issue_access_token(user_id)
    assert verify_access_token(token) == user_id


def test_round_trip_for_zero_uuid() -> None:
    # Edge case: nil UUID still survives a round-trip.
    user_id = UUID(int=0)
    assert verify_access_token(issue_access_token(user_id)) == user_id


def test_default_access_ttl_is_15_minutes() -> None:
    # P02.2.1 spec: access tokens expire after 15 minutes by default.
    token = issue_access_token(uuid4())
    claims = jose_jwt.get_unverified_claims(token)
    assert claims["exp"] - claims["iat"] == 900


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
    header, payload, _signature = token.split(".")
    # Replace the signature segment with random bytes — verification must fail.
    corrupted = f"{header}.{payload}.{secrets.token_urlsafe(43)}"
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
    monkeypatch.setenv("JWT_SECRET", "some-other-secret-value-32-chars!!")
    get_settings.cache_clear()
    with pytest.raises(InvalidTokenError):
        verify_access_token(token)


def test_token_without_sub_claim_raises_invalid_token_error() -> None:
    token = _forge_token_with_claims({"foo": "bar"})
    with pytest.raises(InvalidTokenError):
        verify_access_token(token)


def test_token_with_non_string_sub_raises_invalid_token_error() -> None:
    token = _forge_token_with_claims({"sub": 42})
    with pytest.raises(InvalidTokenError):
        verify_access_token(token)


def test_token_with_non_uuid_sub_raises_invalid_token_error() -> None:
    token = _forge_token_with_claims({"sub": "not-a-uuid"})
    with pytest.raises(InvalidTokenError):
        verify_access_token(token)


def test_token_with_none_algorithm_is_rejected() -> None:
    # Regression for HS256/`alg=none` confusion: even a structurally valid
    # unsigned token must be rejected because `verify_access_token` pins the
    # algorithm whitelist to `["HS256"]`.
    header = _b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode("utf-8"))
    payload = _b64url(json.dumps({"sub": str(uuid4())}).encode("utf-8"))
    unsigned_token = f"{header}.{payload}."
    with pytest.raises(InvalidTokenError):
        verify_access_token(unsigned_token)
