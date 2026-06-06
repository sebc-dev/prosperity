"""Domain events published by the transactions module (S07.4).

Concrete event types live **here**, not in `backend.shared.events`: import-linter
contract #3 forbids `shared` from knowing `modules.*`, so `shared` only owns the
`DomainEvent` base. `transactions` sits above `shared` in the layer graph and may
subclass it. The types are re-exported via `transactions.public` as a surface
discipline (ADR 0005): cross-module subscribers consume them only through
`transactions.public` and wire their handler at the composition root.

These events are published **inside the request transaction** (see
`service.lifecycle`), before `get_db` commits. Their subscriber status differs:

* `TransactionConfirmedEvent` — has an **async** subscriber (the E08 budget
  threshold detector, #21), dispatched via `dispatch`.
* `TransactionEditableFieldsChangedEvent` — foundation of the overflow
  re-materialisation (F10) ; its **async** `debts` subscriber is wired at the
  composition root in S11.3 (P11.3.4), so `update_editable_fields` emits it via
  `dispatch` (sync+async). Not yet subscribed in S11.1.
* `TransactionVoidedEvent` — no subscriber yet, emitted via `publish` (sync-only).

⚠️ `TransactionVoidedEvent.reason` is **unbounded free text** in V1 (no sink). The
first consumer MUST bound its length and sanitise it (PII / log-injection) before
logging or persisting — it is the only place a void `reason` survives, so it also
carries the ADR 0001 audit-trail concern for corrections.
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
class TransactionEditableFieldsChangedEvent(DomainEvent):
    """A field of `EDITABLE_AFTER_CONFIRMED` changed on a `confirmed` transaction.

    Foundation of the overflow re-materialisation (F10 ; S11.3, P11.3.4): the
    `debts` subscriber — wired at the composition root in S11.3, **never imported
    here** (ADR 0005) — re-materialises only when `debt_generation_override` (or
    another overflow-relevant field) appears in `changed_fields`, so it never
    over-triggers. Emitted on the mini-bus **async** channel (`dispatch`), inside
    the request transaction.

    `changed_fields` carries field **names only — never values** — deliberately,
    so no business datum or PII transits the bus (mirrors the `reason` caveat on
    `TransactionVoidedEvent`). The names are bounded to `EDITABLE_AFTER_CONFIRMED`
    (a finite set known at compile time) and built at the emission site in
    `update_editable_fields`. A subscriber needing the new value re-reads it from
    the session it is handed.
    """

    transaction_id: UUID
    changed_fields: frozenset[str]


@dataclass(frozen=True, slots=True)
class TransactionVoidedEvent(DomainEvent):
    """A transaction reached the terminal `void` state.

    `reason` is unbounded in V1 — see the module docstring; the E08 subscriber
    bounds/sanitises it.
    """

    transaction_id: UUID
    account_id: UUID
    reason: str
