"""JWT issuance and verification helpers (story S02.2).

Internal to the auth module: cross-module callers must import the public
surface from `backend.modules.auth.public` instead.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import jwt
from jwt import ExpiredSignatureError, PyJWTError
from jwt.exceptions import (
    ImmatureSignatureError,
    InvalidAudienceError,
    InvalidIssuedAtError,
    InvalidIssuerError,
    MissingRequiredClaimError,
)

from backend.config import Settings


class InvalidTokenError(Exception):
    """Raised when a token fails verification (bad signature, malformed, etc.)."""


class ExpiredTokenError(InvalidTokenError):
    """Raised when a token's `exp` claim is in the past.

    Subclasses `InvalidTokenError` so broad `except InvalidTokenError`
    handlers also catch expirations.
    """


def issue_access_token(user_id: UUID, *, settings: Settings) -> str:
    """Issue a signed HS256 access JWT for `user_id`.

    The payload contains `sub` (stringified UUID), `iat`, `exp`
    (exp = iat + `settings.jwt_access_ttl_seconds`), and the pinned
    `aud` / `iss` claims (ADR 0016).

    `settings` is passed kw-only so the caller controls config injection
    (FastAPI routes use `Depends(get_settings)`); avoids the cached-import
    coupling that forced `cache_clear()` in tests.
    """
    now_ts = int(datetime.now(tz=UTC).timestamp())
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now_ts,
        "exp": now_ts + settings.jwt_access_ttl_seconds,
        "aud": settings.jwt_audience,
        "iss": settings.jwt_issuer,
    }
    return jwt.encode(
        payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
    )


# 30s of leeway absorbs typical NTP skew between a freshly-issued token and a
# verifying server with a slightly fast clock. Without it, a client at +1s
# would see the token rejected the instant after issuance.
_CLOCK_SKEW_LEEWAY_SECONDS = 30


def verify_access_token(token: str, *, settings: Settings) -> UUID:
    """Verify `token` and return the `user_id` from its `sub` claim.

    `aud` / `iss` are pinned per ADR 0016: a token missing those claims
    or carrying values different from `settings.jwt_audience` /
    `settings.jwt_issuer` is rejected as `InvalidTokenError`.

    Raises:
        ExpiredTokenError: when the token's `exp` claim is in the past
            (a 30 s NTP leeway is applied before declaring expiration).
        InvalidTokenError: on bad signature, malformed token, missing/
            malformed `sub` claim, missing/wrong `aud` or `iss`, or
            `iat` further in the future than the same 30 s leeway
            (defense in depth against backdated tokens).
    """
    try:
        # Algorithm whitelist is hardcoded (not read from settings) so a misconfigured
        # `JWT_ALGORITHM` cannot open HS256/RS256 key-confusion or `alg=none` attacks.
        # `leeway` widens the `exp` window symmetrically to tolerate NTP skew, and it
        # also bounds PyJWT's `iat` check: a token whose `iat` is more than `leeway`
        # in the future is rejected as `ImmatureSignatureError` (caught below). The
        # explicit post-decode `iat` check is kept only as a residual guard.
        # `audience=` + `issuer=` enforce ADR 0016. With both passed, PyJWT rejects a
        # token that is *missing* `aud` or `iss` (raising `MissingRequiredClaimError`),
        # closing the asymmetric gap that older python-jose left on `aud`. The explicit
        # `"aud"`/`"iss"` checks after `decode` are kept as defense-in-depth so a future
        # PyJWT change that loosens that validation cannot reintroduce the issue.
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            leeway=_CLOCK_SKEW_LEEWAY_SECONDS,
        )
    except ExpiredSignatureError as exc:
        raise ExpiredTokenError("Access token has expired") from exc
    except (
        InvalidAudienceError,
        InvalidIssuerError,
        InvalidIssuedAtError,
        ImmatureSignatureError,
        MissingRequiredClaimError,
    ) as exc:
        # Dedicated branch for claim-shape failures (`aud`/`iss` mismatch or
        # missing, `iat` non-int or further in the future than the leeway). The
        # catch-all `PyJWTError` below covers the structural / signature failures
        # — keep them distinct so a future caller can refine.
        raise InvalidTokenError("Access token has invalid claims") from exc
    except PyJWTError as exc:
        raise InvalidTokenError("Access token is invalid") from exc

    if "aud" not in payload:
        raise InvalidTokenError("Access token has no 'aud' claim")
    if "iss" not in payload:
        raise InvalidTokenError("Access token has no 'iss' claim")

    # Residual defense-in-depth: PyJWT already rejects an integer `iat` beyond
    # the leeway (`ImmatureSignatureError`, caught above). This re-check covers
    # the sliver PyJWT's integer comparison can miss — a sub-second float `iat`
    # straddling the `now + leeway` boundary — and survives a future PyJWT
    # change that loosened `iat` validation.
    iat = payload.get("iat")
    if isinstance(iat, int | float):
        now_ts = int(datetime.now(tz=UTC).timestamp())
        if iat > now_ts + _CLOCK_SKEW_LEEWAY_SECONDS:
            raise InvalidTokenError("Access token 'iat' is in the future")

    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise InvalidTokenError("Access token has no valid 'sub' claim")
    try:
        return UUID(sub)
    except ValueError as exc:
        raise InvalidTokenError("Access token 'sub' is not a valid UUID") from exc


def issue_sse_token(user_id: UUID, *, settings: Settings) -> str:
    """Issue a short-lived HS256 SSE stream token for `user_id` (S17.1, ADR 0012).

    Identical shape to `issue_access_token` but with the **dedicated** SSE
    audience (`settings.jwt_sse_audience`) and TTL (`settings.jwt_sse_ttl_seconds`,
    5 min). The audience is the only cloisonnement vs the access token (same
    `jwt_secret`, ADR 0016): this token is rejected by `verify_access_token` and
    vice-versa. There is **no** `scope` claim — the `aud` claim IS the scope, and
    unlike a custom `scope` it is verified by PyJWT at `decode` (ADR 0012 addendum).
    """
    now_ts = int(datetime.now(tz=UTC).timestamp())
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now_ts,
        "exp": now_ts + settings.jwt_sse_ttl_seconds,
        "aud": settings.jwt_sse_audience,
        "iss": settings.jwt_issuer,
    }
    return jwt.encode(
        payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
    )


def _decode_sse_payload(token: str, *, settings: Settings) -> dict[str, Any]:
    """`verify_sse_token` step 1: decode + verify signature/exp/aud/iss.

    Extracted so `verify_sse_token` stays a flat sequence of steps (C901):
    same hardcoded `["HS256"]` whitelist, same `leeway`, same `audience=`/
    `issuer=` pinning (rejects a *missing* `aud`/`iss`) as `verify_access_token`.
    """
    try:
        return jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            audience=settings.jwt_sse_audience,
            issuer=settings.jwt_issuer,
            leeway=_CLOCK_SKEW_LEEWAY_SECONDS,
        )
    except ExpiredSignatureError as exc:
        raise ExpiredTokenError("SSE token has expired") from exc
    except (
        InvalidAudienceError,
        InvalidIssuerError,
        InvalidIssuedAtError,
        ImmatureSignatureError,
        MissingRequiredClaimError,
    ) as exc:
        raise InvalidTokenError("SSE token has invalid claims") from exc
    except PyJWTError as exc:
        raise InvalidTokenError("SSE token is invalid") from exc


def _check_sse_claims_present(payload: dict[str, Any]) -> None:
    """`verify_sse_token` step 2: `aud`/`iss` presence guard."""
    if "aud" not in payload:
        raise InvalidTokenError("SSE token has no 'aud' claim")
    if "iss" not in payload:
        raise InvalidTokenError("SSE token has no 'iss' claim")


def _check_sse_iat_not_future(payload: dict[str, Any]) -> None:
    """`verify_sse_token` step 3: residual defense-in-depth `iat` guard (see
    `verify_access_token` for the full rationale — PyJWT already rejects an
    integer `iat` beyond the leeway; this covers a sub-second float straddling
    the boundary)."""
    iat = payload.get("iat")
    if isinstance(iat, int | float):
        now_ts = int(datetime.now(tz=UTC).timestamp())
        if iat > now_ts + _CLOCK_SKEW_LEEWAY_SECONDS:
            raise InvalidTokenError("SSE token 'iat' is in the future")


def _extract_sse_exp(payload: dict[str, Any]) -> int:
    """`verify_sse_token` step 4: `exp` claim extraction."""
    exp = payload.get("exp")
    if not isinstance(exp, int | float):
        raise InvalidTokenError("SSE token has no valid 'exp' claim")
    return int(exp)


def _extract_sse_user_id(payload: dict[str, Any]) -> UUID:
    """`verify_sse_token` step 5: `sub` claim extraction + UUID parsing."""
    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise InvalidTokenError("SSE token has no valid 'sub' claim")
    try:
        return UUID(sub)
    except ValueError as exc:
        raise InvalidTokenError("SSE token 'sub' is not a valid UUID") from exc


def verify_sse_token(token: str, *, settings: Settings) -> tuple[UUID, int]:
    """Verify an SSE token and return `(user_id, exp_ts)` (S17.1).

    Mirror of `verify_access_token` (same hardcoded `["HS256"]` whitelist, same
    `leeway`, same `audience=`/`issuer=` pinning that rejects a *missing* `aud`/
    `iss`, same defense-in-depth post-decode checks) but pinned on
    `settings.jwt_sse_audience`. `exp_ts` is returned so the stream can close the
    connection when the token expires (it is verified only at open).

    EVERY claim extraction is wrapped so a malformed token yields
    `InvalidTokenError` (HTTP 401), never an unhandled `KeyError`/`ValueError`
    surfacing as a 500.

    Delegates each step (decode, `aud`/`iss` presence, `iat` guard, `exp`/`sub`
    extraction) to a dedicated private helper, called in the SAME ORDER as
    before extraction (C901) — this function is a flat composition.

    Raises:
        ExpiredTokenError / InvalidTokenError: as `verify_access_token`.
    """
    payload = _decode_sse_payload(token, settings=settings)
    _check_sse_claims_present(payload)
    _check_sse_iat_not_future(payload)
    exp = _extract_sse_exp(payload)
    user_id = _extract_sse_user_id(payload)
    return user_id, exp
