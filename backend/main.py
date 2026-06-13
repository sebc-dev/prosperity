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
from backend.modules.budget.public import (
    BudgetCreatedEvent,
    BudgetUpdatedEvent,
    on_transaction_confirmed,
)
from backend.modules.budget.transports.budgets_http import budgets_router
from backend.modules.budget.transports.http import categories_router
from backend.modules.debts.public import (
    materialize_overflow,
    recompute_overflow_on_budget_event,
    rematerialize_overflow_on_edit,
    remove_overflow_on_void,
)
from backend.modules.debts.transports.http import (
    debts_router,
    settlements_router,
    share_requests_router,
    tx_share_requests_router,
)
from backend.modules.sse.transports.http import sse_router
from backend.modules.sync.transports.http import sync_router
from backend.modules.transactions.public import (
    TransactionConfirmedEvent,
    TransactionEditableFieldsChangedEvent,
    TransactionVoidedEvent,
)
from backend.modules.transactions.transports.http import (
    account_tx_router,
    transactions_router,
)
from backend.shared.db import lifespan as db_lifespan
from backend.shared.events import subscribe_async
from backend.transports.imports_http import imports_router


def _register_event_subscribers() -> None:
    """Wire the mini-bus subscribers at the composition root (idempotent).

    Lives here, NOT in `budget.public`: `budget ⊥ transactions` (peer modules,
    contract 1), so `budget` cannot import `TransactionConfirmedEvent`. `main`
    sits above every module → it imports both `.public` surfaces freely and
    connects them.

    Called from the `lifespan` BEFORE `yield` (symmetry with
    `bootstrap_initial_admin_from_env`), NOT at module top-level: a top-level
    call would run at IMPORT time, and a cross-import in tests (testcontainers
    re-imports `main`) would re-register the handler. `subscribe_async` is
    idempotent, so even a re-run of the lifespan (a test app) stays safe.

    S11.3 wires the `debts` overflow materializer (F10) to three `transactions`
    events: confirm/edit re-materialise the overflow debts, void removes them.
    S11.4 wires it to the `budget` created/updated events too (reclassement F10): a
    budget that appears / changes / is archived re-materialises the overflow of the
    past transactions it covers.
    """
    subscribe_async(TransactionConfirmedEvent, on_transaction_confirmed)
    subscribe_async(TransactionConfirmedEvent, materialize_overflow)
    subscribe_async(TransactionVoidedEvent, remove_overflow_on_void)
    subscribe_async(TransactionEditableFieldsChangedEvent, rematerialize_overflow_on_edit)
    subscribe_async(BudgetCreatedEvent, recompute_overflow_on_budget_event)
    subscribe_async(BudgetUpdatedEvent, recompute_overflow_on_budget_event)


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

    3. `_register_event_subscribers` wires the mini-bus subscribers
       (idempotent) before `yield` — see its docstring for why this
       lives at the composition root and not at module top-level.
    """
    async with db_lifespan(app):
        await bootstrap_initial_admin_from_env(app.state.sessionmaker, get_settings())
        _register_event_subscribers()
        yield


app = FastAPI(title="Prosperity", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(invitations_router)
app.include_router(accept_invite_router)
app.include_router(setup_router)
app.include_router(accounts_router)
app.include_router(categories_router)
app.include_router(budgets_router)
app.include_router(account_tx_router)
app.include_router(transactions_router)
app.include_router(tx_share_requests_router)
app.include_router(share_requests_router)
app.include_router(debts_router)
app.include_router(settlements_router)
app.include_router(imports_router)
app.include_router(sync_router)
app.include_router(sse_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
