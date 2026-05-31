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
    publish,
    subscribe,
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
