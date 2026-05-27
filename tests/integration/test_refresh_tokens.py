"""Integration tests for the refresh-token service (story S02.3).

Drives the full `issue → verify → revoke` lifecycle against a real
Postgres via testcontainers, plus the negative paths:

- expired token (rows with past `expires_at`) → `ExpiredRefreshTokenError`,
- revoked token (rows with non-null `revoked_at`) → `RevokedRefreshTokenError`,
- isolated revoke (revoking one token leaves the user's other tokens
  intact),
- empty / non-ASCII raw tokens → `InvalidRefreshTokenError` (contract
  pin from S02.3 review).

Schema bootstrap mirrors `test_user_factory`: `Base.metadata.create_all`
on the test's transactional connection materialises both `users` and
`refresh_tokens` together (FK depends on `users.id`). Per-test rollback
keeps state from leaking.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.modules.auth.models import Base, RefreshToken, User
from backend.modules.auth.service.refresh_tokens import (
    ExpiredRefreshTokenError,
    InvalidRefreshTokenError,
    RevokedRefreshTokenError,
    hash_refresh_token,
    issue,
    revoke,
    verify,
)
from tests.factories.sqlalchemy import UserFactory

# Settings are pulled once at module load; tests that need a custom
# value (e.g. shorter TTL) build a fresh `Settings()` locally rather
# than mutating env vars + clearing a cache.
_settings = get_settings()


@pytest_asyncio.fixture(loop_scope="session")
async def auth_schema(db_session: AsyncSession) -> AsyncSession:
    """Create `users` + `refresh_tokens` on the test's transactional connection."""
    conn = await db_session.connection()
    await conn.run_sync(Base.metadata.create_all)
    return db_session


async def _make_user(session: AsyncSession, **overrides: object) -> User:
    def _create(sync_session: Session) -> User:
        UserFactory._meta.sqlalchemy_session = sync_session  # type: ignore[attr-defined]
        return cast(User, UserFactory(**overrides))

    return await session.run_sync(_create)


async def test_issue_returns_raw_token_and_persists_only_hash(
    auth_schema: AsyncSession,
) -> None:
    user = await _make_user(auth_schema, email="alice@example.com")

    raw = await issue(auth_schema, user.id, settings=_settings, device_label="laptop")

    assert isinstance(raw, str)
    # `secrets.token_urlsafe(32)` always returns 43 url-safe chars
    # (base64 of 32 bytes, no padding). Pin the exact length so a future
    # entropy bump (or accidental shrink) trips the test.
    assert len(raw) == 43

    record = (
        await auth_schema.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))
    ).scalar_one()
    # Raw value MUST NOT appear anywhere in the DB row.
    assert record.token_hash != raw
    assert record.token_hash == hash_refresh_token(raw, settings=_settings)
    assert record.revoked_at is None
    assert record.device_label == "laptop"
    delta = record.expires_at - record.issued_at
    assert abs(delta - timedelta(seconds=30 * 24 * 3600)) < timedelta(seconds=1)


async def test_issue_without_device_label_is_allowed(auth_schema: AsyncSession) -> None:
    user = await _make_user(auth_schema, email="bob@example.com")
    raw = await issue(auth_schema, user.id, settings=_settings)
    record = (
        await auth_schema.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))
    ).scalar_one()
    assert record.device_label is None
    assert record.token_hash == hash_refresh_token(raw, settings=_settings)


async def test_verify_returns_user_id_for_a_valid_token(auth_schema: AsyncSession) -> None:
    user = await _make_user(auth_schema, email="carol@example.com")
    raw = await issue(auth_schema, user.id, settings=_settings)

    assert await verify(auth_schema, raw, settings=_settings) == user.id


async def test_verify_rejects_unknown_token(auth_schema: AsyncSession) -> None:
    # No row was ever issued for this random string — must raise the base
    # `InvalidRefreshTokenError` (not the more specific Expired/Revoked).
    with pytest.raises(InvalidRefreshTokenError) as excinfo:
        await verify(auth_schema, "totally-not-a-real-token", settings=_settings)
    assert not isinstance(excinfo.value, ExpiredRefreshTokenError | RevokedRefreshTokenError)


async def test_verify_rejects_empty_raw_token(auth_schema: AsyncSession) -> None:
    """Contract: empty `raw_token` hashes to a value no row matches → Invalid.

    Pins behaviour so a future "validate raw input shape" refactor is a
    deliberate breaking choice rather than silent drift. Raised by the
    S02.3 multi-agent review.
    """
    with pytest.raises(InvalidRefreshTokenError) as excinfo:
        await verify(auth_schema, "", settings=_settings)
    assert not isinstance(excinfo.value, ExpiredRefreshTokenError | RevokedRefreshTokenError)


async def test_verify_rejects_non_ascii_raw_token(auth_schema: AsyncSession) -> None:
    """Contract: non-ASCII `raw_token` is utf-8-hashed; no row matches → Invalid."""
    with pytest.raises(InvalidRefreshTokenError) as excinfo:
        await verify(auth_schema, "café-🥐-token", settings=_settings)
    assert not isinstance(excinfo.value, ExpiredRefreshTokenError | RevokedRefreshTokenError)


async def test_verify_rejects_expired_token(auth_schema: AsyncSession) -> None:
    """A token whose `expires_at` is in the past raises `ExpiredRefreshTokenError`.

    Inserts directly rather than going through `issue()` so the test
    binds to the verify-time deadline check, not to a clock-fudging
    issuance path.
    """
    user = await _make_user(auth_schema, email="dave@example.com")
    raw = "expired-token-raw-value"
    now = datetime.now(tz=UTC)
    auth_schema.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw, settings=_settings),
            issued_at=now - timedelta(days=31),
            expires_at=now - timedelta(seconds=1),
        )
    )
    await auth_schema.flush()

    with pytest.raises(ExpiredRefreshTokenError):
        await verify(auth_schema, raw, settings=_settings)


async def test_verify_rejects_revoked_token(auth_schema: AsyncSession) -> None:
    """A revoked token raises `RevokedRefreshTokenError` even before it expires."""
    user = await _make_user(auth_schema, email="erin@example.com")
    raw = await issue(auth_schema, user.id, settings=_settings)

    await revoke(auth_schema, hash_refresh_token(raw, settings=_settings))

    with pytest.raises(RevokedRefreshTokenError):
        await verify(auth_schema, raw, settings=_settings)


async def test_revoked_check_fires_before_expired_check(auth_schema: AsyncSession) -> None:
    """If a token is both revoked AND expired, the revoked error wins.

    Upstream handlers can log a deliberate revocation differently from a
    natural expiration; pinning the order here prevents that distinction
    from silently flipping in a refactor.
    """
    user = await _make_user(auth_schema, email="frank@example.com")
    raw = "old-and-revoked"
    now = datetime.now(tz=UTC)
    auth_schema.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw, settings=_settings),
            issued_at=now - timedelta(days=31),
            expires_at=now - timedelta(days=1),
            revoked_at=now - timedelta(hours=1),
        )
    )
    await auth_schema.flush()

    with pytest.raises(RevokedRefreshTokenError):
        await verify(auth_schema, raw, settings=_settings)


async def test_revoke_does_not_affect_other_tokens_for_same_user(
    auth_schema: AsyncSession,
) -> None:
    """Revoking one of a user's tokens leaves the others usable.

    Models the real-world flow where a user logs out from a single
    device but other devices stay signed in.
    """
    user = await _make_user(auth_schema, email="gina@example.com")
    raw_a = await issue(auth_schema, user.id, settings=_settings, device_label="laptop")
    raw_b = await issue(auth_schema, user.id, settings=_settings, device_label="phone")

    await revoke(auth_schema, hash_refresh_token(raw_a, settings=_settings))

    with pytest.raises(RevokedRefreshTokenError):
        await verify(auth_schema, raw_a, settings=_settings)
    assert await verify(auth_schema, raw_b, settings=_settings) == user.id


async def test_revoke_is_idempotent(auth_schema: AsyncSession) -> None:
    """Revoking twice keeps the original `revoked_at` and never raises.

    Logout retries (network blip → client replay) must not error.
    """
    user = await _make_user(auth_schema, email="hank@example.com")
    raw = await issue(auth_schema, user.id, settings=_settings)
    token_hash = hash_refresh_token(raw, settings=_settings)

    await revoke(auth_schema, token_hash)
    first_revocation = (
        await auth_schema.execute(
            select(RefreshToken.revoked_at).where(RefreshToken.token_hash == token_hash)
        )
    ).scalar_one()
    assert first_revocation is not None

    await revoke(auth_schema, token_hash)
    second_revocation = (
        await auth_schema.execute(
            select(RefreshToken.revoked_at).where(RefreshToken.token_hash == token_hash)
        )
    ).scalar_one()
    # Idempotency: the second call must NOT overwrite the original timestamp.
    assert second_revocation == first_revocation


async def test_revoke_unknown_hash_is_silent(auth_schema: AsyncSession) -> None:
    # Logging out a token that doesn't exist (already cleaned up, replay,
    # forged value) must be a no-op, not a 500. We also assert no other
    # rows were touched so a future buggy WHERE clause (e.g. always-true)
    # cannot pass this test.
    user = await _make_user(auth_schema, email="ken@example.com")
    raw_live = await issue(auth_schema, user.id, settings=_settings, device_label="phone")
    pre_revoked_at = (
        await auth_schema.execute(
            select(RefreshToken.revoked_at).where(
                RefreshToken.token_hash == hash_refresh_token(raw_live, settings=_settings)
            )
        )
    ).scalar_one()
    assert pre_revoked_at is None

    rowcount = await revoke(
        auth_schema, hash_refresh_token("never-issued", settings=_settings)
    )

    assert rowcount == 0
    # The bystander token must still be live.
    post_revoked_at = (
        await auth_schema.execute(
            select(RefreshToken.revoked_at).where(
                RefreshToken.token_hash == hash_refresh_token(raw_live, settings=_settings)
            )
        )
    ).scalar_one()
    assert post_revoked_at is None


async def test_issue_respects_custom_ttl_setting(auth_schema: AsyncSession) -> None:
    # Build an ad-hoc `Settings` instead of mutating env vars + clearing
    # caches; the new kw-only `settings=` API makes this trivially safe.
    custom = Settings(jwt_secret=_settings.jwt_secret, refresh_token_ttl_seconds=60)
    user = await _make_user(auth_schema, email="ivy@example.com")

    await issue(auth_schema, user.id, settings=custom)

    record = (
        await auth_schema.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))
    ).scalar_one()
    assert abs((record.expires_at - record.issued_at) - timedelta(seconds=60)) < timedelta(
        seconds=1
    )


async def test_issued_tokens_are_unique_across_calls(auth_schema: AsyncSession) -> None:
    # `token_urlsafe(32)` collisions are astronomically improbable, but a
    # bug that returned a constant string would be caught here cheaply.
    user = await _make_user(auth_schema, email="judy@example.com")
    raws = {await issue(auth_schema, user.id, settings=_settings) for _ in range(5)}
    assert len(raws) == 5


async def test_issue_for_unknown_user_id_violates_fk(auth_schema: AsyncSession) -> None:
    # The FK to `users.id` must reject a refresh token bound to a UUID
    # that doesn't exist — guards against a future refactor that drops
    # the FK in favour of "soft" linking.
    with pytest.raises(IntegrityError):
        await issue(auth_schema, UUID(int=0), settings=_settings)


async def test_deleting_user_cascades_to_refresh_tokens(
    auth_schema: AsyncSession,
) -> None:
    """`ON DELETE CASCADE` removes a user's tokens when the user is deleted.

    Pins the FK action so a future migration that drops `ondelete=CASCADE`
    (or replaces it with `SET NULL`) is caught here — otherwise account
    deletion would leave orphaned refresh tokens unable to authenticate
    against any user.
    """
    user = await _make_user(auth_schema, email="lana@example.com")
    await issue(auth_schema, user.id, settings=_settings, device_label="laptop")
    await issue(auth_schema, user.id, settings=_settings, device_label="phone")
    pre_count = (
        await auth_schema.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))
    ).all()
    assert len(pre_count) == 2

    await auth_schema.execute(delete(User).where(User.id == user.id))
    await auth_schema.flush()

    remaining = (
        await auth_schema.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))
    ).all()
    assert remaining == []


async def test_verify_rejects_token_expiring_exactly_now(
    auth_schema: AsyncSession,
) -> None:
    """A token whose `expires_at` equals `now` is rejected (boundary `<=`).

    Locks the `expires_at <= now` semantics in `verify()`: if a refactor
    flipped it to `<`, a token at the exact deadline would still be
    accepted for one more instant — measurable in practice given clock
    skew between issuance and verification.
    """
    user = await _make_user(auth_schema, email="mia@example.com")
    raw = "deadline-exactly-now"
    now = datetime.now(tz=UTC)
    auth_schema.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw, settings=_settings),
            issued_at=now - timedelta(seconds=60),
            expires_at=now,
        )
    )
    await auth_schema.flush()

    with pytest.raises(ExpiredRefreshTokenError):
        await verify(auth_schema, raw, settings=_settings)


async def test_revoke_marks_already_expired_token(auth_schema: AsyncSession) -> None:
    """`revoke()` still flips `revoked_at` on a row whose `expires_at` is past.

    The `WHERE` clause filters on `revoked_at IS NULL` but NOT on
    `expires_at`, so revoking an expired-but-not-yet-revoked token
    succeeds. Pinning this prevents a future "skip expired rows"
    optimisation from making `revoke()` quietly miss tombstoning rows
    needed for audit trails.
    """
    user = await _make_user(auth_schema, email="nina@example.com")
    raw = "expired-but-still-revocable"
    now = datetime.now(tz=UTC)
    auth_schema.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw, settings=_settings),
            issued_at=now - timedelta(days=31),
            expires_at=now - timedelta(seconds=1),
        )
    )
    await auth_schema.flush()

    rowcount = await revoke(auth_schema, hash_refresh_token(raw, settings=_settings))

    assert rowcount == 1
    revoked_at = (
        await auth_schema.execute(
            select(RefreshToken.revoked_at).where(
                RefreshToken.token_hash == hash_refresh_token(raw, settings=_settings)
            )
        )
    ).scalar_one()
    assert revoked_at is not None


async def test_issue_starts_a_fresh_family(auth_schema: AsyncSession) -> None:
    """Each `issue()` for a fresh login is the root of a new rotation family.

    Pins `parent_id is None` and `family_id` distinct across two calls
    for the same user — otherwise the S02.4 rotation logic would think
    two independent logins were part of the same chain and invalidate
    both on a single replay.
    """
    user = await _make_user(auth_schema, email="oscar@example.com")
    raw_a = await issue(auth_schema, user.id, settings=_settings, device_label="laptop")
    raw_b = await issue(auth_schema, user.id, settings=_settings, device_label="phone")

    rows = (
        await auth_schema.execute(
            select(RefreshToken.token_hash, RefreshToken.family_id, RefreshToken.parent_id).where(
                RefreshToken.user_id == user.id
            )
        )
    ).all()
    by_hash = {row.token_hash: row for row in rows}
    a = by_hash[hash_refresh_token(raw_a, settings=_settings)]
    b = by_hash[hash_refresh_token(raw_b, settings=_settings)]

    assert a.parent_id is None
    assert b.parent_id is None
    assert a.family_id != b.family_id


async def test_parent_id_self_fk_rejects_unknown_uuid(
    auth_schema: AsyncSession,
) -> None:
    """The self-FK on `parent_id` rejects rows pointing at a non-existent token.

    Guards the S02.4 rotation contract: a refactor that drops the FK in
    favour of "soft" linking (string column) would let dangling
    `parent_id`s sneak in, silently breaking replay detection.
    """
    user = await _make_user(auth_schema, email="paige@example.com")
    now = datetime.now(tz=UTC)
    auth_schema.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token("orphan", settings=_settings),
            issued_at=now,
            expires_at=now + timedelta(seconds=60),
            parent_id=UUID(int=0),
            family_id=UUID(int=1),
        )
    )
    with pytest.raises(IntegrityError):
        await auth_schema.flush()
