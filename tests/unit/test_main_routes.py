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

from backend.main import _register_event_subscribers, app
from backend.modules.debts.public import (
    materialize_overflow,
    rematerialize_overflow_on_edit,
    remove_overflow_on_void,
)
from backend.modules.transactions.public import (
    TransactionConfirmedEvent,
    TransactionEditableFieldsChangedEvent,
    TransactionVoidedEvent,
)
from backend.shared import events as bus


def _paths() -> set[str]:
    return {getattr(route, "path", "") for route in app.routes}


def test_auth_routes_registered_on_app() -> None:
    paths = _paths()
    assert "/auth/login" in paths
    assert "/auth/refresh" in paths
    assert "/auth/logout" in paths


def test_healthz_route_still_registered() -> None:
    assert "/healthz" in _paths()


def test_overflow_handlers_wired_at_composition_root() -> None:
    # The three S11.3 overflow handlers must be subscribed by `main.py`'s
    # `_register_event_subscribers` (composition root, ADR 0005 — `debts` cannot
    # know its own subscriptions). The integration tier re-wires the bus via its own
    # autouse fixture, so without THIS test, dropping a `subscribe_async` line from
    # `main.py` would pass every overflow integration test. Drive the real wiring
    # function and assert each handler lands on the right event type.
    bus.clear_subscribers()
    try:
        _register_event_subscribers()
        assert materialize_overflow in bus._async_subscribers[TransactionConfirmedEvent]
        assert remove_overflow_on_void in bus._async_subscribers[TransactionVoidedEvent]
        assert (
            rematerialize_overflow_on_edit
            in bus._async_subscribers[TransactionEditableFieldsChangedEvent]
        )
    finally:
        bus.clear_subscribers()  # global registry — never leak into sibling tests
