"""Domain events published by the budget module (S08.3 / S11.4).

Concrete event type lives **here**, never in `backend.shared.events`: import-linter
contract #3 forbids `shared` from knowing `modules.*`, so `shared` only owns the
`DomainEvent` base. `budget` subclasses it. Re-exported via `budget.public` as a
surface discipline (ADR 0005).

`BudgetThresholdEvent` is published **synchronously** (via `publish`), inside the
request transaction, by `service.threshold_detector` — exactly once per
`(budget, period window, threshold)` thanks to the idempotent INSERT into
`budget_threshold_alerts`. In V1 there is **no** subscriber, so `publish` is a
no-op (a test spy proves the channel); its first real subscriber is `notifications`
(V1+, email/push via post-commit `BackgroundTasks`).

`BudgetCreatedEvent` / `BudgetUpdatedEvent` (S11.4) are dispatched **async** (via
`dispatch`), inside the request transaction, by `service.budget_crud` on every
create / update / archive. Their first subscriber is the `debts` overflow
materializer (F10): a budget that appears, changes amount, or is archived
re-materialises the overflow of the past transactions it covers. The subscription
lives at the **composition root** (`backend/main.py`), NEVER here — `budget ⊥
debts` forbids `budget` from knowing its subscribers (ADR 0005).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from backend.shared.events import DomainEvent


@dataclass(frozen=True, slots=True)
class BudgetThresholdEvent(DomainEvent):
    """A budget crossed a consumption threshold (80 / 100 / 120 %) on its period.

    `consumed_cents` and `period_start` are the values **at the moment of the
    crossing** (the recalculated consumption and the current period window),
    carried so a future `notifications` subscriber needs no second read.
    """

    budget_id: UUID
    threshold_pct: int
    consumed_cents: int
    period_start: date


@dataclass(frozen=True, slots=True)
class BudgetCreatedEvent(DomainEvent):
    """A budget was just created (S11.4) → triggers the overflow re-materialisation
    (F10) of the past transactions it covers (subscriber `debts`, wired at the
    composition root, NEVER imported here: `budget ⊥ debts`).

    Carries identity **scalars** only (`budget_id`; `category_id` / `currency` are
    opaque UUID/code, no PII — mirror of `BudgetThresholdEvent`). It carries **no**
    period window: a budget is a recurring anchor (`compute_period_window`), not a
    single bound — the subscriber re-reads the budget by `budget_id` and sweeps
    **all** its windows, which is the whole point of reclassement (D-B).
    """

    budget_id: UUID
    category_id: UUID
    currency: str


@dataclass(frozen=True, slots=True)
class BudgetUpdatedEvent(DomainEvent):
    """A budget was modified (amount / contributors) or archived (S11.4) → same
    overflow re-materialisation as `BudgetCreatedEvent`, same doctrine and scalars.

    `category_id` / `period_*` are frozen post-creation (`budget_crud` D7), so only
    the **remaining** (amount) and the eligibility (contributors / archive) can
    shift — the budget's *current* state read by `budget_id` suffices to enumerate
    the transactions to recompute (D-C). Archiving removes coverage, so it is
    emitted as an update too (the projection must reflect the current state).
    """

    budget_id: UUID
    category_id: UUID
    currency: str
