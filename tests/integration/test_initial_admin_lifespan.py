"""Smoke test for the composed lifespan in `backend.main` (S03.3).

Verifies the contract that matters for prod:

* With `INITIAL_ADMIN_*` env vars set, an HTTP request reaching the
  fresh app reads the post-bootstrap state — `users` is non-empty,
  `/setup` returns 404 (lock-after-init).
* With no env vars, the app boots cleanly and `/setup` is open.

Builds a **fresh** `FastAPI(lifespan=lifespan)` rather than reusing
`backend.main.app` to avoid cross-test bleed: `backend.main.app` is
imported by `tests/integration/conftest.py` at module-load time and
shared across the suite.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from backend.config import get_settings
from backend.main import lifespan
from backend.modules.accounts.transports.http import router as accounts_router
from backend.modules.auth.models import User
from backend.modules.auth.transports.http import router as auth_router
from backend.shared.models import Base

_PLAINTEXT = "correct-horse-battery-staple-12chars"


def _build_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.include_router(auth_router)
    app.include_router(accounts_router)
    return app


@pytest_asyncio.fixture(loop_scope="session")
async def _ensure_schema(postgres_container: PostgresContainer) -> AsyncIterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Create the schema once before the test, drop after.

    The composed `lifespan` only builds the engine; it doesn't run
    migrations. We `create_all` against the same DSN before the app
    boots so `bootstrap_initial_admin_from_env` finds the expected
    tables. Truncating between tests keeps each one isolated.
    """
    engine = create_async_engine(postgres_container.get_connection_url(), future=True)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


async def test_lifespan_seeds_admin_when_env_vars_set(
    monkeypatch: pytest.MonkeyPatch,
    postgres_container: PostgresContainer,
    _ensure_schema: None,  # noqa: PT019 — fixture pulled for its side effect
) -> None:
    """Env vars set → after lifespan startup, the admin row is present + /setup is 404."""
    precomputed = PasswordHash.recommended().hash(_PLAINTEXT)

    monkeypatch.setenv("DATABASE_URL", postgres_container.get_connection_url())
    monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD_HASH", precomputed)
    monkeypatch.setenv("INITIAL_ADMIN_DISPLAY_NAME", "Admin")
    monkeypatch.setenv("INITIAL_HOUSEHOLD_NAME", "Foyer Lifespan")
    # Clear the `lru_cache` so the lifespan reads the patched env vars.
    get_settings.cache_clear()

    app = _build_app()
    try:
        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Post-bootstrap → /setup is permanently locked.
                resp = await client.get("/setup")
                assert resp.status_code == 404

            # Side-channel: the admin row exists with the expected email.
            sm: async_sessionmaker[AsyncSession] = app.state.sessionmaker
            async with sm() as s:
                user = (await s.execute(select(User))).scalar_one()
            assert user.email == "admin@example.com"
            assert user.password_hash == precomputed
    finally:
        get_settings.cache_clear()


async def test_lifespan_normal_mode_when_env_vars_absent(
    monkeypatch: pytest.MonkeyPatch,
    postgres_container: PostgresContainer,
    _ensure_schema: None,  # noqa: PT019
) -> None:
    """No env vars → no admin, /setup open. The standard installer experience."""
    monkeypatch.setenv("DATABASE_URL", postgres_container.get_connection_url())
    for key in (
        "INITIAL_ADMIN_EMAIL",
        "INITIAL_ADMIN_PASSWORD_HASH",
        "INITIAL_ADMIN_DISPLAY_NAME",
        "INITIAL_HOUSEHOLD_NAME",
    ):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()

    app = _build_app()
    try:
        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/setup")
                assert resp.status_code == 200
                assert resp.json() == {"status": "open"}

            sm: async_sessionmaker[AsyncSession] = app.state.sessionmaker
            async with sm() as s:
                users = (await s.execute(select(User))).scalars().all()
            assert users == []
    finally:
        get_settings.cache_clear()
