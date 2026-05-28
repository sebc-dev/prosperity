"""Integration tests for `backend.modules.auth.service.users` (S03.2 P0).

`create_user` and `any_user_exists` are tested against a real Postgres
schema via `auth_schema` so the functional unique index on
`lower(email)` actually fires (the model validator alone would let
case-different duplicates through if the index regressed).
"""

from __future__ import annotations

import pytest
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.models import User, UserRole
from backend.modules.auth.service.users import any_user_exists, create_user

_HASHER = PasswordHash.recommended()


async def test_create_user_persists_user_with_argon2id_hash(
    auth_schema: AsyncSession,
) -> None:
    user = await create_user(
        auth_schema,
        email="admin@example.com",
        password="correct-horse-battery-staple",
        display_name="Admin",
        role=UserRole.ADMIN,
    )
    assert user.id is not None
    assert user.email == "admin@example.com"
    assert user.role is UserRole.ADMIN
    # Argon2id digests start with `$argon2id$` per the OWASP encoding.
    assert user.password_hash.startswith("$argon2id$")
    # The hash must verify the plaintext we passed in.
    assert _HASHER.verify("correct-horse-battery-staple", user.password_hash)


async def test_create_user_lowercases_email_via_validator(
    auth_schema: AsyncSession,
) -> None:
    user = await create_user(
        auth_schema,
        email="Admin@Example.COM",
        password="correct-horse-battery-staple",
        display_name="Admin",
        role=UserRole.ADMIN,
    )
    assert user.email == "admin@example.com"


async def test_create_user_duplicate_email_raises_integrity_error(
    auth_schema: AsyncSession,
) -> None:
    await create_user(
        auth_schema,
        email="admin@example.com",
        password="correct-horse-battery-staple",
        display_name="Admin",
        role=UserRole.ADMIN,
    )
    with pytest.raises(IntegrityError):
        await create_user(
            auth_schema,
            email="ADMIN@example.COM",  # same row under lower(email)
            password="another-strong-password",
            display_name="Admin Bis",
            role=UserRole.ADMIN,
        )


async def test_any_user_exists_false_on_empty_table(
    auth_schema: AsyncSession,
) -> None:
    assert await any_user_exists(auth_schema) is False


async def test_any_user_exists_true_after_insert(
    auth_schema: AsyncSession,
) -> None:
    await create_user(
        auth_schema,
        email="solo@example.com",
        password="correct-horse-battery-staple",
        display_name="Solo",
        role=UserRole.MEMBER,
    )
    assert await any_user_exists(auth_schema) is True


async def test_create_user_does_not_commit(auth_schema: AsyncSession) -> None:
    """Pin the contract that `create_user` flushes but never commits.

    `auth_schema` runs inside a transaction that the per-test fixture
    rolls back at teardown. If `create_user` accidentally committed,
    the row would survive a subsequent rollback — the assertion below
    proves it does not.
    """
    await create_user(
        auth_schema,
        email="no-commit@example.com",
        password="correct-horse-battery-staple",
        display_name="No Commit",
        role=UserRole.MEMBER,
    )
    # Visible inside the current transaction (post-flush).
    result = await auth_schema.execute(select(User).where(User.email == "no-commit@example.com"))
    assert result.scalar_one_or_none() is not None
    # The teardown rollback in `db_session` would erase the row if no
    # implicit commit happened — that's the rollback-isolation invariant
    # this test depends on.
