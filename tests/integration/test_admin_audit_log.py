"""Integration tests for the admin audit-log service (S04.2, P04.2.2).

Drives `log_admin_action` against a real Postgres via `auth_schema` so
the parts that only exist at the DB level actually fire:

- the `metadata` column mapping (the model attribute is `event_metadata`
  because `metadata` is reserved by SQLAlchemy — a raw `SELECT metadata`
  proves the on-disk name),
- the `created_at` server default,
- the two `ON DELETE SET NULL` FKs (a log must outlive the actor/target
  it references; the identity snapshot survives the null-out),
- the append-only trigger (`create_all` installs it via the model's DDL
  events, mirroring migration 0005),
- flush-without-commit (a rollback discards the row — the helper defers
  the commit to the caller).

Per-test rollback (via `auth_schema` / `db_session`) keeps state from
leaking.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from uuid import UUID

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.domain import AdminAction, UserRole
from backend.modules.auth.models import AdminAuditLog, User
from backend.modules.auth.service.audit import log_admin_action

UserMaker = Callable[..., Awaitable[User]]


async def test_log_admin_action_round_trips_by_action(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    actor = await bound_user_factory(email="admin@example.com")
    target = await bound_user_factory(email="promoted@example.com")
    # Capture ids before `expire_all` — expiring the actor/target too would
    # make a later sync attribute read trigger an illegal lazy DB load.
    actor_id, target_id = actor.id, target.id

    log = await log_admin_action(
        auth_schema,
        action=AdminAction.USER_PROMOTED,
        by=actor_id,
        target=target_id,
        metadata={"old_role": "member", "new_role": "admin"},
    )
    log_id = log.id
    assert log_id is not None

    # Force a real DB read rather than an identity-map hit.
    auth_schema.expire_all()
    fetched = (
        await auth_schema.execute(
            select(AdminAuditLog).where(AdminAuditLog.action == AdminAction.USER_PROMOTED.value)
        )
    ).scalar_one()

    assert fetched.id == log_id
    assert fetched.action == "user_promoted"
    assert fetched.actor_user_id == actor_id
    assert fetched.target_user_id == target_id
    assert fetched.event_metadata == {"old_role": "member", "new_role": "admin"}


async def test_log_admin_action_snapshots_actor_and_target_identity(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    actor = await bound_user_factory(email="acting-admin@example.com", role=UserRole.ADMIN)
    target = await bound_user_factory(email="victim@example.com")

    log = await log_admin_action(
        auth_schema,
        action=AdminAction.USER_DISABLED,
        by=actor.id,
        target=target.id,
    )

    # The snapshot is captured by the helper, not the caller.
    assert log.actor_email == "acting-admin@example.com"
    assert log.actor_label == "acting-admin@example.com (admin)"
    assert log.target_email == "victim@example.com"


async def test_log_admin_action_persists_under_metadata_column_name(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    actor = await bound_user_factory(email="admin@example.com")

    log = await log_admin_action(
        auth_schema,
        action=AdminAction.INVITE_SENT,
        by=actor.id,
        metadata={"invitation_id": "abc-123"},
    )

    # A raw `SELECT metadata` would raise UndefinedColumn if the column
    # were named `event_metadata`; selecting it successfully proves the
    # on-disk name survived the reserved-attribute workaround. asyncpg's
    # JSONB codec hands back a deserialised dict.
    raw = (
        await auth_schema.execute(
            text("SELECT metadata FROM admin_audit_logs WHERE id = :id"), {"id": log.id}
        )
    ).scalar_one()
    assert raw == {"invitation_id": "abc-123"}


async def test_log_admin_action_preserves_nested_metadata(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    actor = await bound_user_factory(email="admin@example.com")
    payload = {
        "invitation_id": "abc-123",
        "nested": {"roles": ["member", "admin"], "active": True},
        "count": 3,
    }

    log = await log_admin_action(
        auth_schema,
        action=AdminAction.INVITE_REGENERATED,
        by=actor.id,
        metadata=payload,
    )

    # `refresh` reloads from the DB (async-safe), proving the JSONB
    # round-trips with nested structure rather than echoing the in-memory
    # dict held since the flush.
    await auth_schema.refresh(log)
    assert log.event_metadata == payload


async def test_log_admin_action_allows_null_target_and_metadata(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    actor = await bound_user_factory(email="admin@example.com")

    log = await log_admin_action(
        auth_schema,
        action=AdminAction.TWOFA_RESET_VIA_DB,
        by=actor.id,
    )

    assert log.target_user_id is None
    assert log.target_email is None
    assert log.event_metadata is None


async def test_log_admin_action_fills_created_at_from_server_default(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    actor = await bound_user_factory(email="admin@example.com")

    log = await log_admin_action(
        auth_schema,
        action=AdminAction.INVITE_ACCEPTED,
        by=actor.id,
    )

    assert isinstance(log.created_at, datetime)
    # `server_default=func.now()` yields a timezone-aware timestamp.
    assert log.created_at.tzinfo is not None


async def test_deleting_actor_nulls_fk_but_keeps_identity_snapshot(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    actor = await bound_user_factory(email="rogue-admin@example.com")
    actor_id = actor.id
    log = await log_admin_action(
        auth_schema,
        action=AdminAction.USER_PROMOTED,
        by=actor_id,
    )
    log_id = log.id

    await auth_schema.execute(delete(User).where(User.id == actor_id))
    await auth_schema.flush()
    auth_schema.expire_all()

    surviving = (
        await auth_schema.execute(select(AdminAuditLog).where(AdminAuditLog.id == log_id))
    ).scalar_one()
    # The row survives (audit must outlive the account)...
    assert surviving.actor_user_id is None  # ...with the FK nulled...
    assert surviving.actor_email == "rogue-admin@example.com"  # ...but identity preserved.


async def test_deleting_target_nulls_fk_but_keeps_email_snapshot(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    actor = await bound_user_factory(email="admin@example.com")
    target = await bound_user_factory(email="deleted-user@example.com")
    target_id = target.id
    log = await log_admin_action(
        auth_schema,
        action=AdminAction.USER_DISABLED,
        by=actor.id,
        target=target_id,
    )
    log_id = log.id

    await auth_schema.execute(delete(User).where(User.id == target_id))
    await auth_schema.flush()
    auth_schema.expire_all()

    surviving = (
        await auth_schema.execute(select(AdminAuditLog).where(AdminAuditLog.id == log_id))
    ).scalar_one()
    assert surviving.target_user_id is None
    assert surviving.target_email == "deleted-user@example.com"


async def test_log_admin_action_does_not_commit(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    actor = await bound_user_factory(email="admin@example.com")

    savepoint = await auth_schema.begin_nested()
    await log_admin_action(
        auth_schema,
        action=AdminAction.INVITE_SENT,
        by=actor.id,
    )
    await savepoint.rollback()

    # The helper only flushed; rolling back the enclosing unit of work
    # discards the row — proof the commit is the caller's responsibility.
    remaining = (await auth_schema.execute(select(AdminAuditLog))).all()
    assert remaining == []


async def test_log_admin_action_unknown_actor_violates_fk(
    auth_schema: AsyncSession,
) -> None:
    with pytest.raises(IntegrityError):
        await log_admin_action(
            auth_schema,
            action=AdminAction.USER_PROMOTED,
            by=UUID(int=0),
        )


async def test_admin_audit_logs_rejects_update(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    actor = await bound_user_factory(email="admin@example.com")
    log = await log_admin_action(
        auth_schema,
        action=AdminAction.INVITE_SENT,
        by=actor.id,
    )

    # The append-only trigger raises on any row UPDATE.
    with pytest.raises(DBAPIError):
        await auth_schema.execute(
            update(AdminAuditLog)
            .where(AdminAuditLog.id == log.id)
            .values(action=AdminAction.INVITE_REVOKED.value)
        )


async def test_admin_audit_logs_rejects_delete(
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    actor = await bound_user_factory(email="admin@example.com")
    await log_admin_action(
        auth_schema,
        action=AdminAction.INVITE_SENT,
        by=actor.id,
    )

    # The append-only trigger raises on any row DELETE.
    with pytest.raises(DBAPIError):
        await auth_schema.execute(delete(AdminAuditLog))
