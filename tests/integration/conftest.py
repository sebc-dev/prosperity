"""Fixtures shared by integration tests.

Provides a `db_session` async SQLAlchemy session backed by a Postgres
container managed by testcontainers. Tests opt in by depending on the
fixture; each test runs in its own transaction that is rolled back at
teardown so state never leaks across tests.

If Docker is not reachable on the host (typical local dev without Docker
Desktop's WSL integration enabled), the container fixture skips —
keeping the unit/http tiers green while the integration tier defers to
CI where Docker is available.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer


def _docker_available() -> bool:
    try:
        import docker

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
