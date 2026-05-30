"""Integration tests for `promote_to_admin` (S04.1, P04.1.3).

Drives the role-transition service against a real Postgres so the parts
that only exist at the DB level actually fire: the conditional
`UPDATE … RETURNING` atomicity, the same-transaction audit write, the
actor-snapshot survival across deletion, and — on `committed_engine` —
the no-commit contract and the two concurrent-promotion race shapes,
mirroring `test_refresh_tokens_race.py`:

- an `asyncio.Event` pins the deterministic `rowcount=0` path (the loser
  opens its snapshot after the winner has committed `role='admin'`);
- an `asyncio.Barrier` pins the true-contention path that surfaces a
  `SerializationFailure` (SQLSTATE 40001) recovery.

The `auth_schema` / `db_session` tests use per-test rollback isolation;
the `committed_engine` tests use real commits + independent sessions and
opt into the `_clean_committed_db` truncation.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.modules.auth.domain import AdminAction, UserRole
from backend.modules.auth.models import AdminAuditLog, User
from backend.modules.auth.service.roles import (
    AlreadyAdminError,
    NotAuthorizedError,
    UserNotFoundError,
    promote_to_admin,
)

UserMaker = Callable[..., Awaitable[User]]


async def _audit_rows(session: AsyncSession) -> list[AdminAuditLog]:
    return list((await session.execute(select(AdminAuditLog))).scalars().all())


# ---------------------------------------------------------------------------
# Rollback-isolated tests (single transactional session)
# ---------------------------------------------------------------------------


async def test_promote_member_to_admin_happy_path(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    actor = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    target = await bound_user_factory(email="member@example.com", role=UserRole.MEMBER)
    actor_id, target_id = actor.id, target.id

    promoted = await promote_to_admin(auth_schema, user_id=target_id, by_admin_id=actor_id)

    # Returned object reflects the in-transaction UPDATE, not a stale
    # identity-map snapshot (the target was pre-loaded in this session).
    assert promoted.id == target_id
    assert promoted.role == UserRole.ADMIN

    # Force a real DB read of the role to prove the UPDATE persisted (within
    # the transaction), not just the refreshed in-memory attribute.
    auth_schema.expire_all()
    db_role = (
        await auth_schema.execute(select(User.role).where(User.id == target_id))
    ).scalar_one()
    assert db_role == UserRole.ADMIN

    # Exactly one audit row, same transaction, with the actor snapshot.
    rows = await _audit_rows(auth_schema)
    assert len(rows) == 1
    log = rows[0]
    assert log.action == AdminAction.USER_PROMOTED.value
    assert log.actor_user_id == actor_id
    assert log.target_user_id == target_id
    assert log.actor_email == "admin@example.com"
    assert log.actor_label == "admin@example.com (admin)"
    assert log.event_metadata == {"old_role": "member", "new_role": "admin"}


async def test_promote_already_admin_raises_without_audit(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    actor = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    target = await bound_user_factory(email="already@example.com", role=UserRole.ADMIN)

    with pytest.raises(AlreadyAdminError):
        await promote_to_admin(auth_schema, user_id=target.id, by_admin_id=actor.id)

    assert await _audit_rows(auth_schema) == []


async def test_promote_unknown_user_raises_without_audit(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    actor = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)

    with pytest.raises(UserNotFoundError):
        await promote_to_admin(auth_schema, user_id=uuid4(), by_admin_id=actor.id)

    assert await _audit_rows(auth_schema) == []


async def test_promote_self_raises_already_admin(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    # `by_admin_id == user_id`: the actor guard passes (active admin), the
    # conditional UPDATE (`WHERE role='member'`) matches nothing, so
    # re-resolution surfaces `AlreadyAdminError`. No audit row is written.
    actor = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)

    with pytest.raises(AlreadyAdminError):
        await promote_to_admin(auth_schema, user_id=actor.id, by_admin_id=actor.id)

    assert await _audit_rows(auth_schema) == []


@pytest.mark.parametrize(
    "actor_kind",
    ["unknown", "member", "disabled_admin"],
)
async def test_promote_by_non_admin_raises_without_audit_or_mutation(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
    actor_kind: str,
) -> None:
    target = await bound_user_factory(email="member@example.com", role=UserRole.MEMBER)
    target_id = target.id

    if actor_kind == "unknown":
        by_admin_id = uuid4()
    elif actor_kind == "member":
        actor = await bound_user_factory(email="plain@example.com", role=UserRole.MEMBER)
        by_admin_id = actor.id
    else:  # disabled_admin
        actor = await bound_user_factory(
            email="frozen-admin@example.com",
            role=UserRole.ADMIN,
            disabled_at=datetime.now(tz=UTC),
        )
        by_admin_id = actor.id

    with pytest.raises(NotAuthorizedError):
        await promote_to_admin(auth_schema, user_id=target_id, by_admin_id=by_admin_id)

    # The non-admin produced neither a mutation nor an audit row.
    assert await _audit_rows(auth_schema) == []
    auth_schema.expire_all()
    db_role = (
        await auth_schema.execute(select(User.role).where(User.id == target_id))
    ).scalar_one()
    assert db_role == UserRole.MEMBER


async def test_promote_disabled_member_is_allowed(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    # Promotion filters on `role='member'` only — a disabled target is still
    # promotable by design (re-enabling is a separate concern). This test
    # pins that documented behaviour so a future filter change is deliberate.
    actor = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    target = await bound_user_factory(
        email="disabled@example.com",
        role=UserRole.MEMBER,
        disabled_at=datetime.now(tz=UTC),
    )

    promoted = await promote_to_admin(auth_schema, user_id=target.id, by_admin_id=actor.id)

    assert promoted.role == UserRole.ADMIN
    assert len(await _audit_rows(auth_schema)) == 1


async def test_promotion_audit_survives_actor_deletion(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    # The `user_promoted` row must stay meaningful after the acting admin's
    # account is deleted: FK nulled, identity snapshot preserved.
    actor = await bound_user_factory(email="rogue-admin@example.com", role=UserRole.ADMIN)
    target = await bound_user_factory(email="member@example.com", role=UserRole.MEMBER)
    actor_id = actor.id

    await promote_to_admin(auth_schema, user_id=target.id, by_admin_id=actor_id)

    await auth_schema.execute(delete(User).where(User.id == actor_id))
    await auth_schema.flush()
    auth_schema.expire_all()

    surviving = (
        await auth_schema.execute(
            select(AdminAuditLog).where(AdminAuditLog.action == AdminAction.USER_PROMOTED.value)
        )
    ).scalar_one()
    assert surviving.actor_user_id is None  # FK nulled by ON DELETE SET NULL...
    assert surviving.actor_email == "rogue-admin@example.com"  # ...snapshot survives.


# ---------------------------------------------------------------------------
# Real-commit tests (independent sessions on `committed_engine`)
# ---------------------------------------------------------------------------


async def _seed_user(
    sm: async_sessionmaker[AsyncSession],
    *,
    email: str,
    role: UserRole,
) -> UUID:
    async with sm() as session:
        user = User(
            email=email,
            password_hash="x" * 60,
            display_name=email.split("@", 1)[0],
            role=role,
        )
        session.add(user)
        await session.flush()
        user_id = user.id
        await session.commit()
    return user_id


@pytest.mark.usefixtures("_clean_committed_db")
async def test_promote_does_not_commit(committed_engine: AsyncEngine) -> None:
    # The service flushes but never commits: a separate session must not see
    # the promotion until the caller commits. Modelled on ADR 0015's
    # "pinning via a separate session" rule.
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    actor_id = await _seed_user(sm, email="admin@example.com", role=UserRole.ADMIN)
    target_id = await _seed_user(sm, email="member@example.com", role=UserRole.MEMBER)

    async with sm() as session:
        promoted = await promote_to_admin(session, user_id=target_id, by_admin_id=actor_id)
        assert promoted.role == UserRole.ADMIN
        # Deliberately no commit — let the session close, rolling back.

    # A third, independent session sees neither the role change nor an audit row.
    async with sm() as session:
        db_role = (
            await session.execute(select(User.role).where(User.id == target_id))
        ).scalar_one()
        assert db_role == UserRole.MEMBER
        audit_count = (
            await session.execute(select(func.count()).select_from(AdminAuditLog))
        ).scalar_one()
        assert audit_count == 0


@pytest.mark.usefixtures("_clean_committed_db")
async def test_promote_concurrent_race_with_barrier_yields_one_success_one_audit(
    committed_engine: AsyncEngine,
) -> None:
    # True-contention shape: an `asyncio.Barrier` forces both transactions to
    # open their REPEATABLE READ snapshot first, then issue the UPDATE row
    # lock simultaneously. Postgres aborts the loser with SerializationFailure
    # (SQLSTATE 40001), which `promote_to_admin` recovers into
    # `AlreadyAdminError`. Converges to exactly one success / one
    # `AlreadyAdminError` / one audit row. The `rowcount=0` sequential path is
    # pinned separately below via `asyncio.Event`.
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    actor_id = await _seed_user(sm, email="admin@example.com", role=UserRole.ADMIN)
    target_id = await _seed_user(sm, email="member@example.com", role=UserRole.MEMBER)

    barrier = asyncio.Barrier(2)

    async def attempt() -> str:
        async with sm() as session:
            # Materialise the REPEATABLE READ snapshot before the barrier so
            # both transactions contend on the UPDATE row lock together.
            await session.execute(select(User).limit(1))
            await barrier.wait()
            try:
                await promote_to_admin(session, user_id=target_id, by_admin_id=actor_id)
                await session.commit()
                return "success"
            except AlreadyAdminError:
                await session.rollback()
                return "already_admin"
            except Exception as exc:  # noqa: BLE001 — surface unexpected outcomes loudly
                await session.rollback()
                return f"other:{type(exc).__name__}"

    statuses = sorted(await asyncio.wait_for(asyncio.gather(attempt(), attempt()), timeout=10.0))
    assert statuses == ["already_admin", "success"], f"unexpected race outcome: {statuses}"

    # Final state from an independent session: promoted, with one audit row.
    async with sm() as session:
        db_role = (
            await session.execute(select(User.role).where(User.id == target_id))
        ).scalar_one()
        assert db_role == UserRole.ADMIN
        audit_count = (
            await session.execute(select(func.count()).select_from(AdminAuditLog))
        ).scalar_one()
        assert audit_count == 1


@pytest.mark.usefixtures("_clean_committed_db")
async def test_promote_loser_after_commit_yields_already_admin_one_audit(
    committed_engine: AsyncEngine,
) -> None:
    # Sequential shape: an `asyncio.Event` makes the loser open its REPEATABLE
    # READ snapshot strictly AFTER the winner has committed `role='admin'`, so
    # its conditional `UPDATE … WHERE role='member'` matches zero rows and
    # `_raise_for_unpromotable` re-resolves to `AlreadyAdminError` — the
    # deterministic `rowcount=0` path, with no SerializationFailure involved
    # (the barrier test above pins the 40001 contention path). Together the
    # two tests cover both concurrent-loser branches of `promote_to_admin`.
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    actor_id = await _seed_user(sm, email="admin@example.com", role=UserRole.ADMIN)
    target_id = await _seed_user(sm, email="member@example.com", role=UserRole.MEMBER)

    winner_committed = asyncio.Event()

    async def winner() -> str:
        async with sm() as session:
            try:
                await promote_to_admin(session, user_id=target_id, by_admin_id=actor_id)
                await session.commit()
                return "success"
            except Exception as exc:  # noqa: BLE001 — surface, never hang
                await session.rollback()
                return f"winner-failed:{type(exc).__name__}"
            finally:
                # Unblock the loser even on failure so `gather()` cannot hang.
                winner_committed.set()

    async def loser() -> str:
        await winner_committed.wait()
        async with sm() as session:
            # First statement opens the snapshot — after the winner's commit,
            # so the row already reads `role='admin'` and the UPDATE no-ops.
            try:
                await promote_to_admin(session, user_id=target_id, by_admin_id=actor_id)
                await session.commit()
                return "success"
            except AlreadyAdminError:
                await session.rollback()
                return "already_admin"
            except Exception as exc:  # noqa: BLE001 — surface unexpected outcomes loudly
                await session.rollback()
                return f"other:{type(exc).__name__}"

    statuses = await asyncio.wait_for(asyncio.gather(winner(), loser()), timeout=10.0)
    # Order is deterministic by construction: winner first, loser second.
    assert statuses == ["success", "already_admin"], f"unexpected race outcome: {statuses}"

    # Final state from an independent session: promoted, with one audit row
    # (the loser's no-op wrote nothing).
    async with sm() as session:
        db_role = (
            await session.execute(select(User.role).where(User.id == target_id))
        ).scalar_one()
        assert db_role == UserRole.ADMIN
        audit_count = (
            await session.execute(select(func.count()).select_from(AdminAuditLog))
        ).scalar_one()
        assert audit_count == 1
