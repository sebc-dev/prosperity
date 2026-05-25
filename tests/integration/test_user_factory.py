"""Integration test for `UserFactory`.

Exercises the factory end-to-end: it must persist a `User` row, hash the
supplied plaintext with Argon2id, and let `pwdlib` re-verify the hash on
read-back. The session is the per-test rollback-isolated `db_session`
fixture from `tests/integration/conftest.py`.

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

import pytest_asyncio
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.modules.auth.models import Base, User
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
