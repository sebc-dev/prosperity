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
    """The duplicate must trip `uq_users_email_lower` specifically.

    Asserting `IntegrityError` alone is too loose — any future UNIQUE/PK
    regression would pass. Pinning the constraint name in `exc.orig`
    confirms the **functional** index on `lower(email)` fired (and not,
    e.g., a different UNIQUE added later by mistake).
    """
    await create_user(
        auth_schema,
        email="admin@example.com",
        password="correct-horse-battery-staple",
        display_name="Admin",
        role=UserRole.ADMIN,
    )
    with pytest.raises(IntegrityError) as exc_info:
        await create_user(
            auth_schema,
            email="ADMIN@example.COM",  # same row under lower(email)
            password="another-strong-password",
            display_name="Admin Bis",
            role=UserRole.ADMIN,
        )
    assert "uq_users_email_lower" in str(exc_info.value.orig)


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
    """Pin the contract: a SAVEPOINT rollback erases the row.

    Post-flush visibility inside the *same* session does not distinguish
    commit from no-commit (the row is visible either way). The real
    discriminator is a SAVEPOINT rollback: if `create_user` had issued
    an implicit `commit()`, the outer transaction would end and any
    SAVEPOINT would be released, leaving the row persisted. We assert
    the SAVEPOINT rollback successfully erases the row — proving no
    commit happened inside `create_user`.
    """
    savepoint = await auth_schema.begin_nested()
    try:
        await create_user(
            auth_schema,
            email="no-commit-sentinel@example.com",
            password="correct-horse-battery-staple",
            display_name="No Commit",
            role=UserRole.MEMBER,
        )
        # Visible inside the SAVEPOINT post-flush.
        inside = await auth_schema.execute(
            select(User).where(User.email == "no-commit-sentinel@example.com")
        )
        assert inside.scalar_one_or_none() is not None
    finally:
        await savepoint.rollback()

    # After SAVEPOINT rollback the row is gone — proves `create_user`
    # did not call `commit()` (a commit would have released the
    # SAVEPOINT, leaving the row persisted past this point).
    after = await auth_schema.execute(
        select(User).where(User.email == "no-commit-sentinel@example.com")
    )
    assert after.scalar_one_or_none() is None
