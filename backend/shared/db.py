"""Async SQLAlchemy engine + FastAPI dependency.

The engine is created at app startup via :func:`lifespan` and stored on
``app.state.engine``. Tests construct their own engine via the
``async_client`` fixture (which overrides :func:`get_db`); no global
cache to clear.

REPEATABLE READ isolation closes the replay-vs-rotate race window where
an UPDATE in a concurrent transaction could miss an INSERT made by a
still-uncommitted sibling transaction (see
:func:`backend.modules.auth.service.refresh_tokens.rotate` for details).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import Settings, get_settings


def build_engine(settings: Settings) -> AsyncEngine:
    """Build the async engine with REPEATABLE READ isolation.

    Defense-in-depth against the replay-vs-rotate race. True concurrent
    contention surfaces as Postgres SQLSTATE 40001
    (`serialization_failure`); `service.refresh_tokens.rotate()` catches
    it and treats the loser as a replay (cf. ADR 0015). Callers in other
    services that don't handle 40001 will see it bubble up to a 500 —
    deliberate signal, since no other path currently exercises true
    concurrent UPDATEs on the same row.
    """
    # `hide_parameters=True` keeps bound values out of `DBAPIError.__str__`
    # (and therefore out of any `logger.warning("...", extra={"error": str(exc)})`
    # call site) — defense in depth against accidentally leaking the
    # hashed/plaintext password during `/setup`, refresh-token hashes
    # during rotation, or the S03.3 `INITIAL_ADMIN_PASSWORD_HASH` during
    # boot. We never log `str(exc)` ourselves, but Sentry / a future
    # logging shim might, and `hide_parameters` is the belt to that
    # braces. SQLAlchemy still emits the SQL statement with `?` markers,
    # which is enough for debugging.
    return create_async_engine(
        settings.database_url,
        future=True,
        isolation_level="REPEATABLE READ",
        hide_parameters=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    engine = build_engine(get_settings())
    app.state.engine = engine
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield
    finally:
        await engine.dispose()


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an async session bound to the request.

    Commit-on-success: the route never needs to call `commit()` itself.
    Rollback fires on any exception so partial writes don't bleed across
    requests.

    Risk note: if Pydantic serialisation fails *after* the commit, the
    client receives 500 while the DB is already mutated. Acceptable for
    S02.4 (token-pair responses are trivial); revisit if richer response
    shapes are added.
    """
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
