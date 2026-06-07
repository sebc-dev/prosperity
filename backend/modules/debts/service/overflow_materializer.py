"""Overflow debt materializer (E11 / S11.3): the mini-bus handlers for F10.

Three async handlers, wired at the composition root (`backend/main.py`), all
**transaction-agnostic** (ADR 0015 — `flush`/`execute` only, never a commit; they
run INSIDE the request transaction via `dispatch`, so a failure rolls the
confirm/void/edit back):

* `materialize_overflow` (`TransactionConfirmedEvent`, P11.3.2) — derives the
  scalars (expense total, ordered-window budget remaining, members + quote-parts),
  calls the pure `DebtCalculator.compute_for_overflow`, then **upserts** the
  `shared_account_overflow` debts and **prunes** the rows gone stale — idempotently
  (the `uq_debts_overflow_active` partial unique backs `ON CONFLICT DO UPDATE`).
* `remove_overflow_on_void` (`TransactionVoidedEvent`, P11.3.3) — deletes the
  tx's overflow debts.
* `rematerialize_overflow_on_edit` (`TransactionEditableFieldsChangedEvent`,
  P11.3.4 + S11.4 P11.4.4) — re-runs the materialisation path when
  `debt_generation_override` OR `category_id` (reclassement) changed, plus the
  period neighbours whose ordered-window remaining the reclassement shifts.
* `recompute_overflow_on_budget_event` (`BudgetCreatedEvent`/`BudgetUpdatedEvent`,
  S11.4 P11.4.1) — a budget that appears / changes / is archived re-materialises
  the overflow of **all** the past transactions it covers, idempotently, REUSING
  the same per-tx path (`_materialize_for_tx`) — never a second materialisation
  voie. Emits a server-only audit trace (P11.4.2) bounding the recompute cost.

Layering (ADR 0005, contract `2-debts`): `debts` sits *above* `transactions`,
`budget` and `accounts`, so it imports their `.public` surfaces directly
(`get_transaction`/events, `resolve_overflow_context`/budget events/enumerators,
`shared_account_members_with_ratios`) — the `debts → budget.public` arc is the
first import of `budget` by `debts`, covered by the `2-debts` `ignore_imports`
block (the `budget.events` second-hop is not forbidden — it imports only
`shared.events`). The transaction aggregate is
duck-typed via a `Protocol` (gabarit `threshold_detector._ConfirmedEvent`) so the
service never names `transactions.domain.Transaction` (a forbidden internal),
while still being strict-typed.

**Exclusivité d'origine** (AC opposable): EVERY write here filters
`origin = 'shared_account_overflow'` (the upsert's `index_where`, the prune's and
the void's `WHERE`), so a co-present `personal_share_request` debt is never
touched.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, text, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.public import shared_account_members_with_ratios
from backend.modules.budget.public import (
    BudgetCreatedEvent,
    BudgetUpdatedEvent,
    list_overflow_budget_ids_for_categories,
    list_overflow_recompute_tx_ids,
    resolve_overflow_context,
)
from backend.modules.debts.domain import (
    Debt as DebtDomain,
)
from backend.modules.debts.domain import (
    DebtCalculator,
    DebtGenerationOverride,
    OverflowMember,
)
from backend.modules.debts.models import Debt as DebtModel
from backend.modules.transactions.public import (
    TransactionConfirmedEvent,
    TransactionEditableFieldsChangedEvent,
    TransactionState,
    TransactionVoidedEvent,
    get_transaction,
)
from backend.shared.money import Money

logger = logging.getLogger(__name__)

_OVERFLOW = "shared_account_overflow"


class _OverflowSplit(Protocol):
    """Duck-typing surface of a split — PURELY STATIC (no `transactions.domain`
    import, contract `2-debts`). `leg_role` is read-only `str` (the concrete
    `LegRole` Literal is a subtype)."""

    @property
    def amount(self) -> Money: ...
    @property
    def category_id(self) -> UUID | None: ...
    @property
    def leg_role(self) -> str: ...


class _OverflowTx(Protocol):
    """Duck-typing surface of the transaction aggregate the materializer reads
    (gabarit `threshold_detector._ConfirmedEvent`): the concrete
    `transactions.domain.Transaction` satisfies it structurally, so `debts` never
    names a forbidden `transactions` internal."""

    @property
    def id(self) -> UUID: ...
    @property
    def account_id(self) -> UUID: ...
    @property
    def date(self) -> date: ...
    @property
    def created_by(self) -> UUID: ...
    @property
    def debt_generation_override(self) -> DebtGenerationOverride: ...
    @property
    def splits(self) -> Sequence[_OverflowSplit]: ...


def _classification_total_and_categories(tx: _OverflowTx) -> tuple[Money, set[UUID]]:
    """`(expense_total, category_ids)` of the classification legs (D5). PURE —
    operates on the domain object, not the DB, so it is unit-testable.

    `expense_total` = sum of the `leg_role == "classification"` legs (the funding
    leg is excluded); a transfer (no classification leg) yields `Money(0, …)` ⇒
    the caller short-circuits to no overflow. `category_ids` = the non-NULL
    `category_id`s of those legs (canonical form: exactly the spend leg).
    """
    legs = [s for s in tx.splits if s.leg_role == "classification"]
    category_ids = {s.category_id for s in legs if s.category_id is not None}
    if not legs:
        # Transfer / no classification leg → currency is irrelevant (amount 0
        # short-circuits the caller); mirror the tx currency when a split exists.
        base_ccy = tx.splits[0].amount.currency if tx.splits else "EUR"
        return Money(0, base_ccy), category_ids  # type: ignore[arg-type]
    total = legs[0].amount
    for split in legs[1:]:
        total = total + split.amount  # IncompatibleCurrencyError if mixed (V1 mono-devise)
    return total, category_ids


async def _upsert_and_prune(
    session: AsyncSession, *, tx_id: UUID, debts: Sequence[DebtDomain]
) -> None:
    """Upsert the overflow `debts` of `tx_id`, then prune the rows gone stale (D3/D4).

    `ON CONFLICT (source_transaction_id, from_user_id, to_user_id, origin)
    WHERE origin = '…' DO UPDATE` targets the partial unique `uq_debts_overflow_active`
    by `index_elements + index_where` (a partial index is not a named constraint
    referenceable by `constraint=`). The complementary DELETE removes the overflow
    rows of the tx NOT in the freshly-computed `(from, to)` set — a member who no
    longer owes anything (override → `force_no_debt`, base under the rounding
    threshold, budget gone) would otherwise leave a phantom debt. Both writes
    filter `origin = '…'` ⇒ a co-present `personal_share_request` debt is untouched.
    """
    kept: set[tuple[UUID, UUID]] = set()
    for d in debts:
        await session.execute(
            pg_insert(DebtModel)
            .values(
                from_user_id=d.from_user_id,
                to_user_id=d.to_user_id,
                amount_cents=d.amount.amount_cents,
                currency=d.amount.currency,
                account_id=d.account_id,
                source_transaction_id=d.source_transaction_id,
                origin=d.origin,
                share_ratio=d.share_ratio,
            )
            .on_conflict_do_update(
                index_elements=["source_transaction_id", "from_user_id", "to_user_id", "origin"],
                index_where=text("origin = 'shared_account_overflow'"),
                set_={"amount_cents": d.amount.amount_cents, "share_ratio": d.share_ratio},
            )
        )
        kept.add((d.from_user_id, d.to_user_id))

    stmt = delete(DebtModel).where(
        DebtModel.source_transaction_id == tx_id,
        DebtModel.origin == _OVERFLOW,
    )
    if kept:
        stmt = stmt.where(tuple_(DebtModel.from_user_id, DebtModel.to_user_id).notin_(list(kept)))
    await session.execute(stmt)


async def _recompute_overflow(
    session: AsyncSession, *, tx: _OverflowTx, members: Sequence[tuple[UUID, Decimal]]
) -> None:
    """Derive the scalars, project the overflow debts (S11.2), upsert + prune."""
    expense_total, category_ids = _classification_total_and_categories(tx)
    if expense_total.amount_cents <= 0:
        # Transfer / no spend leg → no overflow; still prune any stale rows.
        await _upsert_and_prune(session, tx_id=tx.id, debts=[])
        return

    ctx = (
        await resolve_overflow_context(
            session,
            category_ids=category_ids,
            account_id=tx.account_id,
            as_of=tx.date,
            before=(tx.date, tx.id),  # ordered window (D7): remaining BEFORE this tx
        )
        if category_ids
        else None
    )
    # D9: always call the domain. Without a covering budget,
    # `budget_remaining_before = None` → base = expense_total (≡ force_full_debt).
    remaining_before = Money(ctx.remaining_before_cents, ctx.currency) if ctx else None  # type: ignore[arg-type]
    debts = DebtCalculator.compute_for_overflow(
        expense_total=expense_total,
        budget_remaining_before=remaining_before,
        account_members=[OverflowMember(user_id=u, share_ratio=r) for u, r in members],
        payer_user_id=tx.created_by,
        override=tx.debt_generation_override,
        source_transaction_id=tx.id,
        source_account_id=tx.account_id,
    )
    await _upsert_and_prune(session, tx_id=tx.id, debts=debts)


async def _materialize_for_tx(session: AsyncSession, *, tx_id: UUID) -> None:
    """Shared path of `confirmed` (P11.3.2) and override edit (P11.3.4)."""
    tx = await get_transaction(session, tx_id=tx_id)
    if tx is None or tx.state is not TransactionState.CONFIRMED:
        return  # defensive: tx voided/absent between dispatch and handler
    members = await shared_account_members_with_ratios(session, account_id=tx.account_id)
    if members is None:
        return  # personal / archived / unknown account → never an overflow debt
    await _recompute_overflow(session, tx=tx, members=members)


async def materialize_overflow(session: AsyncSession, event: TransactionConfirmedEvent) -> None:
    """Mini-bus handler: materialise the overflow debts of a confirmed tx (P11.3.2)."""
    await _materialize_for_tx(session, tx_id=event.transaction_id)


async def remove_overflow_on_void(session: AsyncSession, event: TransactionVoidedEvent) -> None:
    """`void` → delete the tx's `shared_account_overflow` debts (P11.3.3).

    Filters the origin → `personal_share_request` debts of the same tx are left
    intact (AC opposable). The FK `debts.source_transaction_id` is `ON DELETE
    CASCADE`, but `void` is a state transition (it does NOT delete the tx), so the
    cascade never fires — this handler is required.
    """
    await session.execute(
        delete(DebtModel).where(
            DebtModel.source_transaction_id == event.transaction_id,
            DebtModel.origin == _OVERFLOW,
        )
    )


async def rematerialize_overflow_on_edit(
    session: AsyncSession, event: TransactionEditableFieldsChangedEvent
) -> None:
    """Editable-field change post-confirm → re-materialise the overflow.

    Reacts to `debt_generation_override` (S11.3) AND, since S11.4 (P11.4.4), to
    `category_id` (reclassement F10): a category edit moves the tx to a different
    covering budget (or out of any), so its overflow is recomputed — AND the
    **period neighbours** of BOTH the former and the new covering budget (their
    ordered-window `(date, id)` remaining is shifted) are recomputed too. Anything
    else is a no-op (avoids churn). All recomputes REUSE the idempotent P11.3.2 path
    (`_materialize_for_tx` / `recompute_overflow_for_budget`), never a second voie
    (ADR 0002 — the upsert + prune guarantees no duplicate across passes).

    The former categories travel on `event.previous_category_ids` — the one value
    the subscriber cannot re-read (the old category is gone post-edit, P11.4.3)."""
    if event.changed_fields & {"debt_generation_override", "category_id"}:
        await _materialize_for_tx(session, tx_id=event.transaction_id)

    if "category_id" not in event.changed_fields:
        return
    # Reclassement: recompute the neighbours of every budget concerned by the FORMER
    # (`previous_category_ids`) AND the new category, on the tx's account. The tx
    # itself is re-included idempotently by `recompute_overflow_for_budget` of the
    # new budget — `_upsert_and_prune` dedups. If the new category is unbudgeted, the
    # tx re-resolves « sans budget » (base = M) via `_materialize_for_tx` above.
    tx = await get_transaction(session, tx_id=event.transaction_id)
    if tx is None:
        return
    _, new_category_ids = _classification_total_and_categories(tx)
    budget_ids: set[UUID] = set()
    for category_ids in (event.previous_category_ids, new_category_ids):
        budget_ids.update(
            await list_overflow_budget_ids_for_categories(
                session, category_ids=set(category_ids), account_id=tx.account_id
            )
        )
    for budget_id in budget_ids:
        await recompute_overflow_for_budget(session, budget_id=budget_id)


# --- Budget reclassement (S11.4 P11.4.1 / P11.4.2) --------------------------


async def recompute_overflow_for_budget(session: AsyncSession, *, budget_id: UUID) -> int:
    """Re-materialise the overflow of every tx covered by `budget_id`, REUSING the
    idempotent S11.3 path (`_materialize_for_tx` per tx, D5) — never a second
    materialisation voie. Returns the number of txs traversed (audit counter,
    P11.4.2).

    MVP: NO optimisation (note implémenteur). A `BudgetCreatedEvent` may sweep many
    past transactions; the async batch split is deferred to V1.5 — the audit trace
    is the instrumentation that bounds the cost.
    """
    tx_ids = await list_overflow_recompute_tx_ids(session, budget_id=budget_id)
    for tx_id in tx_ids:
        await _materialize_for_tx(session, tx_id=tx_id)
    return len(tx_ids)


async def recompute_overflow_on_budget_event(
    session: AsyncSession, event: BudgetCreatedEvent | BudgetUpdatedEvent
) -> None:
    """Mini-bus handler (S11.4): a budget created / updated / archived re-materialises
    the overflow of the past transactions it covers. Idempotent (upsert S11.3).

    P11.4.2 audit trace: a server-only structured log (no table, no migration), the
    gabarit of the `budget`/`consumption` logs. WITHOUT PII — only `budget_id` (an
    opaque UUID) and the recomputed-tx counter, never an email / label / amount. The
    trace is ALWAYS written (even at count 0) so the sweep is observable.
    """
    count = await recompute_overflow_for_budget(session, budget_id=event.budget_id)
    logger.info(
        "debts_recomputed_on_budget_event budget_id=%s transactions_recomputed_count=%d",
        event.budget_id,
        count,
    )
