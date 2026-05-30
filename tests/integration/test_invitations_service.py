"""Integration tests for `service.invitations` (S04.3, P04.3.3).

Drives `create` / `regenerate` / `revoke` against a real Postgres so the
DB-level behaviour fires: the sha256 token persistence, the
`expires_at = invited_at + TTL` clock, the pending-only conditional
UPDATEs, and — on `committed_engine` — the no-commit contract (D6) and the
exact-double-`create` race that the partial unique index backstops (D9).

Rollback-isolated tests use `auth_schema` / `bound_user_factory`; the
real-commit tests use independent sessions on `committed_engine` and opt
into `_clean_committed_db` truncation.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.modules.auth.models import Invitation, User, UserRole
from backend.modules.auth.service.invitations import (
    INVITATION_TTL,
    DuplicatePendingInvitationError,
    InvitationNotFoundError,
    InvitationNotPendingError,
    create,
    hash_invitation_token,
    regenerate,
    revoke,
)

UserMaker = Callable[..., Awaitable[User]]


async def _admin(factory: UserMaker, *, email: str = "admin@example.com") -> uuid.UUID:
    admin = await factory(email=email, role=UserRole.ADMIN)
    return admin.id


async def _get(session: AsyncSession, invitation_id: uuid.UUID) -> Invitation:
    session.expire_all()  # Core UPDATEs bypass the identity map; force a read.
    return (
        await session.execute(select(Invitation).where(Invitation.id == invitation_id))
    ).scalar_one()


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


async def test_create_persists_sha256_and_normalised_email(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    by = await _admin(bound_user_factory)

    raw = await create(auth_schema, email="  New@Example.com  ", by_admin_id=by)

    assert isinstance(raw, str) and raw
    inv = (
        await auth_schema.execute(select(Invitation).where(Invitation.invited_by == by))
    ).scalar_one()
    assert inv.email == "new@example.com"
    assert inv.token_hash == hash_invitation_token(raw)
    assert inv.token_hash != raw  # the raw token is never persisted
    assert inv.invited_by == by
    assert inv.accepted_at is None
    assert inv.revoked_at is None


async def test_create_sets_expiry_to_invited_at_plus_ttl(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    by = await _admin(bound_user_factory)
    await create(auth_schema, email="ttl@example.com", by_admin_id=by)
    inv = (
        await auth_schema.execute(select(Invitation).where(Invitation.invited_by == by))
    ).scalar_one()
    assert inv.expires_at == inv.invited_at + INVITATION_TTL


async def test_create_duplicate_pending_is_rejected(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    by = await _admin(bound_user_factory)
    await create(auth_schema, email="dup@example.com", by_admin_id=by)

    with pytest.raises(DuplicatePendingInvitationError):
        await create(auth_schema, email="dup@example.com", by_admin_id=by)
    # Case-different spelling resolves to the same normalised email.
    with pytest.raises(DuplicatePendingInvitationError):
        await create(auth_schema, email="DUP@Example.com", by_admin_id=by)


async def test_create_after_revoke_is_allowed(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    by = await _admin(bound_user_factory)
    raw1 = await create(auth_schema, email="re@example.com", by_admin_id=by)
    inv = (
        await auth_schema.execute(select(Invitation).where(Invitation.invited_by == by))
    ).scalar_one()
    await revoke(auth_schema, inv.id)

    raw2 = await create(auth_schema, email="re@example.com", by_admin_id=by)
    assert raw2 != raw1


async def test_create_after_acceptance_is_allowed(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    by = await _admin(bound_user_factory)
    await create(auth_schema, email="acc@example.com", by_admin_id=by)
    inv = (
        await auth_schema.execute(select(Invitation).where(Invitation.invited_by == by))
    ).scalar_one()
    inv.accepted_at = datetime.now(tz=UTC)
    await auth_schema.flush()

    # The accepted row dropped out of the partial index → re-invite succeeds.
    await create(auth_schema, email="acc@example.com", by_admin_id=by)


async def test_create_unknown_actor_violates_fk(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    # Pre-check finds no pending row, then the INSERT's FK backstop fires.
    with pytest.raises(IntegrityError):
        await create(auth_schema, email="fk@example.com", by_admin_id=uuid.uuid4())


# ---------------------------------------------------------------------------
# regenerate
# ---------------------------------------------------------------------------


async def test_regenerate_replaces_token_and_resets_expiry(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    by = await _admin(bound_user_factory)
    raw1 = await create(auth_schema, email="regen@example.com", by_admin_id=by)
    before = (
        await auth_schema.execute(select(Invitation).where(Invitation.invited_by == by))
    ).scalar_one()
    inv_id = before.id
    old_hash = before.token_hash
    old_invited_at = before.invited_at
    old_expires_at = before.expires_at

    raw2 = await regenerate(auth_schema, inv_id)

    assert raw2 != raw1
    after = await _get(auth_schema, inv_id)
    assert after.token_hash == hash_invitation_token(raw2)
    assert after.token_hash != old_hash
    assert after.invited_at == old_invited_at  # original timestamp preserved
    assert after.expires_at > old_expires_at  # fresh window
    # The old link is dead: its hash is gone from the table.
    orphan = (
        await auth_schema.execute(select(Invitation).where(Invitation.token_hash == old_hash))
    ).first()
    assert orphan is None


async def test_regenerate_unknown_raises_not_found(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    await _admin(bound_user_factory)
    with pytest.raises(InvitationNotFoundError):
        await regenerate(auth_schema, uuid.uuid4())


@pytest.mark.parametrize("terminal", ["revoked", "accepted"])
async def test_regenerate_on_terminal_raises_not_pending(
    auth_schema: AsyncSession, bound_user_factory: UserMaker, terminal: str
) -> None:
    by = await _admin(bound_user_factory)
    await create(auth_schema, email="term@example.com", by_admin_id=by)
    inv = (
        await auth_schema.execute(select(Invitation).where(Invitation.invited_by == by))
    ).scalar_one()
    if terminal == "revoked":
        inv.revoked_at = datetime.now(tz=UTC)
    else:
        inv.accepted_at = datetime.now(tz=UTC)
    await auth_schema.flush()

    with pytest.raises(InvitationNotPendingError):
        await regenerate(auth_schema, inv.id)


# ---------------------------------------------------------------------------
# revoke
# ---------------------------------------------------------------------------


async def test_revoke_sets_revoked_at(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    by = await _admin(bound_user_factory)
    await create(auth_schema, email="rev@example.com", by_admin_id=by)
    inv = (
        await auth_schema.execute(select(Invitation).where(Invitation.invited_by == by))
    ).scalar_one()

    await revoke(auth_schema, inv.id)

    after = await _get(auth_schema, inv.id)
    assert after.revoked_at is not None


async def test_revoke_is_idempotent_on_revoked(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    by = await _admin(bound_user_factory)
    await create(auth_schema, email="idem@example.com", by_admin_id=by)
    inv = (
        await auth_schema.execute(select(Invitation).where(Invitation.invited_by == by))
    ).scalar_one()
    await revoke(auth_schema, inv.id)
    first = (await _get(auth_schema, inv.id)).revoked_at

    # Second revoke is a silent no-op: no error, timestamp unchanged.
    await revoke(auth_schema, inv.id)
    assert (await _get(auth_schema, inv.id)).revoked_at == first


async def test_revoke_unknown_raises_not_found(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    await _admin(bound_user_factory)
    with pytest.raises(InvitationNotFoundError):
        await revoke(auth_schema, uuid.uuid4())


async def test_revoke_accepted_raises_not_pending(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    by = await _admin(bound_user_factory)
    await create(auth_schema, email="revacc@example.com", by_admin_id=by)
    inv = (
        await auth_schema.execute(select(Invitation).where(Invitation.invited_by == by))
    ).scalar_one()
    inv.accepted_at = datetime.now(tz=UTC)
    await auth_schema.flush()

    with pytest.raises(InvitationNotPendingError):
        await revoke(auth_schema, inv.id)


# ---------------------------------------------------------------------------
# Real-commit tests (independent sessions on `committed_engine`)
# ---------------------------------------------------------------------------


async def _seed_admin(sm: async_sessionmaker[AsyncSession], *, email: str) -> uuid.UUID:
    async with sm() as session:
        admin = User(
            email=email,
            password_hash="x" * 60,
            display_name=email.split("@", 1)[0],
            role=UserRole.ADMIN,
        )
        session.add(admin)
        await session.flush()
        admin_id = admin.id
        await session.commit()
    return admin_id


@pytest.mark.usefixtures("_clean_committed_db")
async def test_create_does_not_commit(committed_engine: AsyncEngine) -> None:
    # D6: the service flushes but never commits — an independent session
    # must not see the invitation until the caller commits.
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    by = await _seed_admin(sm, email="admin@example.com")

    async with sm() as session:
        raw = await create(session, email="nocommit@example.com", by_admin_id=by)
        assert raw
        # Deliberately no commit — let the session close, rolling back.

    async with sm() as session:
        count = (await session.execute(select(func.count()).select_from(Invitation))).scalar_one()
        assert count == 0


@pytest.mark.usefixtures("_clean_committed_db")
async def test_concurrent_create_same_email_one_succeeds_one_conflicts(
    committed_engine: AsyncEngine,
) -> None:
    # D9: the partial unique index is the hard backstop for a true
    # concurrent double-create. Both pre-checks see no pending row (their
    # snapshots predate either commit), both INSERT; exactly one commits,
    # the loser takes a unique violation (IntegrityError).
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    by = await _seed_admin(sm, email="admin@example.com")

    barrier = asyncio.Barrier(2)

    async def attempt() -> str:
        async with sm() as session:
            # Pin the REPEATABLE READ snapshot before the barrier so both
            # transactions run their pre-check against the empty table.
            await session.execute(select(Invitation).limit(1))
            await barrier.wait()
            try:
                await create(session, email="race@example.com", by_admin_id=by)
                await session.commit()
                return "success"
            except (DuplicatePendingInvitationError, IntegrityError):
                await session.rollback()
                return "conflict"
            except Exception as exc:  # noqa: BLE001 — surface unexpected outcomes loudly
                await session.rollback()
                return f"other:{type(exc).__name__}"

    statuses = sorted(await asyncio.wait_for(asyncio.gather(attempt(), attempt()), timeout=10.0))
    assert statuses == ["conflict", "success"], f"unexpected race outcome: {statuses}"

    async with sm() as session:
        count = (await session.execute(select(func.count()).select_from(Invitation))).scalar_one()
        assert count == 1
