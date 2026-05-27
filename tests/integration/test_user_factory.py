"""Integration tests for `UserFactory` and the `users` table invariants.

Exercises the factory end-to-end (persist + Argon2id round-trip via
`pwdlib`) and locks the DB-level constraints that `test_migrations_schema.py`
cannot cover from column-name snapshots alone:

- the `user_role` PG ENUM rejects values outside `{admin, member}`,
- the functional unique index on `lower(email)` rejects case-insensitive
  duplicates even when the ORM validator is bypassed via raw SQL,
- the `@validates("email")` ORM hook lowercases + strips on assignment.

The session is the per-test rollback-isolated `db_session` fixture from
`tests/integration/conftest.py`.

factory-boy's SQLAlchemy backend calls synchronous `session.add` /
`session.flush`; we bridge to the async test session via
`AsyncSession.run_sync`, which yields the underlying sync `Session` to a
callable run inside greenlet-translated I/O.

The `users` table is materialised on the test's transactional connection
via `Base.metadata.create_all`. We deliberately don't run Alembic here:
the migration-vs-model contract is enforced by
`test_migrations_schema.py`, and re-running migrations per test would
slow the tier down. The transaction is rolled back on teardown so the
table never leaks across tests.
"""

from __future__ import annotations

from typing import cast

import pytest
import pytest_asyncio
from pwdlib import PasswordHash
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.modules.auth.models import User
from backend.shared.models import Base
from tests.factories.sqlalchemy import UserFactory


@pytest_asyncio.fixture(loop_scope="session")
async def users_schema(db_session: AsyncSession) -> AsyncSession:
    """Create the `users` table on the test's transactional connection."""
    conn = await db_session.connection()
    await conn.run_sync(Base.metadata.create_all)
    return db_session


async def test_user_factory_persists_and_hashes_password(
    users_schema: AsyncSession,
) -> None:
    plaintext = "correct horse battery staple"

    def _create_user(sync_session: Session) -> User:
        UserFactory._meta.sqlalchemy_session = sync_session  # type: ignore[attr-defined]
        return cast(
            User,
            UserFactory(
                email="alice@example.com",
                display_name="Alice",
                password=plaintext,
            ),
        )

    created = await users_schema.run_sync(_create_user)

    fetched = (
        await users_schema.execute(select(User).where(User.email == "alice@example.com"))
    ).scalar_one()

    assert fetched.id == created.id
    assert fetched.display_name == "Alice"
    assert fetched.role == "member"
    assert fetched.disabled_at is None

    hasher = PasswordHash.recommended()
    assert hasher.verify(plaintext, fetched.password_hash) is True
    assert hasher.verify("not the right password", fetched.password_hash) is False


async def test_email_normalised_on_assignment(users_schema: AsyncSession) -> None:
    """`@validates("email")` lowercases + strips before the row is persisted."""

    def _create(sync_session: Session) -> User:
        UserFactory._meta.sqlalchemy_session = sync_session  # type: ignore[attr-defined]
        return cast(User, UserFactory(email="  Alice@Example.COM  "))

    created = await users_schema.run_sync(_create)
    assert created.email == "alice@example.com"


async def test_duplicate_email_rejected(users_schema: AsyncSession) -> None:
    """`uq_users_email_lower` rejects same-case duplicate emails."""

    def _make(sync_session: Session, mail: str) -> None:
        UserFactory._meta.sqlalchemy_session = sync_session  # type: ignore[attr-defined]
        UserFactory(email=mail)

    await users_schema.run_sync(lambda s: _make(s, "dup@example.com"))
    with pytest.raises(IntegrityError):
        await users_schema.run_sync(lambda s: _make(s, "dup@example.com"))


async def test_duplicate_email_case_insensitive_rejected(
    users_schema: AsyncSession,
) -> None:
    """The functional `lower(email)` unique index catches case-different duplicates.

    Even if a future path bypasses the ORM validator (raw SQL, admin
    script, etc.), inserting both "alice@x.com" and "Alice@X.com" must
    fail — otherwise S02.4 login routes would race on two distinct rows.
    """

    def _make(sync_session: Session, mail: str) -> None:
        UserFactory._meta.sqlalchemy_session = sync_session  # type: ignore[attr-defined]
        UserFactory(email=mail)

    await users_schema.run_sync(lambda s: _make(s, "alice@example.com"))
    with pytest.raises(IntegrityError):
        await users_schema.run_sync(lambda s: _make(s, "Alice@Example.com"))


async def test_role_not_in_enum_rejected_at_db(users_schema: AsyncSession) -> None:
    """The `user_role` PG ENUM rejects unknown values on raw INSERT.

    Goes through `text()` rather than `UserFactory` so the assertion
    binds to the DB-level constraint (not Python-side StrEnum coercion):
    if a future refactor drops the PG ENUM in favour of a free string
    column, this test will fail loudly.
    """
    with pytest.raises(DBAPIError):
        await users_schema.execute(
            text(
                "INSERT INTO users "
                "(id, email, password_hash, display_name, role) "
                "VALUES (gen_random_uuid(), 'x@y.com', 'h', 'X', 'superadmin')"
            )
        )
