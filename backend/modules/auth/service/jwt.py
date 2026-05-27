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


def verify_access_token(token: str, *, settings: Settings) -> UUID:
    """Verify `token` and return the `user_id` from its `sub` claim.

    Raises:
        ExpiredTokenError: when the token's `exp` claim is in the past.
        InvalidTokenError: on bad signature, malformed token, or missing/
            malformed `sub` claim.
    """
    try:
        # Algorithm whitelist is hardcoded (not read from settings) so a misconfigured
        # `JWT_ALGORITHM` cannot open HS256/RS256 key-confusion or `alg=none` attacks.
        payload: dict[str, Any] = jwt.decode(
            token, settings.jwt_secret.get_secret_value(), algorithms=["HS256"]
        )
    except ExpiredSignatureError as exc:
        raise ExpiredTokenError("Access token has expired") from exc
    except JWTError as exc:
        raise InvalidTokenError("Access token is invalid") from exc

    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise InvalidTokenError("Access token has no valid 'sub' claim")
    try:
        return UUID(sub)
    except ValueError as exc:
        raise InvalidTokenError("Access token 'sub' is not a valid UUID") from exc
