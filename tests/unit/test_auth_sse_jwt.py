"""Unit tests du token SSE scopé (S17.1, ADR 0012/0016).

Vérifie `issue_sse_token`/`verify_sse_token` : audience dédiée `prosperity-sse`,
TTL 5 min, **confusion d'audience BIDIRECTIONNELLE** fermée (un access token est
rejeté côté SSE et réciproquement — le cloisonnement = `aud`, ADR 0016), et la
robustesse F2 (toute extraction de claim → `InvalidTokenError`, jamais un 500 :
un `exp` absent/non-int donne 401)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import jwt as pyjwt
import pytest
from pydantic import SecretStr

from backend.config import Settings
from backend.modules.auth.service.jwt import (
    ExpiredTokenError,
    InvalidTokenError,
    issue_access_token,
    issue_sse_token,
    verify_access_token,
    verify_sse_token,
)

_SECRET = SecretStr("test-secret-do-not-use-in-prod-only-tests-okay!")
_OMIT = object()


def _settings(*, jwt_sse_ttl_seconds: int = 300, jwt_issuer: str = "prosperity-auth") -> Settings:
    return Settings(
        jwt_secret=_SECRET, jwt_sse_ttl_seconds=jwt_sse_ttl_seconds, jwt_issuer=jwt_issuer
    )


def _forge_sse(claims: dict[str, object], settings: Settings) -> str:
    """JWT signé avec le secret, claims arbitraires, `aud`/`iss` SSE par défaut."""
    enriched: dict[str, object] = {
        "aud": settings.jwt_sse_audience,
        "iss": settings.jwt_issuer,
        **claims,
    }
    enriched = {k: v for k, v in enriched.items() if v is not _OMIT}
    return pyjwt.encode(enriched, settings.jwt_secret.get_secret_value(), algorithm="HS256")


def test_round_trip_returns_user_id_and_exp() -> None:
    settings = _settings()
    uid = uuid4()
    user_id, exp_ts = verify_sse_token(issue_sse_token(uid, settings=settings), settings=settings)
    assert user_id == uid
    now = int(datetime.now(tz=UTC).timestamp())
    assert 290 <= exp_ts - now <= 305  # ~5 min, marge


def test_default_sse_ttl_is_5_minutes() -> None:
    assert Settings(jwt_secret=_SECRET).jwt_sse_ttl_seconds == 300


# ── confusion d'audience BIDIRECTIONNELLE (le cœur du cloisonnement) ────────────
def test_access_token_is_rejected_by_verify_sse_token() -> None:
    settings = _settings()
    access = issue_access_token(uuid4(), settings=settings)  # aud=prosperity-api
    with pytest.raises(InvalidTokenError):
        verify_sse_token(access, settings=settings)


def test_sse_token_is_rejected_by_verify_access_token() -> None:
    settings = _settings()
    sse = issue_sse_token(uuid4(), settings=settings)  # aud=prosperity-sse
    with pytest.raises(InvalidTokenError):
        verify_access_token(sse, settings=settings)


def test_sse_token_with_foreign_issuer_is_rejected() -> None:
    # `aud` correct mais `iss` étranger → rejeté (les DEUX claims sont épinglés).
    settings = _settings()
    forged = _forge_sse({"sub": str(uuid4()), "exp": 9_999_999_999, "iss": "evil"}, settings)
    with pytest.raises(InvalidTokenError):
        verify_sse_token(forged, settings=settings)


def test_sse_token_without_aud_is_rejected() -> None:
    settings = _settings()
    forged = _forge_sse({"sub": str(uuid4()), "exp": 9_999_999_999, "aud": _OMIT}, settings)
    with pytest.raises(InvalidTokenError):
        verify_sse_token(forged, settings=settings)


def test_corrupted_signature_is_rejected() -> None:
    settings = _settings()
    token = issue_sse_token(uuid4(), settings=settings)
    with pytest.raises(InvalidTokenError):
        verify_sse_token(token + "x", settings=settings)


def test_expired_sse_token_raises_expired() -> None:
    settings = _settings(jwt_sse_ttl_seconds=-60)
    token = issue_sse_token(uuid4(), settings=settings)
    with pytest.raises(ExpiredTokenError):
        verify_sse_token(token, settings=settings)


# ── F2 : robustesse — extraction de claim défensive (jamais 500) ───────────────
def test_sse_token_without_exp_raises_invalid_not_500() -> None:
    settings = _settings()
    forged = _forge_sse({"sub": str(uuid4()), "exp": _OMIT}, settings)  # signé, aud OK, pas d'exp
    with pytest.raises(InvalidTokenError):
        verify_sse_token(forged, settings=settings)


def test_sse_token_with_non_numeric_exp_raises_invalid_not_500() -> None:
    settings = _settings()
    forged = _forge_sse({"sub": str(uuid4()), "exp": "soon"}, settings)
    with pytest.raises(InvalidTokenError):
        verify_sse_token(forged, settings=settings)


def test_sse_token_with_non_uuid_sub_raises_invalid() -> None:
    settings = _settings()
    forged = _forge_sse({"sub": "not-a-uuid", "exp": 9_999_999_999}, settings)
    with pytest.raises(InvalidTokenError):
        verify_sse_token(forged, settings=settings)
