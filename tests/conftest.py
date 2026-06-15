"""Shared pytest fixtures and configuration.

Hosts the **real-commit** fixture stack (`postgres_container`,
`committed_engine`, `committed_sessionmaker`, `committed_client`,
`_clean_committed_db`) at the test-tree root so *both* the `integration`
and `e2e` tiers can resolve them: a `conftest.py`'s fixtures are only
visible down its own subtree, and the nearest common ancestor of
`tests/integration/` and `tests/e2e/` is this file (P-E2E.1 hoist).

The `unit` tier never depends on these, and they are lazy
(`postgres_container` skips when Docker is unreachable), so the unit tier
still runs without a Docker daemon. The rollback/savepoint stack
(`db_engine`, `db_session`, `auth_schema`, `bound_user_factory`,
`async_client`) stays local to `tests/integration/conftest.py`.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import docker
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from hypothesis import settings as _hyp_settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

import backend.modules.accounts.models  # noqa: F401  # pyright: ignore[reportUnusedImport]  side-effect: register tables on `Base.metadata`

# Side-effect: register the `debts` tables (`debts` + `share_requests`). REQUIRED
# because S09.1 activates the FK `transactions.share_request_id →
# share_requests.id` — `backend.main` pulls in `transactions.models` but NOT
# `debts.models`, so the e2e `create_all` (below) cannot resolve that FK target
# table unless `share_requests` is registered here first.
import backend.modules.debts.models  # noqa: F401  # pyright: ignore[reportUnusedImport]

# Side-effect: register `sync_request_log` (S13.2, #187) so the real-commit
# `committed_engine` `create_all` materialises it for the purge-script test.
import backend.modules.sync.models  # noqa: F401  # pyright: ignore[reportUnusedImport]
from backend.main import app
from backend.shared.db import get_db
from backend.shared.models import Base

# Profiles consumed by CI: push.yml leaves the default (max_examples=100),
# nightly.yml sets HYPOTHESIS_PROFILE=nightly for the 500-example sweep
# (docs/Stratégie de tests §9.3).
_hyp_settings.register_profile("ci", max_examples=50)
_hyp_settings.register_profile("nightly", max_examples=500)
_hyp_settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))


# ---------------------------------------------------------------------------
# Real-commit fixtures
# ---------------------------------------------------------------------------
#
# Tests that need true `after_commit` events (S03.2 cache invalidation)
# or cross-session concurrency races (S02.4 refresh-token replay,
# S03.2 `/setup` race) cannot use the `db_session` / `async_client`
# pair: the savepoint mode means request-level "commits" are SAVEPOINT
# releases, which do not fire `after_commit` on the outer transaction
# and stay invisible to sibling sessions.
#
# `committed_engine` is the dedicated alternative — own connection,
# REPEATABLE READ (production isolation, cf. `shared.db.build_engine`),
# create_all/drop_all at module scope.


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
    # Throwaway test database → durability is irrelevant: disable fsync, group-commit
    # and full-page-writes. Removes the per-write disk-sync cost that dominates a
    # write-heavy integration suite. NEVER use these flags for a real database.
    # (The official postgres image's entrypoint prepends `postgres` to a command that
    # starts with `-`, so this becomes `postgres -c fsync=off …`.)
    container = PostgresContainer("postgres:17-alpine", driver="asyncpg").with_command(
        "-c fsync=off -c synchronous_commit=off -c full_page_writes=off"
    )
    with container as started:
        yield started


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def committed_engine(
    postgres_container: PostgresContainer,
) -> AsyncIterator[AsyncEngine]:
    """Module-scoped engine with real commits + REPEATABLE READ.

    Distinct from `db_engine`: the latter is session-scoped and meant
    for the per-test rollback pattern (`db_session`). `committed_engine`
    is for tests that need:
    - true `after_commit` events to fire (S03.2 cache invalidation)
    - cross-session visibility (concurrency races on independent sessions)

    Schema is created at module setup and dropped at teardown so
    subsequent test modules (those using `db_session`) start clean.
    """
    engine = create_async_engine(
        postgres_container.get_connection_url(),
        future=True,
        isolation_level="REPEATABLE READ",
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def committed_sessionmaker(
    committed_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Pre-built sessionmaker on `committed_engine` for side-channel writes."""
    return async_sessionmaker(committed_engine, expire_on_commit=False)


@pytest_asyncio.fixture(loop_scope="session")
async def committed_client(
    committed_sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    """httpx AsyncClient whose `get_db` yields real-commit sessions.

    Each HTTP request opens a fresh session on `committed_engine`,
    commits on success, rolls back on exception. The `after_commit`
    listener registered in
    `accounts.service.setup.initialize_bootstrap` actually fires here
    — that's the whole point of this fixture vs `async_client` (which
    uses savepoint mode).
    """

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with committed_sessionmaker() as session:
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


@pytest_asyncio.fixture
async def _clean_committed_db(  # pyright: ignore[reportUnusedFunction]
    committed_sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    """Truncate every committed-engine table before AND after each test.

    Module-scoped `committed_engine` keeps real-committed state between
    tests; without this opt-in cleanup a test that doesn't tidy up
    poisons the next one. Iterating `Base.metadata.sorted_tables` keeps
    the table list automatic as future modules add tables. CASCADE
    handles FK chains; `RESTART IDENTITY` resets sequences (gratuit
    today, cheap insurance for future BIGSERIAL columns).

    Opt in per file via
    `pytestmark = [pytest.mark.usefixtures("_clean_committed_db")]`.
    `db_session`-based tests don't need it (rollback isolation).
    """

    async def _truncate_all() -> None:
        names = [t.name for t in Base.metadata.sorted_tables]
        if not names:
            return  # defensive: empty metadata (cannot happen here)
        async with committed_sessionmaker() as session:
            await session.execute(text(f"TRUNCATE {', '.join(names)} RESTART IDENTITY CASCADE"))
            await session.commit()

    # Defensive truncate-before: a prior crashed test may have left state.
    await _truncate_all()
    yield
    await _truncate_all()
