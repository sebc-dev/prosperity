"""Smoke tests for the production `shared/db.py` contract (issue #52).

The standard integration suite overrides `get_db` so the real lifespan
+ session contract is never exercised. This module bypasses that
override and drives the actual code path so a regression in
`build_engine`, `lifespan`, or `get_db` fails CI loudly.

Covers:
- `lifespan` populates `app.state.engine` and `app.state.sessionmaker`
- `build_engine` actually pins isolation to REPEATABLE READ
- `get_db` commits on success
- `get_db` rolls back on exception
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from _pytest.monkeypatch import MonkeyPatch
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from backend.config import Settings, get_settings
from backend.shared.db import build_engine, get_db, lifespan


@pytest_asyncio.fixture(loop_scope="session")
async def lifespan_app(
    postgres_container: PostgresContainer, monkeypatch_session
) -> AsyncIterator[FastAPI]:
    """A fresh FastAPI app wired to the production `lifespan`, pointed at
    the testcontainers Postgres via DATABASE_URL.

    Forces a `get_settings.cache_clear()` so the URL override is picked
    up; restores afterwards to avoid bleeding into adjacent tests.
    """
    monkeypatch_session.setenv("DATABASE_URL", postgres_container.get_connection_url())
    get_settings.cache_clear()
    try:
        app = FastAPI(lifespan=lifespan)

        @app.post("/_smoke/insert/{value}")
        async def smoke_insert(  # pyright: ignore[reportUnusedFunction]
            value: str,
            session=Depends(get_db),  # noqa: B008 — FastAPI dep injection
        ) -> dict[str, str]:
            await session.execute(
                text("INSERT INTO smoke_lifespan_marker (value) VALUES (:v)"),
                {"v": value},
            )
            return {"value": value}

        @app.post("/_smoke/insert-then-fail/{value}")
        async def smoke_insert_then_fail(  # pyright: ignore[reportUnusedFunction]
            value: str,
            session=Depends(get_db),  # noqa: B008
        ) -> dict[str, str]:
            await session.execute(
                text("INSERT INTO smoke_lifespan_marker (value) VALUES (:v)"),
                {"v": value},
            )
            raise RuntimeError("intentional smoke failure")

        # Materialise the marker table on a separate connection so it
        # survives the test's own transactional churn. Drop it at teardown.
        prep_engine = create_async_engine(
            postgres_container.get_connection_url(), future=True
        )
        try:
            async with prep_engine.begin() as conn:
                await conn.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS smoke_lifespan_marker "
                        "(value text PRIMARY KEY)"
                    )
                )
            yield app
        finally:
            async with prep_engine.begin() as conn:
                await conn.execute(text("DROP TABLE IF EXISTS smoke_lifespan_marker"))
            await prep_engine.dispose()
    finally:
        get_settings.cache_clear()


@pytest.fixture(scope="session")
def monkeypatch_session() -> Iterator[MonkeyPatch]:
    """Session-scoped monkeypatch (the default `monkeypatch` is function-scoped).

    Needed because `lifespan_app` is session-scoped via `loop_scope="session"`
    on the async fixture above.
    """
    mp = MonkeyPatch()
    try:
        yield mp
    finally:
        mp.undo()


async def test_lifespan_populates_engine_and_sessionmaker(lifespan_app: FastAPI) -> None:
    async with lifespan(lifespan_app):
        assert isinstance(lifespan_app.state.engine, AsyncEngine)
        assert isinstance(lifespan_app.state.sessionmaker, async_sessionmaker)


async def test_build_engine_pins_repeatable_read_isolation(
    postgres_container: PostgresContainer, monkeypatch_session
) -> None:
    """Defense-in-depth for `rotate()`: regressing to READ COMMITTED would
    reopen the replay-vs-rotate race window. `SHOW transaction_isolation`
    asserts what Postgres actually applies to a session from `build_engine`.
    """
    settings = Settings(
        database_url=postgres_container.get_connection_url(),
        jwt_secret=SecretStr("smoke-test-jwt-secret-min-32-chars!!"),
    )
    engine = build_engine(settings)
    try:
        async with async_sessionmaker(engine)() as session:
            result = await session.execute(text("SHOW transaction_isolation"))
            assert result.scalar_one() == "repeatable read"
    finally:
        await engine.dispose()


async def test_get_db_commits_on_success(lifespan_app: FastAPI) -> None:
    async with lifespan(lifespan_app):
        transport = ASGITransport(app=lifespan_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/_smoke/insert/committed-value")
            assert resp.status_code == 200

        # Verify with a connection that is independent of the request session.
        async with lifespan_app.state.engine.begin() as conn:
            row = await conn.execute(
                text("SELECT value FROM smoke_lifespan_marker WHERE value = 'committed-value'")
            )
            assert row.scalar_one() == "committed-value"


async def test_get_db_rolls_back_on_exception(lifespan_app: FastAPI) -> None:
    async with lifespan(lifespan_app):
        # `raise_app_exceptions=False` lets the test see the 500 response
        # FastAPI synthesises for unhandled exceptions, instead of the
        # exception propagating up through httpx (the default).
        transport = ASGITransport(app=lifespan_app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/_smoke/insert-then-fail/rolled-back-value")
            assert resp.status_code == 500

        async with lifespan_app.state.engine.begin() as conn:
            row = await conn.execute(
                text(
                    "SELECT value FROM smoke_lifespan_marker WHERE value = 'rolled-back-value'"
                )
            )
            assert row.scalar_one_or_none() is None
