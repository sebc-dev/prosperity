"""Domain events published by the budget module (S08.3).

Concrete event type lives **here**, never in `backend.shared.events`: import-linter
contract #3 forbids `shared` from knowing `modules.*`, so `shared` only owns the
`DomainEvent` base. `budget` subclasses it. Re-exported via `budget.public` as a
surface discipline (ADR 0005) — the first (future) subscriber is `notifications`
(V1+, email/push via post-commit `BackgroundTasks`).

`BudgetThresholdEvent` is published **synchronously** (via `publish`), inside the
request transaction, by `service.threshold_detector` — exactly once per
`(budget, period window, threshold)` thanks to the idempotent INSERT into
`budget_threshold_alerts`. In V1 there is **no** subscriber, so `publish` is a
no-op (a test spy proves the channel).
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
