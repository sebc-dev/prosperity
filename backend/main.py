"""FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.config import get_settings
from backend.modules.accounts.public import bootstrap_initial_admin_from_env
from backend.modules.accounts.transports.http import (
    accounts_router,
)
from backend.modules.accounts.transports.http import (
    router as setup_router,
)
from backend.modules.auth.transports.http import (
    accept_invite_router,
    invitations_router,
)
from backend.modules.auth.transports.http import (
    router as auth_router,
)
from backend.modules.budget.transports.http import categories_router
from backend.shared.db import lifespan as db_lifespan


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Compose the DB lifespan with the S03.3 initial-admin bootstrap.

    Ordering matters:

    1. `db_lifespan` builds the engine + sessionmaker on `app.state`.
    2. `bootstrap_initial_admin_from_env` runs against that sessionmaker
       BEFORE `yield` — the app must not accept traffic until the
       (potential) bootstrap has succeeded, skipped, or degraded
       gracefully. FastAPI/Starlette only begins accepting requests
       after the lifespan's `yield`, so `/setup` cannot race against
       the env-var seeding from outside.

    `bootstrap_initial_admin_from_env` never raises on infra/DB
    failures (see its docstring), so the surrounding `async with`
    always completes cleanly. A persistent DB error logs an error and
    the app starts without an admin — operators can then `/setup`
    manually once the DB recovers.
    """
    async with db_lifespan(app):
        await bootstrap_initial_admin_from_env(app.state.sessionmaker, get_settings())
        yield


app = FastAPI(title="Prosperity", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(invitations_router)
app.include_router(accept_invite_router)
app.include_router(setup_router)
app.include_router(accounts_router)
app.include_router(categories_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
