"""Refresh-token lifecycle helpers (story S02.3).

Issue / verify / revoke long-lived refresh tokens persisted in the
`refresh_tokens` table. The raw token is a 256-bit URL-safe random
string returned once by `issue()`; only its sha256 hex digest is stored
on disk so a DB read alone cannot resurrect a session.

Internal to the auth module — cross-module callers must go through
`backend.modules.auth.public` (none of these helpers are exposed there
yet; the S02.4 transports live inside `modules.auth` itself).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.modules.auth.models import RefreshToken

# 32 bytes = 256 bits → 43 url-safe characters after base64. Wide enough
# that collisions on `token_hash` are not a realistic concern (the UNIQUE
# index is belt-and-braces).
_TOKEN_ENTROPY_BYTES = 32


class InvalidRefreshTokenError(Exception):
    """Raised when a refresh token fails verification (unknown, expired, revoked)."""


class ExpiredRefreshTokenError(InvalidRefreshTokenError):
    """Raised when the token's `expires_at` is in the past."""


class RevokedRefreshTokenError(InvalidRefreshTokenError):
    """Raised when the token has been explicitly revoked."""


def hash_refresh_token(raw_token: str) -> str:
    """Return the sha256 hex digest of `raw_token`.

    Exposed (rather than kept module-private) because `revoke()` takes a
    hash by design — callers receiving a raw token (e.g. the S02.4
    logout route) need a single canonical helper to derive the lookup
    key and stay aligned with what `issue()` persists.
    """
    return hashlib.sha256(raw_token.encode("ascii")).hexdigest()


async def issue(
    session: AsyncSession,
    user_id: UUID,
    device_label: str | None = None,
) -> str:
    """Persist a new refresh token for `user_id` and return the raw value.

    The raw token is returned **once** — the caller (login/refresh route)
    must hand it to the client immediately because the DB only retains a
    one-way hash. `expires_at` is computed from the current settings'
    `refresh_token_ttl_seconds`.
    """
    raw_token = secrets.token_urlsafe(_TOKEN_ENTROPY_BYTES)
    now = datetime.now(tz=UTC)
    settings = get_settings()
    record = RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh_token(raw_token),
        issued_at=now,
        expires_at=now + timedelta(seconds=settings.refresh_token_ttl_seconds),
        device_label=device_label,
    )
    session.add(record)
    await session.flush()
    return raw_token


async def verify(session: AsyncSession, raw_token: str) -> UUID:
    """Return the `user_id` bound to `raw_token` if it is still usable.

    Raises:
        RevokedRefreshTokenError: token row exists but `revoked_at` is set.
        ExpiredRefreshTokenError: token row exists but `expires_at` is in the past.
        InvalidRefreshTokenError: no token row matches the supplied value.

    The revoked check fires before the expired check so a deliberately
    revoked token never looks like "merely expired" to upstream handlers
    (which would otherwise log it less loudly).
    """
    token_hash = hash_refresh_token(raw_token)
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise InvalidRefreshTokenError("Refresh token is invalid")
    if record.revoked_at is not None:
        raise RevokedRefreshTokenError("Refresh token has been revoked")
    if record.expires_at <= datetime.now(tz=UTC):
        raise ExpiredRefreshTokenError("Refresh token has expired")
    return record.user_id


async def revoke(session: AsyncSession, token_hash: str) -> None:
    """Mark the refresh token with the given hash as revoked.

    Idempotent: a no-op when no row matches, or when the row is already
    revoked. We never delete rows (tombstone semantics) so audit logs
    and concurrent verifies still see the explicit revocation.
    """
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(tz=UTC))
    )
    await session.flush()
