"""Budget threshold detector (S08.3): the mini-bus handler on transaction confirm.

`on_transaction_confirmed(session, event)` recomputes the consumption of every
budget concerned by a confirmed transaction (its split categories ∈ the budget's
subtree) and publishes a `BudgetThresholdEvent` **exactly once** per
`(budget, period window, threshold)` via an idempotent INSERT into
`budget_threshold_alerts` (the table is the source of truth — robust to server
restart and to the E13 write-upload replay).

It subscribes on the **async** channel (`shared.events.subscribe_async`), so it
runs INSIDE the request transaction (a failure rolls the confirm back). This puts
a *secondary* module (alerts) on the *critical path* of confirmation — a
deliberate availability arbitrage assumed in V1 (#127 D13): the atomicity of the
idempotent INSERT with the confirm is required (else a row-without-publish or
publish-without-row on replay), and a fail-hard makes any detector bug visible
rather than silent. A multi-household / high-concurrency future must revisit this
(post-commit offload with idempotence preserved).

Flush-only (ADR 0015 — `get_db` commits). `transactions ⊥ budget` (contract 1):
the splits' `category_id` are read via SQLAlchemy Core, never via
`transactions.models`. NOT handled: `TransactionVoidedEvent` (E08 non-objective —
an already-emitted alert is not cancelled by a void).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import column, select, table
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.budget.domain import compute_period_window, crossed_thresholds
from backend.modules.budget.events import BudgetThresholdEvent
from backend.modules.budget.models import Budget, BudgetThresholdAlert, Category
from backend.modules.budget.service.consumption import compute_consumption
from backend.shared.events import publish

# Lightweight Core handle on a PEER module's table (`transactions ⊥ budget`,
# contract 1). Read-only — NO import of `transactions.models` (gabarit
# `consumption._splits`). Only the columns this query touches are declared.
_splits = table("splits", column("transaction_id"), column("category_id"))


class _ConfirmedEvent(Protocol):
    """Duck-typing surface of the confirm event — PURELY STATIC (no
    `@runtime_checkable`/`isinstance`), so `budget` imports no concrete
    `TransactionConfirmedEvent` (peer module, #127 D5).

    The members are declared **read-only** (via `@property`) so the protocol
    matches a *frozen* dataclass whose fields are read-only — a plain
    `attr: UUID` would require a writable attribute and reject the frozen event.
    """

    @property
    def transaction_id(self) -> UUID: ...

    @property
    def account_id(self) -> UUID: ...


async def _split_category_ids(session: AsyncSession, tx_id: UUID) -> set[UUID]:
    """The distinct non-NULL `category_id`s of the transaction's splits."""
    rows = await session.execute(
        select(_splits.c.category_id).where(
            _splits.c.transaction_id == tx_id, _splits.c.category_id.is_not(None)
        )
    )
    return set(rows.scalars().all())


async def _concerned_budgets(session: AsyncSession, category_ids: set[UUID]) -> list[Budget]:
    """Active budgets whose category is an ancestor-or-self of a split category.

    A budget is concerned iff `split.category ∈ subtree(budget.category)` ⟺
    `budget.category` is an ancestor-or-self of a split category — so we walk
    UPWARD (recursive CTE, gabarit `categories._load_ancestor_chain`), then join
    active budgets. SELECTs the full `Budget` ENTITIES (populates the identity-map
    → no re-SELECT per `session.get` in the handler loop). Ordered `(created_at,
    id)` for determinism.

    Over-resolution is safe: the `publish` decision depends EXCLUSIVELY on
    `crossed_thresholds(consumed, amount)`, where `consumed` is recomputed by
    `compute_consumption` (re-filtered strictly by subtree, eligible accounts,
    window, currency, state) — never on membership of this candidate set. A
    falsely-candidate budget computes its true consumption (often 0 on the
    eligible accounts) → `crossed_thresholds` returns `[]` → no INSERT, no publish.
    This only WIDENS the candidate set, never triggers an effect by itself.
    """
    cat = Category.__table__
    anchor = (
        select(cat.c.id, cat.c.parent_id)
        .where(cat.c.id.in_(category_ids))
        .cte("concerned", recursive=True)
    )
    parent = cat.alias("p")
    chain = anchor.union(  # UNION (dedup) → terminates even on a corrupted tree
        select(parent.c.id, parent.c.parent_id).join(anchor, parent.c.id == anchor.c.parent_id)
    )
    stmt = (
        select(Budget)
        .where(Budget.category_id.in_(select(chain.c.id)), Budget.archived_at.is_(None))
        .order_by(Budget.created_at, Budget.id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def on_transaction_confirmed(session: AsyncSession, event: _ConfirmedEvent) -> None:
    """Detect threshold crossings for a confirmed transaction and publish once each.

    For every concerned budget, recompute the consumption (S08.2), then for each
    threshold its current consumption reaches, attempt the idempotent INSERT into
    `budget_threshold_alerts`; publish a `BudgetThresholdEvent` ONLY if the row is
    new (the `ON CONFLICT DO NOTHING ... RETURNING` distinguishes a real insert
    from a conflict, so a replay or a concurrent loser never double-publishes).
    """
    category_ids = await _split_category_ids(session, event.transaction_id)
    if not category_ids:
        return  # transfer / uncategorised → no budget concerned
    as_of = datetime.now(UTC).date()  # clock boundary, frozen for both computations
    for budget in await _concerned_budgets(session, category_ids):
        consumption = await compute_consumption(session, budget_id=budget.id, as_of=as_of)
        if consumption is None:  # defensive skip (budget purged concurrently); no assert
            continue
        period_start, _ = compute_period_window(budget.period_kind, budget.period_start, as_of)  # type: ignore[arg-type]
        for pct in crossed_thresholds(consumption.consumed_cents, budget.amount_cents):
            inserted = await session.execute(
                pg_insert(BudgetThresholdAlert)
                .values(budget_id=budget.id, period_start=period_start, threshold_pct=pct)
                .on_conflict_do_nothing(constraint="uq_budget_threshold_alerts_dedup")
                .returning(BudgetThresholdAlert.id)
            )
            if inserted.first() is not None:  # new row → first crossing of this threshold
                publish(  # SYNC publish (a sync spy captures it) — NOT dispatch
                    BudgetThresholdEvent(
                        budget_id=budget.id,
                        threshold_pct=pct,
                        consumed_cents=consumption.consumed_cents,
                        period_start=period_start,
                    )
                )
