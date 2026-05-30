"""Integration tests for the token-consumption service (S04.5, P04.5.2).

Drives `invitations.resolve_pending` (read) and `invitations.accept`
(atomic claim) against a real Postgres via `auth_schema`. Pins:

- the uniform `None` for every invalid case (unknown/expired/accepted/
  revoked) the route collapses to a single 410;
- the strict `expires_at > now` boundary (testable via the `now=` param);
- the conditional `UPDATE … RETURNING(Invitation)` actually marks the row
  and returns a populated entity (a pattern new to the repo);
- the no-commit/no-rollback contract (D2/D6) — the caller owns the txn;
- lookup by sha256 digest, not by raw token.

Per-test rollback (via `auth_schema`) keeps state from leaking.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.domain import UserRole
from backend.modules.auth.models import Invitation, User
from backend.modules.auth.service import invitations as invitation_service
from backend.modules.auth.service.invitations import hash_invitation_token

UserMaker = Callable[..., Awaitable[User]]


def _make_invitation(
    *,
    invited_by: User,
    email: str = "invitee@example.com",
    expires_in: timedelta = timedelta(days=7),
    accepted: bool = False,
    revoked: bool = False,
) -> tuple[Invitation, str]:
    """Build an (unpersisted) invitation plus its raw token.

    The S04.4 `_seed_invitation` helper does not expose the raw token (it
    hashes a throwaway string), but the accept flow needs the raw value the
    client would send — so this helper keeps the pair together.
    """
    now = datetime.now(tz=UTC)
    raw = secrets.token_urlsafe(32)
    inv = Invitation(
        email=email,
        invited_by=invited_by.id,
        invited_at=now,
        expires_at=now + expires_in,
        token_hash=hash_invitation_token(raw),
        accepted_at=now if accepted else None,
        revoked_at=now if revoked else None,
    )
    return inv, raw


async def _seed_invitation_token(
    session: AsyncSession, *, invited_by: User, **kwargs: object
) -> tuple[Invitation, str]:
    inv, raw = _make_invitation(invited_by=invited_by, **kwargs)  # type: ignore[arg-type]
    session.add(inv)
    await session.flush()
    return inv, raw


@pytest.fixture
async def admin(bound_user_factory: UserMaker) -> User:
    return await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)


# ---------------------------------------------------------------------------
# resolve_pending (GET path)
# ---------------------------------------------------------------------------


async def test_resolve_pending_valid_returns_row(auth_schema: AsyncSession, admin: User) -> None:
    inv, raw = await _seed_invitation_token(auth_schema, invited_by=admin)
    resolved = await invitation_service.resolve_pending(auth_schema, raw)
    assert resolved is not None
    assert resolved.id == inv.id


async def test_resolve_pending_unknown_returns_none(auth_schema: AsyncSession, admin: User) -> None:
    await _seed_invitation_token(auth_schema, invited_by=admin)
    assert await invitation_service.resolve_pending(auth_schema, "never-issued") is None


async def test_resolve_pending_expired_returns_none(auth_schema: AsyncSession, admin: User) -> None:
    _, raw = await _seed_invitation_token(
        auth_schema, invited_by=admin, expires_in=timedelta(days=-1)
    )
    assert await invitation_service.resolve_pending(auth_schema, raw) is None


async def test_resolve_pending_accepted_returns_none(
    auth_schema: AsyncSession, admin: User
) -> None:
    _, raw = await _seed_invitation_token(auth_schema, invited_by=admin, accepted=True)
    assert await invitation_service.resolve_pending(auth_schema, raw) is None


async def test_resolve_pending_revoked_returns_none(auth_schema: AsyncSession, admin: User) -> None:
    _, raw = await _seed_invitation_token(auth_schema, invited_by=admin, revoked=True)
    assert await invitation_service.resolve_pending(auth_schema, raw) is None


async def test_resolve_pending_does_not_consume(auth_schema: AsyncSession, admin: User) -> None:
    inv, raw = await _seed_invitation_token(auth_schema, invited_by=admin)
    await invitation_service.resolve_pending(auth_schema, raw)
    await auth_schema.refresh(inv)
    assert inv.accepted_at is None


async def test_resolve_pending_expiry_boundary_is_strict(
    auth_schema: AsyncSession, admin: User
) -> None:
    # `expires_at > now` is strict: at the exact expiry instant the row is
    # already invalid; one microsecond before, it is still pending.
    inv, raw = await _seed_invitation_token(auth_schema, invited_by=admin)
    expiry = inv.expires_at
    assert await invitation_service.resolve_pending(auth_schema, raw, now=expiry) is None
    just_before = expiry - timedelta(microseconds=1)
    assert await invitation_service.resolve_pending(auth_schema, raw, now=just_before) is not None


# ---------------------------------------------------------------------------
# accept (POST path)
# ---------------------------------------------------------------------------


async def test_accept_valid_marks_accepted(auth_schema: AsyncSession, admin: User) -> None:
    inv, raw = await _seed_invitation_token(auth_schema, invited_by=admin)
    claimed = await invitation_service.accept(auth_schema, raw)
    assert claimed is not None
    assert claimed.id == inv.id
    # `RETURNING(Invitation)` + `populate_existing` hands back the mutated
    # entity with `accepted_at` set; a fresh read confirms it persisted.
    assert claimed.accepted_at is not None
    await auth_schema.refresh(inv)
    assert inv.accepted_at is not None


async def test_accept_sequential_double_returns_none(
    auth_schema: AsyncSession, admin: User
) -> None:
    # Sequential window (not a true race): the second claim sees the row
    # already accepted → 0 rows → None. No 40001 here; the real race is
    # exercised at the route level.
    _, raw = await _seed_invitation_token(auth_schema, invited_by=admin)
    assert await invitation_service.accept(auth_schema, raw) is not None
    assert await invitation_service.accept(auth_schema, raw) is None


async def test_accept_expired_returns_none(auth_schema: AsyncSession, admin: User) -> None:
    _, raw = await _seed_invitation_token(
        auth_schema, invited_by=admin, expires_in=timedelta(days=-1)
    )
    assert await invitation_service.accept(auth_schema, raw) is None


async def test_accept_revoked_returns_none(auth_schema: AsyncSession, admin: User) -> None:
    _, raw = await _seed_invitation_token(auth_schema, invited_by=admin, revoked=True)
    assert await invitation_service.accept(auth_schema, raw) is None


async def test_accept_unknown_returns_none(auth_schema: AsyncSession, admin: User) -> None:
    await _seed_invitation_token(auth_schema, invited_by=admin)
    assert await invitation_service.accept(auth_schema, "never-issued") is None


async def test_accept_does_not_commit(auth_schema: AsyncSession, admin: User) -> None:
    # `accept` only flushes; rolling back the enclosing unit of work
    # discards the claim — proof the commit (and rollback) stay with the
    # caller (D2/D6).
    inv, raw = await _seed_invitation_token(auth_schema, invited_by=admin)
    inv_id = inv.id  # capture before `expire_all` so the query build is pure
    savepoint = await auth_schema.begin_nested()
    claimed = await invitation_service.accept(auth_schema, raw)
    assert claimed is not None
    await savepoint.rollback()

    auth_schema.expire_all()
    reread = (
        await auth_schema.execute(select(Invitation).where(Invitation.id == inv_id))
    ).scalar_one()
    assert reread.accepted_at is None


async def test_accept_lookup_is_by_digest_not_clear(auth_schema: AsyncSession, admin: User) -> None:
    # A token whose digest differs from the stored `token_hash` never
    # matches — the lookup is an equality on the sha256 digest, not on the
    # raw value.
    _, raw = await _seed_invitation_token(auth_schema, invited_by=admin)
    assert await invitation_service.accept(auth_schema, raw + "tampered") is None
