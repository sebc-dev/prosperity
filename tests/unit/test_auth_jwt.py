"""Unit tests for `backend.modules.auth.service.jwt` (story S02.2)."""

from __future__ import annotations

import base64
import json
import secrets
from uuid import UUID, uuid4

import pytest
from jose import jwt as jose_jwt
from pydantic import SecretStr

from backend.config import Settings
from backend.modules.auth.service.jwt import (
    ExpiredTokenError,
    InvalidTokenError,
    issue_access_token,
    verify_access_token,
)

_DEFAULT_TEST_SECRET = SecretStr("test-secret-do-not-use-in-prod-only-tests-okay!")


def _settings(
    *,
    jwt_secret: SecretStr = _DEFAULT_TEST_SECRET,
    jwt_algorithm: str = "HS256",
    jwt_access_ttl_seconds: int = 900,
) -> Settings:
    """Build a fresh `Settings` for a single test.

    Tests opt-in to overrides (e.g. negative TTL, alternate secret)
    per-call rather than via the `lru_cache`-mediated `get_settings()`
    they used to rely on.
    """
    return Settings(
        jwt_secret=jwt_secret,
        jwt_algorithm=jwt_algorithm,
        jwt_access_ttl_seconds=jwt_access_ttl_seconds,
    )


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _forge_token_with_claims(claims: dict[str, object], settings: Settings) -> str:
    """Encode a JWT signed with the supplied secret but arbitrary claims.

    Used to drive `verify_access_token`'s payload-validation branches without
    going through `issue_access_token` (which enforces a well-formed `sub`).
    """
    return jose_jwt.encode(
        claims,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def test_round_trip_returns_original_uuid() -> None:
    settings = _settings()
    user_id = uuid4()
    token = issue_access_token(user_id, settings=settings)
    assert verify_access_token(token, settings=settings) == user_id


def test_round_trip_for_zero_uuid() -> None:
    settings = _settings()
    user_id = UUID(int=0)
    token = issue_access_token(user_id, settings=settings)
    assert verify_access_token(token, settings=settings) == user_id


def test_default_access_ttl_is_15_minutes() -> None:
    # P02.2.1 spec: access tokens expire after 15 minutes by default.
    settings = _settings()
    token = issue_access_token(uuid4(), settings=settings)
    claims = jose_jwt.get_unverified_claims(token)
    assert claims["exp"] - claims["iat"] == 900


def test_expired_token_raises_expired_token_error() -> None:
    # Negative TTL => token is already expired at issuance time.
    settings = _settings(jwt_access_ttl_seconds=-1)
    token = issue_access_token(uuid4(), settings=settings)
    with pytest.raises(ExpiredTokenError):
        verify_access_token(token, settings=settings)


def test_expired_token_is_also_invalid_token_error() -> None:
    # ExpiredTokenError must subclass InvalidTokenError so broad handlers work.
    settings = _settings(jwt_access_ttl_seconds=-1)
    token = issue_access_token(uuid4(), settings=settings)
    with pytest.raises(InvalidTokenError):
        verify_access_token(token, settings=settings)


def test_corrupted_signature_raises_invalid_token_error() -> None:
    settings = _settings()
    token = issue_access_token(uuid4(), settings=settings)
    header, payload, _signature = token.split(".")
    # Replace the signature segment with random bytes — verification must fail.
    corrupted = f"{header}.{payload}.{secrets.token_urlsafe(43)}"
    with pytest.raises(InvalidTokenError):
        verify_access_token(corrupted, settings=settings)


def test_malformed_token_raises_invalid_token_error() -> None:
    settings = _settings()
    with pytest.raises(InvalidTokenError):
        verify_access_token("not.a.jwt", settings=settings)


def test_wrong_secret_raises_invalid_token_error() -> None:
    issuer_settings = _settings()
    token = issue_access_token(uuid4(), settings=issuer_settings)
    # Rotate the secret after issuance: verification must reject the token.
    verifier_settings = _settings(jwt_secret=SecretStr("some-other-secret-value-32-chars!!"))
    with pytest.raises(InvalidTokenError):
        verify_access_token(token, settings=verifier_settings)


def test_token_without_sub_claim_raises_invalid_token_error() -> None:
    settings = _settings()
    token = _forge_token_with_claims({"foo": "bar"}, settings)
    with pytest.raises(InvalidTokenError):
        verify_access_token(token, settings=settings)


def test_token_with_non_string_sub_raises_invalid_token_error() -> None:
    settings = _settings()
    token = _forge_token_with_claims({"sub": 42}, settings)
    with pytest.raises(InvalidTokenError):
        verify_access_token(token, settings=settings)


def test_token_with_non_uuid_sub_raises_invalid_token_error() -> None:
    settings = _settings()
    token = _forge_token_with_claims({"sub": "not-a-uuid"}, settings)
    with pytest.raises(InvalidTokenError):
        verify_access_token(token, settings=settings)


def test_token_with_none_algorithm_is_rejected() -> None:
    # Regression for HS256/`alg=none` confusion: even a structurally valid
    # unsigned token must be rejected because `verify_access_token` pins the
    # algorithm whitelist to `["HS256"]`.
    settings = _settings()
    header = _b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode("utf-8"))
    payload = _b64url(json.dumps({"sub": str(uuid4())}).encode("utf-8"))
    unsigned_token = f"{header}.{payload}."
    with pytest.raises(InvalidTokenError):
        verify_access_token(unsigned_token, settings=settings)
