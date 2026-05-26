"""Integration tests for the refresh-token service (story S02.3).

Drives the full `issue → verify → revoke` lifecycle against a real
Postgres via testcontainers, plus the negative paths:

- expired token (rows with past `expires_at`) → `ExpiredRefreshTokenError`,
- revoked token (rows with non-null `revoked_at`) → `RevokedRefreshTokenError`,
- isolated revoke (revoking one token leaves the user's other tokens
  intact).

Schema bootstrap mirrors `test_user_factory`: `Base.metadata.create_all`
on the test's transactional connection materialises both `users` and
`refresh_tokens` together (FK depends on `users.id`). Per-test rollback
keeps state from leaking.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.config import get_settings
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


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Re-read env-derived settings each test (e.g. when TTL is monkeypatched)."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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

    raw = await issue(auth_schema, user.id, device_label="laptop")

    assert isinstance(raw, str)
    assert len(raw) >= 32  # token_urlsafe(32) → ~43 chars; cheap floor

    record = (
        await auth_schema.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))
    ).scalar_one()
    # Raw value MUST NOT appear anywhere in the DB row.
    assert record.token_hash != raw
    assert record.token_hash == hash_refresh_token(raw)
    assert record.revoked_at is None
    assert record.device_label == "laptop"
    # `expires_at` is now + default TTL (30 days). Allow a generous skew.
    delta = record.expires_at - record.issued_at
    assert abs(delta - timedelta(seconds=30 * 24 * 3600)) < timedelta(seconds=5)


async def test_issue_without_device_label_is_allowed(auth_schema: AsyncSession) -> None:
    user = await _make_user(auth_schema, email="bob@example.com")
    raw = await issue(auth_schema, user.id)
    record = (
        await auth_schema.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))
    ).scalar_one()
    assert record.device_label is None
    assert record.token_hash == hash_refresh_token(raw)


async def test_verify_returns_user_id_for_a_valid_token(auth_schema: AsyncSession) -> None:
    user = await _make_user(auth_schema, email="carol@example.com")
    raw = await issue(auth_schema, user.id)

    assert await verify(auth_schema, raw) == user.id


async def test_verify_rejects_unknown_token(auth_schema: AsyncSession) -> None:
    # No row was ever issued for this random string — must raise the base
    # `InvalidRefreshTokenError` (not the more specific Expired/Revoked).
    with pytest.raises(InvalidRefreshTokenError) as excinfo:
        await verify(auth_schema, "totally-not-a-real-token")
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
            token_hash=hash_refresh_token(raw),
            issued_at=now - timedelta(days=31),
            expires_at=now - timedelta(seconds=1),
        )
    )
    await auth_schema.flush()

    with pytest.raises(ExpiredRefreshTokenError):
        await verify(auth_schema, raw)


async def test_verify_rejects_revoked_token(auth_schema: AsyncSession) -> None:
    """A revoked token raises `RevokedRefreshTokenError` even before it expires."""
    user = await _make_user(auth_schema, email="erin@example.com")
    raw = await issue(auth_schema, user.id)

    await revoke(auth_schema, hash_refresh_token(raw))

    with pytest.raises(RevokedRefreshTokenError):
        await verify(auth_schema, raw)


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
            token_hash=hash_refresh_token(raw),
            issued_at=now - timedelta(days=31),
            expires_at=now - timedelta(days=1),
            revoked_at=now - timedelta(hours=1),
        )
    )
    await auth_schema.flush()

    with pytest.raises(RevokedRefreshTokenError):
        await verify(auth_schema, raw)


async def test_revoke_does_not_affect_other_tokens_for_same_user(
    auth_schema: AsyncSession,
) -> None:
    """Revoking one of a user's tokens leaves the others usable.

    Models the real-world flow where a user logs out from a single
    device but other devices stay signed in.
    """
    user = await _make_user(auth_schema, email="gina@example.com")
    raw_a = await issue(auth_schema, user.id, device_label="laptop")
    raw_b = await issue(auth_schema, user.id, device_label="phone")

    await revoke(auth_schema, hash_refresh_token(raw_a))

    with pytest.raises(RevokedRefreshTokenError):
        await verify(auth_schema, raw_a)
    assert await verify(auth_schema, raw_b) == user.id


async def test_revoke_is_idempotent(auth_schema: AsyncSession) -> None:
    """Revoking twice keeps the original `revoked_at` and never raises.

    Logout retries (network blip → client replay) must not error.
    """
    user = await _make_user(auth_schema, email="hank@example.com")
    raw = await issue(auth_schema, user.id)
    token_hash = hash_refresh_token(raw)

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
    # forged value) must be a no-op, not a 500.
    await revoke(auth_schema, hash_refresh_token("never-issued"))


async def test_issue_respects_custom_ttl_setting(
    auth_schema: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REFRESH_TOKEN_TTL_SECONDS", "60")
    get_settings.cache_clear()
    user = await _make_user(auth_schema, email="ivy@example.com")

    await issue(auth_schema, user.id)

    record = (
        await auth_schema.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))
    ).scalar_one()
    assert abs((record.expires_at - record.issued_at) - timedelta(seconds=60)) < timedelta(
        seconds=2
    )


async def test_issued_tokens_are_unique_across_calls(auth_schema: AsyncSession) -> None:
    # `token_urlsafe(32)` collisions are astronomically improbable, but a
    # bug that returned a constant string would be caught here cheaply.
    user = await _make_user(auth_schema, email="judy@example.com")
    raws = {await issue(auth_schema, user.id) for _ in range(5)}
    assert len(raws) == 5


async def test_issue_for_unknown_user_id_violates_fk(auth_schema: AsyncSession) -> None:
    # The FK to `users.id` must reject a refresh token bound to a UUID
    # that doesn't exist — guards against a future refactor that drops
    # the FK in favour of "soft" linking.
    with pytest.raises(IntegrityError):
        await issue(auth_schema, UUID(int=0))
