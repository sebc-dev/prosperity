"""Domain events published by the transactions module (S07.4).

Concrete event types live **here**, not in `backend.shared.events`: import-linter
contract #3 forbids `shared` from knowing `modules.*`, so `shared` only owns the
`DomainEvent` base. `transactions` sits above `shared` in the layer graph and may
subclass it. The types are re-exported via `transactions.public` as a surface
discipline (ADR 0005) for the first real subscriber — `budget` (E08, #21), which
reacts to confirmed transactions.

These events are published **synchronously, inside the request transaction**
(see `service.lifecycle`): in V1 there is no subscriber, so `publish` is a no-op.

⚠️ `TransactionVoidedEvent.reason` is **unbounded free text** in V1 (no sink). The
first consumer (E08) MUST bound its length and sanitise it (PII / log-injection)
before logging or persisting — it is the only place a void `reason` survives, so
it also carries the ADR 0001 audit-trail concern for corrections.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from backend.shared.events import DomainEvent


@dataclass(frozen=True, slots=True)
class TransactionConfirmedEvent(DomainEvent):
    """A transaction reached `confirmed` (zero-sum + expenses categorised)."""

    transaction_id: UUID
    account_id: UUID


@dataclass(frozen=True, slots=True)
class TransactionVoidedEvent(DomainEvent):
    """A transaction reached the terminal `void` state.

    `reason` is unbounded in V1 — see the module docstring; the E08 subscriber
    bounds/sanitises it.
    """

    transaction_id: UUID
    account_id: UUID
    reason: str
