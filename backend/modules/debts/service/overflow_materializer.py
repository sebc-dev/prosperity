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
  P11.3.4) — re-runs the materialisation path when `debt_generation_override`
  changed.

Layering (ADR 0005, contract `2-debts`): `debts` sits *above* `transactions`,
`budget` and `accounts`, so it imports their `.public` surfaces directly
(`get_transaction`/events, `resolve_overflow_context`, `shared_account_members_with_ratios`)
— the `debts → budget.public` arc is the first import of `budget` by `debts`,
covered by the `2-debts` `ignore_imports` block. The transaction aggregate is
duck-typed via a `Protocol` (gabarit `threshold_detector._ConfirmedEvent`) so the
service never names `transactions.domain.Transaction` (a forbidden internal),
while still being strict-typed.

**Exclusivité d'origine** (AC opposable): EVERY write here filters
`origin = 'shared_account_overflow'` (the upsert's `index_where`, the prune's and
the void's `WHERE`), so a co-present `personal_share_request` debt is never
touched.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, text, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.public import shared_account_members_with_ratios
from backend.modules.budget.public import resolve_overflow_context
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
    """Editable-field change post-confirm → re-materialise the overflow IF
    `debt_generation_override` changed (else no-op, avoids churn). The recompute
    is idempotent (ADR 0002) via the P11.3.2 path (P11.3.4).

    Scope V1: ONLY `debt_generation_override` triggers a recompute. `category_id`
    is also editable post-confirm and IS overflow-relevant (it picks the covering
    budget, hence `remaining_before`, hence the base) — but re-materialising on a
    category edit (and re-materialising the period *neighbours* whose remaining it
    shifts) is deferred to S11.4 (reclassement). Until then a category edit leaves a
    stale overflow amount. Tracked in `CONTEXT.md` §Excédent _Limite V1_ + roadmap
    E11 §S11.4."""
    if "debt_generation_override" not in event.changed_fields:
        return
    await _materialize_for_tx(session, tx_id=event.transaction_id)
