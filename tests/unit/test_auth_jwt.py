"""Unit tests for `backend.modules.auth.service.jwt` (story S02.2)."""

from __future__ import annotations

import base64
import json
import secrets
from datetime import UTC, datetime
from uuid import UUID, uuid4

import jwt as pyjwt
import pytest
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
    jwt_audience: str = "prosperity-api",
    jwt_issuer: str = "prosperity-auth",
) -> Settings:
    """Build a fresh `Settings` for a single test.

    Tests opt-in to overrides (e.g. negative TTL, alternate secret,
    alternate aud/iss for ADR 0016 negative paths) per-call rather than
    via the `lru_cache`-mediated `get_settings()` they used to rely on.
    """
    return Settings(
        jwt_secret=jwt_secret,
        jwt_algorithm=jwt_algorithm,
        jwt_access_ttl_seconds=jwt_access_ttl_seconds,
        jwt_audience=jwt_audience,
        jwt_issuer=jwt_issuer,
    )


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


_OMIT = object()


def _forge_token_with_claims(claims: dict[str, object], settings: Settings) -> str:
    """Encode a JWT signed with the supplied secret but arbitrary claims.

    Used to drive `verify_access_token`'s payload-validation branches without
    going through `issue_access_token` (which enforces a well-formed `sub`).

    Defaults `aud` / `iss` to the settings values so most negative-path
    tests can exercise their target branch (no `sub`, malformed `sub`, …)
    without each one having to remember the ADR 0016 claims. Tests that
    target the ADR 0016 branch itself pass `aud=_OMIT` or override the
    value explicitly to drop / change the claim.
    """
    enriched: dict[str, object] = {
        "aud": settings.jwt_audience,
        "iss": settings.jwt_issuer,
        **claims,
    }
    enriched = {k: v for k, v in enriched.items() if v is not _OMIT}
    return pyjwt.encode(
        enriched,
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
    claims = pyjwt.decode(token, options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] == 900


def test_expired_token_raises_expired_token_error() -> None:
    # Negative TTL well past the 30 s leeway => token is unambiguously expired.
    settings = _settings(jwt_access_ttl_seconds=-60)
    token = issue_access_token(uuid4(), settings=settings)
    with pytest.raises(ExpiredTokenError):
        verify_access_token(token, settings=settings)


def test_expired_token_is_also_invalid_token_error() -> None:
    # ExpiredTokenError must subclass InvalidTokenError so broad handlers work.
    settings = _settings(jwt_access_ttl_seconds=-60)
    token = issue_access_token(uuid4(), settings=settings)
    with pytest.raises(InvalidTokenError):
        verify_access_token(token, settings=settings)


def test_token_expired_within_leeway_is_accepted() -> None:
    # exp = now - 5s; with 30s leeway the token is still inside the acceptance
    # window. Mirrors a client whose clock is a few seconds ahead of ours.
    settings = _settings()
    now_ts = int(datetime.now(tz=UTC).timestamp())
    user_id = uuid4()
    token = _forge_token_with_claims(
        {"sub": str(user_id), "iat": now_ts - 60, "exp": now_ts - 5},
        settings,
    )
    assert verify_access_token(token, settings=settings) == user_id


def test_token_with_future_iat_outside_leeway_is_rejected() -> None:
    # iat = now + 60s, well past the 30s leeway → backdated token (or attacker
    # with a forged clock). Must be rejected as Invalid (not Expired) because
    # `exp` is also in the future — only `iat` is anomalous.
    settings = _settings()
    now_ts = int(datetime.now(tz=UTC).timestamp())
    token = _forge_token_with_claims(
        {"sub": str(uuid4()), "iat": now_ts + 60, "exp": now_ts + 900},
        settings,
    )
    with pytest.raises(InvalidTokenError) as excinfo:
        verify_access_token(token, settings=settings)
    # Must not be the Expired subclass — we want operators to grep `Invalid…`
    # without surfacing ExpiredTokenError noise.
    assert not isinstance(excinfo.value, ExpiredTokenError)


def test_token_with_future_iat_within_leeway_is_accepted() -> None:
    # iat = now + 5s — within the 30s skew tolerance. Mirrors a client whose
    # clock is a few seconds ahead of the verifier.
    settings = _settings()
    now_ts = int(datetime.now(tz=UTC).timestamp())
    user_id = uuid4()
    token = _forge_token_with_claims(
        {"sub": str(user_id), "iat": now_ts + 5, "exp": now_ts + 900},
        settings,
    )
    assert verify_access_token(token, settings=settings) == user_id


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


# --- ADR 0016: `aud` / `iss` pinning ------------------------------------------
#
# `JWT_SECRET` doubles as the refresh-token HMAC pepper, so any future
# artefact signed under the same key would otherwise be accepted by
# `verify_access_token`. The tests below pin the rejection contract:
# a token must carry `aud=settings.jwt_audience` AND `iss=settings.jwt_issuer`
# to be accepted. PyJWT rejects a missing `aud`/`iss` natively (it raises
# `MissingRequiredClaimError` when `audience=`/`issuer=` are passed);
# `verify_access_token` keeps explicit `"aud"`/`"iss"` checks as
# defense-in-depth should that validation ever loosen.


def test_issued_token_carries_pinned_aud_and_iss() -> None:
    # Round-trip sanity: the claims `verify_access_token` requires are the
    # ones `issue_access_token` actually writes.
    settings = _settings()
    token = issue_access_token(uuid4(), settings=settings)
    claims = pyjwt.decode(token, options={"verify_signature": False})
    assert claims["aud"] == settings.jwt_audience
    assert claims["iss"] == settings.jwt_issuer


def test_token_without_aud_claim_is_rejected() -> None:
    # A token missing `aud` is rejected: PyJWT raises
    # `MissingRequiredClaimError("aud")` when `audience=` is passed, and the
    # explicit `"aud" not in payload` check backs it up as defense-in-depth.
    settings = _settings()
    token = _forge_token_with_claims({"sub": str(uuid4()), "aud": _OMIT}, settings)
    with pytest.raises(InvalidTokenError):
        verify_access_token(token, settings=settings)


def test_token_with_wrong_aud_is_rejected() -> None:
    # Cross-service scenario: a token signed with the same `JWT_SECRET`
    # but emitted by/for another service must not be accepted by the API.
    settings = _settings()
    token = _forge_token_with_claims({"sub": str(uuid4()), "aud": "some-other-service"}, settings)
    with pytest.raises(InvalidTokenError):
        verify_access_token(token, settings=settings)


def test_token_without_iss_claim_is_rejected() -> None:
    # Two redundant rejections cover this: (1) PyJWT raises
    # `MissingRequiredClaimError("iss")` when `issuer=` is passed and the
    # claim is absent; (2) the explicit `"iss" not in payload` check after
    # `decode` catches it again as defense-in-depth, mirroring the `aud` check.
    settings = _settings()
    token = _forge_token_with_claims({"sub": str(uuid4()), "iss": _OMIT}, settings)
    with pytest.raises(InvalidTokenError):
        verify_access_token(token, settings=settings)


def test_token_with_wrong_iss_is_rejected() -> None:
    settings = _settings()
    token = _forge_token_with_claims({"sub": str(uuid4()), "iss": "some-other-issuer"}, settings)
    with pytest.raises(InvalidTokenError):
        verify_access_token(token, settings=settings)


def test_token_aud_iss_rejection_is_invalid_not_expired() -> None:
    # `aud` / `iss` mismatches must surface as `InvalidTokenError`, never
    # the `ExpiredTokenError` subclass — operators grepping for expirations
    # should not see cross-service token attempts in that bucket.
    settings = _settings()
    token = _forge_token_with_claims({"sub": str(uuid4()), "aud": "some-other-service"}, settings)
    with pytest.raises(InvalidTokenError) as excinfo:
        verify_access_token(token, settings=settings)
    assert not isinstance(excinfo.value, ExpiredTokenError)


def test_token_issued_for_one_audience_rejected_when_verifier_expects_another() -> None:
    # Models a deployment that renamed `jwt_audience` (or a separate
    # service that legitimately emits to a different aud): the verifier
    # configured for "prosperity-api" must reject a token issued for
    # "prosperity-mcp" even though signature, sub, and ttl are valid.
    issuer_settings = _settings(jwt_audience="prosperity-mcp")
    token = issue_access_token(uuid4(), settings=issuer_settings)
    verifier_settings = _settings()  # default jwt_audience="prosperity-api"
    with pytest.raises(InvalidTokenError):
        verify_access_token(token, settings=verifier_settings)
