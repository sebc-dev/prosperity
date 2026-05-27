"""Fixtures shared by integration tests.

Provides a `db_session` async SQLAlchemy session backed by a Postgres
container managed by testcontainers. Tests opt in by depending on the
fixture; each test runs in its own transaction that is rolled back at
teardown so state never leaks across tests.

If Docker is not reachable on the host (typical local dev without Docker
Desktop's WSL integration enabled), the container fixture skips —
keeping the unit/http tiers green while the integration tier defers to
CI where Docker is available.

Also exposes:
- `auth_schema` — db_session with `users` + `refresh_tokens` materialised
- `bound_user_factory` — factory that creates a `User` against `db_session`
- `async_client` — httpx AsyncClient bound to the FastAPI app, with
  `get_db` overridden to yield the test's `db_session` (no commit, so
  the transactional rollback teardown reverts everything).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import cast

import docker
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session
from testcontainers.postgres import PostgresContainer

from backend.main import app
from backend.modules.auth.models import User
from backend.shared.db import get_db
from backend.shared.models import Base
from tests.factories.sqlalchemy import UserFactory


def _docker_available() -> bool:
    try:
        docker.from_env().ping()
    except Exception:
        return False
    return True


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    if not _docker_available():
        pytest.skip("Docker unavailable — integration tier requires a Docker daemon")
    with PostgresContainer("postgres:17-alpine", driver="asyncpg") as container:
        yield container


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_engine(postgres_container: PostgresContainer) -> AsyncIterator[object]:
    engine = create_async_engine(postgres_container.get_connection_url(), future=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(db_engine) -> AsyncIterator[AsyncSession]:
    """Per-test async session with rollback-on-teardown isolation."""
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        session_factory = async_sessionmaker(bind=connection, expire_on_commit=False)
        async with session_factory() as session:
            try:
                yield session
            finally:
                await transaction.rollback()


@pytest_asyncio.fixture(loop_scope="session")
async def auth_schema(db_session: AsyncSession) -> AsyncSession:
    """Create every persisted-module table on the test's transactional connection.

    Historically scoped to the auth tables; with the shared `Base`
    `create_all` materialises every module's tables in one shot. The
    name is preserved so S02.* consumers keep working; new callers
    should treat it as "all-modules schema". Setup is cheap (one DDL
    round-trip) and the transaction-level rollback teardown still
    guarantees per-test isolation.
    """
    conn = await db_session.connection()
    await conn.run_sync(Base.metadata.create_all)
    return db_session


@pytest_asyncio.fixture(loop_scope="session")
async def bound_user_factory(
    auth_schema: AsyncSession,
) -> Callable[..., Awaitable[User]]:
    """Async helper that persists a `User` against the test's session.

    Extracted from the `_make_user` helper that lived in
    `test_refresh_tokens.py` once S02.4 introduced a second consumer
    (auth routes tests). Kept here (not in the global `tests/conftest.py`)
    so the unit tier never pulls in `db_session`.
    """

    async def _make_user(**overrides: object) -> User:
        def _create(sync_session: Session) -> User:
            UserFactory._meta.sqlalchemy_session = sync_session  # type: ignore[attr-defined]
            return cast(User, UserFactory(**overrides))

        return await auth_schema.run_sync(_create)

    return _make_user


@pytest_asyncio.fixture(loop_scope="session")
async def async_client(auth_schema: AsyncSession) -> AsyncIterator[AsyncClient]:
    """httpx AsyncClient wired to the FastAPI app with `get_db` overridden.

    Mirrors prod `get_db` semantics: each request gets its **own** session
    bound to the test's connection, with `join_transaction_mode="create_savepoint"`
    so request-level commit/rollback maps to SAVEPOINT release/revert
    inside the outer test transaction. The test's setup writes (via
    `auth_schema` and `bound_user_factory`) stay in the outer transaction
    untouched, so a request that 4xx-rollbacks does not wipe schema or
    fixture users.

    Critically, this means `service.rotate()`'s commit-inside-service
    (ADR 0015) actually survives the route's exception handler in
    tests — the bug fixed in #58 was masked by the previous override
    that yielded the shared session without any commit/rollback wrap.
    `try/finally` + `pop(get_db, None)` so adjacent fixtures that
    register their own overrides are not clobbered.
    """
    connection = await auth_schema.connection()
    request_session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with request_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
