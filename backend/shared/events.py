"""In-process domain-event mini-bus (glossary §Mini-bus).

A **synchronous**, in-process dispatcher that runs **inside the calling DB
transaction**: no thread, no post-commit hook, no eventual consistency. Business
modules (`accounts` here; `budget`/`notifications` later) publish typed
`DomainEvent`s without importing their consumers, which keeps the directional
import graph intact (ADR 0005).

⚠️ Dispatch happens **before** `get_db` commits. A handler that raises
**propagates** into the calling transaction (and rolls it back). A subscriber
must therefore have **no out-of-transaction side effect**, and must be
**bounded — no network I/O, no blocking call**: it runs inside the request's
transaction, so a slow I/O would hold DB locks open (contention/DoS). In V1 there
is **no subscriber**. Any future subscriber (E08) registers **once at application
startup** (idempotent); `clear_subscribers`/`unsubscribe` are test-only hooks and
must never be called in production (they would silently drop subscriptions).

This module imports **nothing** from `backend.modules.*` (import-linter
contract #3) — it only knows the `DomainEvent` base; the concrete event types
live in the publishing module (e.g. `accounts.events`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Immutable base of every domain event dispatched on the bus.

    Deliberately **field-less**: adding an attribute to the base would force a
    re-check of the `slots=True` ⇄ subclass-inheritance interplay
    (`accounts.events`). The payload lives in the concrete subtypes.
    """


# Module-level registry: exact event type → handlers, in registration order.
# Stored as Callable[[Any], None] (variance); the public signatures stay typed.
_subscribers: dict[type[DomainEvent], list[Callable[[Any], None]]] = {}


def subscribe[E: DomainEvent](event_type: type[E], handler: Callable[[E], None]) -> None:
    """Register `handler` for events of the **exact** type `event_type`."""
    _subscribers.setdefault(event_type, []).append(handler)


def unsubscribe[E: DomainEvent](event_type: type[E], handler: Callable[[E], None]) -> None:
    """Remove `handler` (no-op if absent). **Test-only.**"""
    handlers = _subscribers.get(event_type)
    if handlers and handler in handlers:
        handlers.remove(handler)


def publish(event: DomainEvent) -> None:
    """Dispatch `event` to its subscribers (exact runtime type), in order.

    With no subscriber: **no-op**. Synchronous — a handler that raises
    propagates to the caller.
    """
    for handler in _subscribers.get(type(event), ()):
        handler(event)


def clear_subscribers() -> None:
    """Empty the registry — **test-only** (the registry is global mutable state)."""
    _subscribers.clear()
