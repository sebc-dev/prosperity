"""Smoke test for FastAPI app boot (story S02.4).

Importing `backend.main` runs the router-include side effects. If a
chain of imports (transports → public → transports) ever circulates,
the import would fail at module load and this test would surface that
before any HTTP request is dispatched.
"""

# The composition-root wiring test reaches into `main`'s private
# `_register_event_subscribers` and the bus' private `_async_subscribers` registry
# on purpose (there is no public introspection surface) — scope the relaxation to
# this file (gabarit `test_overflow_materializer_unit.py`).
# pyright: reportPrivateUsage=false
from __future__ import annotations

from collections.abc import Callable

import pytest

from backend.main import _register_event_subscribers, app
from backend.modules.budget.public import (
    BudgetCreatedEvent,
    BudgetUpdatedEvent,
    on_transaction_confirmed,
)
from backend.modules.debts.public import (
    materialize_overflow,
    recompute_overflow_on_budget_event,
    rematerialize_overflow_on_edit,
    remove_overflow_on_void,
)
from backend.modules.transactions.public import (
    TransactionConfirmedEvent,
    TransactionEditableFieldsChangedEvent,
    TransactionVoidedEvent,
)
from backend.shared import events as bus

# Every (event_type, handler) pair `_register_event_subscribers` MUST wire — the
# overflow F10 materialiser (S11.3, three tx events) AND the budget reclassement
# (S11.4, two budget events) AND the budget threshold alert (`on_transaction_confirmed`).
# Asserting all SIX closes the residual false-green where `main.py` dropped only the
# budget wiring while the overflow integration tier (own autouse fixture) stayed green.
_WIRED_SUBSCRIBERS: list[tuple[type, Callable[..., object]]] = [
    (TransactionConfirmedEvent, on_transaction_confirmed),
    (TransactionConfirmedEvent, materialize_overflow),
    (TransactionVoidedEvent, remove_overflow_on_void),
    (TransactionEditableFieldsChangedEvent, rematerialize_overflow_on_edit),
    (BudgetCreatedEvent, recompute_overflow_on_budget_event),
    (BudgetUpdatedEvent, recompute_overflow_on_budget_event),
]


def _paths() -> set[str]:
    return {getattr(route, "path", "") for route in app.routes}


def test_auth_routes_registered_on_app() -> None:
    paths = _paths()
    assert "/auth/login" in paths
    assert "/auth/refresh" in paths
    assert "/auth/logout" in paths


def test_healthz_route_still_registered() -> None:
    assert "/healthz" in _paths()


@pytest.mark.parametrize(("event_type", "handler"), _WIRED_SUBSCRIBERS)
def test_overflow_handlers_wired_at_composition_root(
    event_type: type, handler: Callable[..., object]
) -> None:
    # Every subscriber wired by `main.py`'s `_register_event_subscribers` must land on
    # its event type (composition root, ADR 0005 — `debts`/`budget` cannot know their own
    # cross-module subscriptions). The integration tier re-wires the bus via its own
    # autouse fixture, so without THIS test, dropping a `subscribe_async` line from
    # `main.py` would pass every overflow/budget integration test. S13.5 extends the
    # lock from the three overflow handlers to all six wired pairs (incl. the budget
    # reclassement + threshold alert), closing the residual false-green on the budget wiring.
    bus.clear_subscribers()
    try:
        _register_event_subscribers()
        assert handler in bus._async_subscribers[event_type]
    finally:
        bus.clear_subscribers()  # global registry — never leak into sibling tests
