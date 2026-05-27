"""Refresh-token lifecycle helpers (stories S02.3 + S02.4).

Issue / verify / rotate / revoke long-lived refresh tokens persisted in
the `refresh_tokens` table. The raw token is a 256-bit URL-safe random
string returned once on issuance / rotation; only its HMAC-SHA256 hex
digest is stored on disk so a DB read alone cannot resurrect a session.

Internal to the auth module — cross-module callers must go through
`backend.modules.auth.public`.

Settings are passed kw-only (`*, settings: Settings`) to keep these
helpers testable without `get_settings.cache_clear()`. FastAPI routes
inject via `Depends(get_settings)`.
"""

from __future__ import annotations

import hmac
import logging
import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.engine.cursor import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings
from backend.modules.auth.models import RefreshToken

logger = logging.getLogger(__name__)

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


def hash_refresh_token(raw_token: str, *, settings: Settings) -> str:
    """Return the HMAC-SHA256 hex digest of `raw_token` keyed by `JWT_SECRET`.

    Exposed (rather than kept module-private) because `revoke()` takes a
    hash by design — callers receiving a raw token (e.g. the S02.4
    logout route) need a single canonical helper to derive the lookup
    key and stay aligned with what `issue()` persists.

    The HMAC key (the JWT signing secret) acts as a pepper: an attacker
    who obtains a DB dump still cannot offline-confirm a candidate raw
    token without also stealing the application secret. A plain
    `sha256(raw)` would not have that property.

    Operational consequence: rotating `JWT_SECRET` instantly invalidates
    every persisted refresh token (the recomputed HMAC will not match
    any stored hash). Plan a secret rotation as a forced re-login event,
    not a transparent ops task.
    """
    secret = settings.jwt_secret.get_secret_value().encode("utf-8")
    return hmac.new(secret, raw_token.encode("utf-8"), sha256).hexdigest()


async def issue(
    session: AsyncSession,
    user_id: UUID,
    *,
    settings: Settings,
    device_label: str | None = None,
) -> str:
    """Persist a new refresh token for `user_id` and return the raw value.

    The raw token is returned **once** — the caller (login route) must
    hand it to the client immediately because the DB only retains a
    one-way hash. `expires_at` is computed from the supplied settings'
    `refresh_token_ttl_seconds`.

    Each call starts a new rotation family: `family_id = uuid4()`,
    `parent_id = None`. `rotate()` (below) consumes a parent token and
    re-issues sharing the parent's `family_id`.
    """
    raw_token = secrets.token_urlsafe(_TOKEN_ENTROPY_BYTES)
    now = datetime.now(tz=UTC)
    record = RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh_token(raw_token, settings=settings),
        issued_at=now,
        expires_at=now + timedelta(seconds=settings.refresh_token_ttl_seconds),
        device_label=device_label,
        family_id=uuid4(),
    )
    session.add(record)
    await session.flush()
    return raw_token


async def verify_readonly(session: AsyncSession, raw_token: str, *, settings: Settings) -> UUID:
    """Return the `user_id` bound to `raw_token` if it is still usable.

    Raises:
        RevokedRefreshTokenError: token row exists but `revoked_at` is set.
        ExpiredRefreshTokenError: token row exists and `expires_at <= now`
            (the deadline is treated as already elapsed, not "still valid
            for one more instant").
        InvalidRefreshTokenError: no token row matches the supplied value.

    The revoked check fires before the expired check so a deliberately
    revoked token never looks like "merely expired" to upstream handlers
    (which would otherwise log it less loudly).

    **Read-only contract — explicit in the name.** This function does
    NOT take a row lock; using it as the pre-flight check before a write
    re-introduces the S02.3 TOCTOU. Routes that need to consume a
    refresh token (rotate, revoke) must use `rotate()` / `revoke()`
    which are single-statement atomic.
    """
    token_hash = hash_refresh_token(raw_token, settings=settings)
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


async def rotate(session: AsyncSession, raw_token: str, *, settings: Settings) -> tuple[UUID, str]:
    """Atomically revoke `raw_token`, issue a new one in the same family.

    Returns `(user_id, new_raw_token)`. Raises:
      - `InvalidRefreshTokenError`: token unknown.
      - `ExpiredRefreshTokenError`: row exists, `expires_at <= now`, never revoked.
      - `RevokedRefreshTokenError`: row already revoked → triggers
        family-wide invalidation (replay detected) before raising.

    Atomicity: the `UPDATE … RETURNING` of step 1 is single-statement
    atomic and runs under REPEATABLE READ (cf. `backend.shared.db`).
    Concurrent rotations on the same row see exactly one winner — losers
    get `rowcount=0` and fall through to the replay branch, which then
    revokes the whole family.
    """
    token_hash = hash_refresh_token(raw_token, settings=settings)
    now = datetime.now(tz=UTC)

    # Step 1 — atomic UPDATE on the live row. The `revoked_at IS NULL`
    # predicate means at most one of N concurrent rotations wins; the
    # losers see `rowcount=0` and fall through to the replay branch.
    update_result = cast(
        "CursorResult[tuple[UUID, UUID, UUID]]",
        await session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
            .values(revoked_at=now)
            .returning(RefreshToken.id, RefreshToken.user_id, RefreshToken.family_id)
        ),
    )
    row = update_result.one_or_none()

    if row is None:
        # Distinguish unknown / revoked / expired for logging and replay.
        existing = (
            await session.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        ).scalar_one_or_none()
        if existing is None:
            raise InvalidRefreshTokenError("Refresh token is invalid")
        if existing.revoked_at is not None:
            # Replay detected → invalidate the entire family.
            logger.warning(
                "refresh_token_replay_family_invalidated",
                extra={
                    "user_id": str(existing.user_id),
                    "family_id": str(existing.family_id),
                    "token_hash_prefix": token_hash[:8],
                    "time_since_revocation_seconds": (now - existing.revoked_at).total_seconds(),
                },
            )
            await session.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.family_id == existing.family_id,
                    RefreshToken.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            await session.flush()
            raise RevokedRefreshTokenError("Refresh token replay detected; family invalidated")
        raise ExpiredRefreshTokenError("Refresh token has expired")

    # `row` is a SQLAlchemy `Row`; access by named attribute (not `.t`).
    parent_id = row.id
    user_id = row.user_id
    family_id = row.family_id

    # Step 2 — issue the successor in the same family.
    new_raw = secrets.token_urlsafe(_TOKEN_ENTROPY_BYTES)
    record = RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh_token(new_raw, settings=settings),
        issued_at=now,
        expires_at=now + timedelta(seconds=settings.refresh_token_ttl_seconds),
        family_id=family_id,
        parent_id=parent_id,
    )
    session.add(record)
    await session.flush()

    return user_id, new_raw


async def revoke(session: AsyncSession, token_hash: str) -> int:
    """Mark the refresh token with the given hash as revoked.

    Returns the number of rows updated (0 when no row matched or the
    matching row was already revoked, 1 when a live token was just
    revoked). Useful for audit logging — `revoke() == 0` distinguishes
    "hash never existed / already gone" from "actually revoked now".

    Idempotent: a no-op when no row matches, or when the row is already
    revoked. We never delete rows (tombstone semantics) so audit logs
    and concurrent verifies still see the explicit revocation.

    Deliberately ignores `expires_at` — already-expired tokens still
    get a `revoked_at` timestamp. A logout (or admin revoke) on a
    token whose deadline has just elapsed is still a meaningful audit
    event: it records the user's intent to terminate the session and
    keeps the tombstone shape uniform across live and expired rows
    (a row with `expires_at < now AND revoked_at IS NULL` would
    otherwise be indistinguishable from one that was simply forgotten).
    """
    # `AsyncSession.execute` is typed as returning the generic `Result`,
    # but for DML SQLAlchemy returns a `CursorResult` at runtime; cast so
    # `.rowcount` types correctly.
    result = cast(
        "CursorResult[None]",
        await session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(tz=UTC))
        ),
    )
    await session.flush()
    return result.rowcount
