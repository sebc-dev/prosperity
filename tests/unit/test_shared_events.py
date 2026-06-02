"""Unit tests for the in-process domain-event mini-bus (S05.4, P05.4.1).

Pure unit tier — no DB. The bus is module-level mutable state, so an autouse
fixture clears it around every test. The contract pinned here:

- `publish` with no subscriber is a no-op;
- a subscriber receives the exact event instance, once;
- handlers fire in registration order;
- dispatch is by **exact** runtime type (no fan-out to base or sibling types);
- a raising handler propagates synchronously out of `publish`;
- `unsubscribe` removes a handler (and is a no-op on an absent one).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from backend.shared.events import (
    DomainEvent,
    clear_subscribers,
    dispatch,
    publish,
    subscribe,
    subscribe_async,
    unsubscribe,
)


@dataclass(frozen=True, slots=True)
class _EvtA(DomainEvent):
    value: int = 0


@dataclass(frozen=True, slots=True)
class _EvtB(DomainEvent):
    value: int = 0


@dataclass(frozen=True, slots=True)
class _SubEvtA(_EvtA):
    pass


@pytest.fixture(autouse=True)
def _reset_event_bus() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Cold bus around every test (the registry is process-global)."""
    clear_subscribers()
    yield
    clear_subscribers()


def test_publish_without_subscriber_is_noop() -> None:
    # Must not raise, must do nothing observable.
    publish(_EvtA(value=1))
    publish(DomainEvent())


def test_subscriber_receives_exact_event_once() -> None:
    received: list[DomainEvent] = []
    subscribe(_EvtA, received.append)

    evt = _EvtA(value=42)
    publish(evt)

    assert received == [evt]
    assert received[0] is evt


def test_handlers_fire_in_registration_order() -> None:
    calls: list[str] = []
    subscribe(_EvtA, lambda _e: calls.append("h1"))
    subscribe(_EvtA, lambda _e: calls.append("h2"))

    publish(_EvtA())

    assert calls == ["h1", "h2"]


def test_dispatch_is_by_exact_type() -> None:
    a_calls: list[DomainEvent] = []
    subscribe(_EvtA, a_calls.append)

    publish(_EvtB())

    assert a_calls == []


def test_no_fanout_to_subtypes() -> None:
    # A subscriber on the base type is NOT called for a subclass (V1 semantics).
    base_calls: list[DomainEvent] = []
    subscribe(DomainEvent, base_calls.append)
    a_calls: list[DomainEvent] = []
    subscribe(_EvtA, a_calls.append)

    publish(_SubEvtA())

    assert base_calls == []
    assert a_calls == []


def test_raising_handler_propagates() -> None:
    def _boom(_e: DomainEvent) -> None:
        raise ValueError("boom")

    subscribe(_EvtA, _boom)

    with pytest.raises(ValueError, match="boom"):
        publish(_EvtA())


def test_unsubscribe_removes_handler() -> None:
    received: list[DomainEvent] = []
    # Bind the handler to a stable name: `list.append` returns a fresh bound
    # method on each attribute access, so `unsubscribe` must be given the very
    # object that was subscribed.
    handler = received.append
    subscribe(_EvtA, handler)

    publish(_EvtA(value=1))  # delivered
    unsubscribe(_EvtA, handler)
    publish(_EvtA(value=2))  # dropped

    assert len(received) == 1
    assert received[0].value == 1  # type: ignore[attr-defined]


def test_unsubscribe_absent_handler_is_noop() -> None:
    def _h(_e: DomainEvent) -> None:
        pass

    # Never subscribed → must not raise.
    unsubscribe(_EvtA, _h)


# ---------------------------------------------------------------------------
# Async channel (S08.3, P08.3.2) — `subscribe_async` / `dispatch`
# ---------------------------------------------------------------------------
#
# These never touch the DB: the async handlers ignore the `session` argument
# (a sentinel object suffices). The DB-in-transaction proof lives in the
# integration tier (`test_transactions_transitions.py`).

_SESSION = object()  # opaque session sentinel; async handlers below never use it


async def test_dispatch_calls_async_handler_with_session_and_event() -> None:
    received: list[tuple[object, DomainEvent]] = []

    async def _h(session: object, event: _EvtA) -> None:
        received.append((session, event))

    subscribe_async(_EvtA, _h)
    evt = _EvtA(value=7)
    await dispatch(_SESSION, evt)  # type: ignore[arg-type]

    assert received == [(_SESSION, evt)]
    assert received[0][1] is evt


async def test_dispatch_runs_sync_before_async_observable() -> None:
    # A shared order list proves ALL sync subscribers fire before ANY async one
    # (load-bearing: the BudgetThresholdEvent spy is SYNC and must capture an
    # event republished by the async detector).
    order: list[str] = []
    subscribe(_EvtA, lambda _e: order.append("sync"))

    async def _async(_s: object, _e: _EvtA) -> None:
        order.append("async")

    subscribe_async(_EvtA, _async)
    await dispatch(_SESSION, _EvtA())  # type: ignore[arg-type]

    assert order == ["sync", "async"]


async def test_multiple_async_handlers_fire_in_registration_order() -> None:
    order: list[str] = []

    async def _h1(_s: object, _e: _EvtA) -> None:
        order.append("h1")

    async def _h2(_s: object, _e: _EvtA) -> None:
        order.append("h2")

    subscribe_async(_EvtA, _h1)
    subscribe_async(_EvtA, _h2)
    await dispatch(_SESSION, _EvtA())  # type: ignore[arg-type]

    assert order == ["h1", "h2"]


async def test_subscribe_async_is_idempotent() -> None:
    calls: list[int] = []

    async def _h(_s: object, _e: _EvtA) -> None:
        calls.append(1)

    subscribe_async(_EvtA, _h)
    subscribe_async(_EvtA, _h)  # same (type, handler) → no-op
    await dispatch(_SESSION, _EvtA())  # type: ignore[arg-type]

    assert calls == [1]


async def test_dispatch_async_is_by_exact_type() -> None:
    calls: list[DomainEvent] = []

    async def _h(_s: object, e: _EvtA) -> None:
        calls.append(e)

    subscribe_async(_EvtA, _h)
    await dispatch(_SESSION, _EvtB())  # type: ignore[arg-type]

    assert calls == []


async def test_dispatch_async_no_fanout_to_subtypes() -> None:
    # Symmetric to the sync `test_no_fanout_to_subtypes`: the async registry is
    # keyed on `type(event)` exactly, so a parent-type subscriber stays silent on
    # a subtype event.
    calls: list[DomainEvent] = []

    async def _h(_s: object, e: _EvtA) -> None:
        calls.append(e)

    subscribe_async(_EvtA, _h)
    await dispatch(_SESSION, _SubEvtA())  # type: ignore[arg-type]

    assert calls == []


async def test_dispatch_propagates_raising_async_handler() -> None:
    sync_calls: list[str] = []
    subscribe(_EvtA, lambda _e: sync_calls.append("sync"))

    async def _boom(_s: object, _e: _EvtA) -> None:
        raise ValueError("async boom")

    subscribe_async(_EvtA, _boom)

    with pytest.raises(ValueError, match="async boom"):
        await dispatch(_SESSION, _EvtA())  # type: ignore[arg-type]
    # The sync subscriber ran before the async one raised (order guarantee).
    assert sync_calls == ["sync"]


async def test_dispatch_without_async_subscriber_runs_sync_only() -> None:
    # `dispatch` with no async subscriber ≈ `publish` (sync subscribers only).
    received: list[DomainEvent] = []
    subscribe(_EvtA, received.append)

    await dispatch(_SESSION, _EvtA(value=3))  # type: ignore[arg-type]

    assert len(received) == 1
    assert received[0].value == 3  # type: ignore[attr-defined]


async def test_clear_subscribers_empties_async_registry() -> None:
    # The autouse fixture relies on `clear_subscribers` wiping BOTH registries —
    # load-bearing for the threshold scenarios (a leaked async detector across
    # tests would corrupt their `captured` lists).
    calls: list[int] = []

    async def _h(_s: object, _e: _EvtA) -> None:
        calls.append(1)

    subscribe_async(_EvtA, _h)
    clear_subscribers()
    await dispatch(_SESSION, _EvtA())  # type: ignore[arg-type]

    assert calls == []  # the cleared async handler never fires
