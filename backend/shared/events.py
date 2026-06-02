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
transaction, so a slow I/O would hold DB locks open (contention/DoS).

Two channels coexist:

* the **synchronous** one (`subscribe`/`publish`) — handlers are `(event) -> None`,
  cannot `await`. This is the original S05.4 bus; spies and no-op-V1 subscribers
  live here.
* the **asynchronous** one (`subscribe_async`/`dispatch`) — handlers are
  `(session, event) -> await`, so they can do DB I/O **inside the request
  transaction** (recalc + idempotent INSERT for E08 budget threshold alerts).
  `dispatch(session, event)` runs the sync subscribers first (it **calls
  `publish`** internally), then awaits the async ones in registration order.

⚠️ `dispatch` **subsumes** `publish`: on a given event call **either** `publish`
(fully-sync path, e.g. `void`) **or** `dispatch` (sync+async path, e.g. `confirm`),
**never both** — otherwise the sync subscribers fire twice.

The E08 subscriber registers **once at application startup** (in the FastAPI
`lifespan`, idempotent) — `subscribe_async` dedups a repeated `(type, handler)`,
so a cross-import re-registration in tests cannot double-dispatch.
`clear_subscribers`/`unsubscribe` are test-only hooks and must never be called in
production (they would silently drop subscriptions).

This module imports **nothing** from `backend.modules.*` (import-linter
contract #3) — it only knows the `DomainEvent` base; the concrete event types
live in the publishing module (e.g. `accounts.events`, `budget.events`). It does
import `sqlalchemy.ext.asyncio.AsyncSession` (a third-party type, not a module)
to type the async handler's session argument.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


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

# Async-channel registry: exact event type → `(session, event) -> await`
# handlers, in registration order. Separate from `_subscribers` so the sync
# path is untouched (variance erased to `Any`; public signatures stay typed).
_async_subscribers: dict[type[DomainEvent], list[Callable[[Any, Any], Awaitable[None]]]] = {}


def subscribe[E: DomainEvent](event_type: type[E], handler: Callable[[E], None]) -> None:
    """Register `handler` for events of the **exact** type `event_type`."""
    _subscribers.setdefault(event_type, []).append(handler)


def subscribe_async[E: DomainEvent](
    event_type: type[E], handler: Callable[[AsyncSession, E], Awaitable[None]]
) -> None:
    """Register an ASYNC `handler` for the **exact** type `event_type` (IDEMPOTENT).

    Unlike `subscribe` (sync `(event)` handler), an async handler receives
    `(session, event)`: dispatched via `dispatch`, it runs **inside the request
    transaction** and may do `await` DB I/O (recalc + idempotent INSERT for E08).
    Register **once** at the composition root (FastAPI `lifespan`). IDEMPOTENT:
    re-registering the same `(event_type, handler)` is a no-op — robust to an app
    (re)start in tests without a `clear_subscribers` (the module's "registers once
    at application startup" contract).
    """
    handlers = _async_subscribers.setdefault(event_type, [])
    if handler not in handlers:
        handlers.append(handler)


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


async def dispatch(session: AsyncSession, event: DomainEvent) -> None:
    """Dispatch `event` on BOTH channels, inside the caller's transaction.

    Runs the **synchronous** subscribers first (via `publish(event)` — spies and
    the V1 no-op stay fully back-compatible), then `await`s each **async**
    subscriber `(session, event)` for the exact runtime type, in registration
    order. Synchronous w.r.t. the commit: an async handler that raises
    **propagates** to the caller (rolling the transaction back). No
    out-of-transaction side effect; no blocking/network I/O (mini-bus contract).

    ⚠️ `dispatch` SUBSUMES `publish`: on a single event call **either** `publish`
    (fully-sync) **or** `dispatch` (sync+async), **never both** — otherwise the
    sync subscribers are dispatched twice.
    """
    publish(event)
    for handler in _async_subscribers.get(type(event), ()):
        await handler(session, event)


def clear_subscribers() -> None:
    """Empty BOTH registries — **test-only** (the registries are global state)."""
    _subscribers.clear()
    _async_subscribers.clear()
