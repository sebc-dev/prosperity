"""Integration tests for the `invitations` DB constraints (S04.3).

`test_migrations_schema.py` proves the partial unique index, the
`token_hash` UNIQUE and the FK *exist* in the migrated schema; these tests
prove they actually *fire* at the runtime engine level. A partial index
declared but silently mis-scoped (e.g. a wrong WHERE) would pass the
snapshot but let a second pending invitation through here.

Mirrors `test_household_constraint.py`: ORM-path plus a raw-SQL path that
bypasses the `@validates` normalisation, locking the functional
`lower(email)` defence-in-depth.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.models import Invitation, User, UserRole

UserMaker = Callable[..., Awaitable[User]]


def _pending(
    invited_by: uuid.UUID,
    *,
    email: str = "invitee@example.com",
    token_hash: str = "a" * 64,
    accepted_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> Invitation:
    now = datetime.now(tz=UTC)
    return Invitation(
        email=email,
        invited_by=invited_by,
        invited_at=now,
        expires_at=now + timedelta(days=7),
        token_hash=token_hash,
        accepted_at=accepted_at,
        revoked_at=revoked_at,
    )


async def _admin(factory: UserMaker, *, email: str = "admin@example.com") -> uuid.UUID:
    admin = await factory(email=email, role=UserRole.ADMIN)
    return admin.id


async def test_two_pending_same_email_violates_partial_index(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    by = await _admin(bound_user_factory)
    auth_schema.add(_pending(by, email="dup@example.com", token_hash="a" * 64))
    await auth_schema.flush()
    auth_schema.add(_pending(by, email="dup@example.com", token_hash="b" * 64))
    with pytest.raises(IntegrityError):
        await auth_schema.flush()


async def test_partial_index_is_case_insensitive(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    by = await _admin(bound_user_factory)
    auth_schema.add(_pending(by, email="case@example.com", token_hash="a" * 64))
    await auth_schema.flush()
    # `@validates` lowercases "CASE@Example.com" to the same stored value;
    # the functional `lower(email)` index would catch it even if it didn't.
    auth_schema.add(_pending(by, email="CASE@Example.com", token_hash="b" * 64))
    with pytest.raises(IntegrityError):
        await auth_schema.flush()


async def test_partial_index_case_insensitive_against_raw_sql(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    # Defence-in-depth: a raw INSERT bypasses `@validates`, so only the
    # functional `lower(email)` index stands between mixed-case duplicates.
    by = await _admin(bound_user_factory)
    auth_schema.add(_pending(by, email="raw@example.com", token_hash="a" * 64))
    await auth_schema.flush()
    now = datetime.now(tz=UTC)
    stmt = text(
        "INSERT INTO invitations "
        "(id, email, invited_by, invited_at, expires_at, token_hash) "
        "VALUES (:id, :email, :by, :at, :exp, :th)"
    )
    with pytest.raises(IntegrityError):
        await auth_schema.execute(
            stmt,
            {
                "id": uuid.uuid4(),
                "email": "RAW@Example.com",
                "by": by,
                "at": now,
                "exp": now + timedelta(days=7),
                "th": "b" * 64,
            },
        )


async def test_revoked_invitation_does_not_block_new_pending(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    by = await _admin(bound_user_factory)
    auth_schema.add(
        _pending(
            by, email="reinvite@example.com", token_hash="a" * 64, revoked_at=datetime.now(tz=UTC)
        )
    )
    await auth_schema.flush()
    # The revoked row dropped out of the partial index → a new pending one
    # for the same email is allowed.
    auth_schema.add(_pending(by, email="reinvite@example.com", token_hash="b" * 64))
    await auth_schema.flush()  # no IntegrityError


async def test_accepted_invitation_does_not_block_new_pending(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    by = await _admin(bound_user_factory)
    auth_schema.add(
        _pending(
            by, email="accept@example.com", token_hash="a" * 64, accepted_at=datetime.now(tz=UTC)
        )
    )
    await auth_schema.flush()
    auth_schema.add(_pending(by, email="accept@example.com", token_hash="b" * 64))
    await auth_schema.flush()  # no IntegrityError


async def test_duplicate_token_hash_violates_unique(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    by = await _admin(bound_user_factory)
    auth_schema.add(_pending(by, email="one@example.com", token_hash="c" * 64))
    await auth_schema.flush()
    # Different email, same token_hash → uq_invitations_token_hash fires.
    auth_schema.add(_pending(by, email="two@example.com", token_hash="c" * 64))
    with pytest.raises(IntegrityError):
        await auth_schema.flush()


async def test_unknown_invited_by_violates_fk(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    # `auth_schema` materialises the schema; no user with this id exists.
    auth_schema.add(_pending(uuid.uuid4(), email="orphan@example.com"))
    with pytest.raises(IntegrityError):
        await auth_schema.flush()
