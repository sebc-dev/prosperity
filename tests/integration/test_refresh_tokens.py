"""Integration tests for the refresh-token service (stories S02.3 + S02.4).

Drives the full `issue → verify → rotate → revoke` lifecycle against a
real Postgres via testcontainers, plus the negative paths:

- expired token (rows with past `expires_at`) → `ExpiredRefreshTokenError`,
- revoked token (rows with non-null `revoked_at`) → `RevokedRefreshTokenError`,
- isolated revoke (revoking one token leaves the user's other tokens
  intact),
- rotation happy path + replay detection → family-wide invalidation,
- empty / non-ASCII raw tokens → `InvalidRefreshTokenError`.

Per-test rollback (via `db_session`) keeps state from leaking.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings, get_settings
from backend.modules.auth.models import RefreshToken, User
from backend.modules.auth.service.refresh_tokens import (
    ExpiredRefreshTokenError,
    InvalidRefreshTokenError,
    RevokedRefreshTokenError,
    hash_refresh_token,
    issue,
    revoke,
    rotate,
    verify,
)

# `get_settings()` is cached; tests that do not mutate env vars can call
# it once at module load. Tests that need to inspect a custom TTL build
# a fresh `Settings` locally (see `test_issue_respects_custom_ttl_setting`).
_settings = get_settings()


UserMaker = Callable[..., Awaitable[User]]


async def test_issue_returns_raw_token_and_persists_only_hash(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="alice@example.com")

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
    # `expires_at` is now + default TTL (30 days). `issued_at` and the
    # local `now` are both set in Python within the same call so a
    # second of skew is generous.
    delta = record.expires_at - record.issued_at
    assert abs(delta - timedelta(seconds=30 * 24 * 3600)) < timedelta(seconds=1)


async def test_issue_without_device_label_is_allowed(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="bob@example.com")
    raw = await issue(auth_schema, user.id, settings=_settings)
    record = (
        await auth_schema.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))
    ).scalar_one()
    assert record.device_label is None
    assert record.token_hash == hash_refresh_token(raw, settings=_settings)


async def test_verify_returns_user_id_for_a_valid_token(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="carol@example.com")
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
    deliberate breaking choice rather than silent drift.
    """
    with pytest.raises(InvalidRefreshTokenError) as excinfo:
        await verify(auth_schema, "", settings=_settings)
    assert not isinstance(excinfo.value, ExpiredRefreshTokenError | RevokedRefreshTokenError)


async def test_verify_rejects_non_ascii_raw_token(auth_schema: AsyncSession) -> None:
    """Contract: non-ASCII `raw_token` is utf-8-hashed; no row matches → Invalid."""
    with pytest.raises(InvalidRefreshTokenError) as excinfo:
        await verify(auth_schema, "café-🥐-token", settings=_settings)
    assert not isinstance(excinfo.value, ExpiredRefreshTokenError | RevokedRefreshTokenError)


async def test_verify_rejects_expired_token(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="dave@example.com")
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


async def test_verify_rejects_revoked_token(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="erin@example.com")
    raw = await issue(auth_schema, user.id, settings=_settings)

    await revoke(auth_schema, hash_refresh_token(raw, settings=_settings))

    with pytest.raises(RevokedRefreshTokenError):
        await verify(auth_schema, raw, settings=_settings)


async def test_revoked_check_fires_before_expired_check(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="frank@example.com")
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
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="gina@example.com")
    raw_a = await issue(auth_schema, user.id, settings=_settings, device_label="laptop")
    raw_b = await issue(auth_schema, user.id, settings=_settings, device_label="phone")

    await revoke(auth_schema, hash_refresh_token(raw_a, settings=_settings))

    with pytest.raises(RevokedRefreshTokenError):
        await verify(auth_schema, raw_a, settings=_settings)
    assert await verify(auth_schema, raw_b, settings=_settings) == user.id


async def test_revoke_is_idempotent(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="hank@example.com")
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
    assert second_revocation == first_revocation


async def test_revoke_unknown_hash_is_silent(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="ken@example.com")
    raw_live = await issue(auth_schema, user.id, settings=_settings, device_label="phone")
    pre_revoked_at = (
        await auth_schema.execute(
            select(RefreshToken.revoked_at).where(
                RefreshToken.token_hash == hash_refresh_token(raw_live, settings=_settings)
            )
        )
    ).scalar_one()
    assert pre_revoked_at is None

    rowcount = await revoke(auth_schema, hash_refresh_token("never-issued", settings=_settings))

    assert rowcount == 0
    post_revoked_at = (
        await auth_schema.execute(
            select(RefreshToken.revoked_at).where(
                RefreshToken.token_hash == hash_refresh_token(raw_live, settings=_settings)
            )
        )
    ).scalar_one()
    assert post_revoked_at is None


async def test_issue_respects_custom_ttl_setting(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    custom = Settings(
        jwt_secret=_settings.jwt_secret,
        refresh_token_ttl_seconds=60,
    )
    user = await bound_user_factory(email="ivy@example.com")

    await issue(auth_schema, user.id, settings=custom)

    record = (
        await auth_schema.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))
    ).scalar_one()
    assert abs((record.expires_at - record.issued_at) - timedelta(seconds=60)) < timedelta(
        seconds=1
    )


async def test_issued_tokens_are_unique_across_calls(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="judy@example.com")
    raws = {await issue(auth_schema, user.id, settings=_settings) for _ in range(5)}
    assert len(raws) == 5


async def test_issue_for_unknown_user_id_violates_fk(auth_schema: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await issue(auth_schema, UUID(int=0), settings=_settings)


async def test_deleting_user_cascades_to_refresh_tokens(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="lana@example.com")
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
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="mia@example.com")
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


async def test_revoke_marks_already_expired_token(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="nina@example.com")
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


async def test_issue_starts_a_fresh_family(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="oscar@example.com")
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
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="paige@example.com")
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


# -----------------------------------------------------------------------------
# rotate() — added in S02.4 (P02.4.2)
# -----------------------------------------------------------------------------


async def test_rotate_unknown_token_raises_invalid(auth_schema: AsyncSession) -> None:
    with pytest.raises(InvalidRefreshTokenError) as excinfo:
        await rotate(auth_schema, "never-issued", settings=_settings)
    assert not isinstance(excinfo.value, ExpiredRefreshTokenError | RevokedRefreshTokenError)


async def test_rotate_empty_raw_token_raises_invalid(auth_schema: AsyncSession) -> None:
    with pytest.raises(InvalidRefreshTokenError) as excinfo:
        await rotate(auth_schema, "", settings=_settings)
    assert not isinstance(excinfo.value, ExpiredRefreshTokenError | RevokedRefreshTokenError)


async def test_rotate_non_ascii_raw_token_raises_invalid(auth_schema: AsyncSession) -> None:
    with pytest.raises(InvalidRefreshTokenError) as excinfo:
        await rotate(auth_schema, "café-🥐-token", settings=_settings)
    assert not isinstance(excinfo.value, ExpiredRefreshTokenError | RevokedRefreshTokenError)


async def test_rotate_expired_token_raises_expired(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="quinn@example.com")
    raw = "expired-rotate-target"
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
        await rotate(auth_schema, raw, settings=_settings)


async def test_rotate_revoked_token_raises_and_invalidates_family(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    """Replay detection: presenting a revoked token nukes the whole family.

    Sets up T0 → T1 → T2 (each parent_id chained, sharing `family_id`),
    revokes T1 manually, then rotates(T1). The call must raise
    `RevokedRefreshTokenError` AND mark every live row in the family as
    revoked (T0 and T2 included).
    """
    user = await bound_user_factory(email="rita@example.com")
    raw_t0 = await issue(auth_schema, user.id, settings=_settings, device_label="laptop")
    t0 = (
        await auth_schema.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_refresh_token(raw_t0, settings=_settings)
            )
        )
    ).scalar_one()
    family_id = t0.family_id

    # Manually craft T1 and T2 in the same family so we can pin the raw values.
    now = datetime.now(tz=UTC)
    raw_t1 = "rotation-child-one"
    raw_t2 = "rotation-child-two"
    t1 = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_t1, settings=_settings),
        issued_at=now,
        expires_at=now + timedelta(seconds=3600),
        family_id=family_id,
        parent_id=t0.id,
    )
    auth_schema.add(t1)
    await auth_schema.flush()
    t2 = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_t2, settings=_settings),
        issued_at=now,
        expires_at=now + timedelta(seconds=3600),
        family_id=family_id,
        parent_id=t1.id,
    )
    auth_schema.add(t2)
    await auth_schema.flush()

    # Revoke T1 directly (skipping rotate's path), then attempt to rotate it
    # again — that's a replay.
    await revoke(auth_schema, hash_refresh_token(raw_t1, settings=_settings))

    with pytest.raises(RevokedRefreshTokenError):
        await rotate(auth_schema, raw_t1, settings=_settings)

    # All three rows in this family must now be revoked.
    rows = (
        await auth_schema.execute(
            select(RefreshToken.token_hash, RefreshToken.revoked_at).where(
                RefreshToken.family_id == family_id
            )
        )
    ).all()
    assert all(row.revoked_at is not None for row in rows)
    assert len(rows) == 3


async def test_rotate_happy_path_preserves_family_and_sets_parent(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="sasha@example.com")
    raw_t0 = await issue(auth_schema, user.id, settings=_settings, device_label="laptop")
    t0_before = (
        await auth_schema.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_refresh_token(raw_t0, settings=_settings)
            )
        )
    ).scalar_one()
    family_id = t0_before.family_id
    t0_id = t0_before.id

    returned_user_id, raw_new = await rotate(auth_schema, raw_t0, settings=_settings)

    assert returned_user_id == user.id
    assert raw_new != raw_t0

    # T0 must now be revoked.
    t0_after = (
        await auth_schema.execute(
            select(RefreshToken).where(RefreshToken.id == t0_id)
        )
    ).scalar_one()
    assert t0_after.revoked_at is not None

    # The new token sits in the same family, with parent_id = T0.id.
    new_record = (
        await auth_schema.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_refresh_token(raw_new, settings=_settings)
            )
        )
    ).scalar_one()
    assert new_record.family_id == family_id
    assert new_record.parent_id == t0_id
    assert new_record.revoked_at is None
