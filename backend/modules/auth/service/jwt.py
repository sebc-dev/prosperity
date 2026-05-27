"""JWT issuance and verification helpers (story S02.2).

Internal to the auth module: cross-module callers must import the public
surface from `backend.modules.auth.public` instead.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from jose import ExpiredSignatureError, JWTError, jwt

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

    The payload contains `sub` (stringified UUID), `iat`, and `exp` claims
    (exp = iat + `settings.jwt_access_ttl_seconds`).

    `settings` is passed kw-only so the caller controls config injection
    (FastAPI routes use `Depends(get_settings)`); avoids the cached-import
    coupling that forced `cache_clear()` in tests.
    """
    now_ts = int(datetime.now(tz=UTC).timestamp())
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now_ts,
        "exp": now_ts + settings.jwt_access_ttl_seconds,
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

    Raises:
        ExpiredTokenError: when the token's `exp` claim is in the past
            (a 30 s NTP leeway is applied before declaring expiration).
        InvalidTokenError: on bad signature, malformed token, missing/
            malformed `sub` claim, or `iat` further in the future than
            the same 30 s leeway (defense in depth against backdated
            tokens).
    """
    try:
        # Algorithm whitelist is hardcoded (not read from settings) so a misconfigured
        # `JWT_ALGORITHM` cannot open HS256/RS256 key-confusion or `alg=none` attacks.
        # `verify_iat=True` type-checks `iat`; `leeway` widens the `exp` window
        # symmetrically to tolerate NTP skew. python-jose's `verify_iat` does NOT
        # reject future-iat tokens (it only validates the type) — the explicit
        # check below provides that defense-in-depth.
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            options={"verify_iat": True, "leeway": _CLOCK_SKEW_LEEWAY_SECONDS},
        )
    except ExpiredSignatureError as exc:
        raise ExpiredTokenError("Access token has expired") from exc
    except JWTError as exc:
        raise InvalidTokenError("Access token is invalid") from exc

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
