"""Transaction lifecycle service (S07.4).

Wires the immutable aggregate (S07.3) onto the ORM (S07.2): create a draft, add
or remove splits while it is a draft, transition through the state machine
(`planned`/`confirmed`/`void`), edit the post-confirmed allowed fields, and emit
the matching `DomainEvent` on each transition. Each function loads the ORM rows,
builds the pure `domain.Transaction` via the **validating** constructor (mapper
`_to_domain`), runs the domain rule (state machine / zero-sum / checker), then
re-writes the scalar columns and **flushes — never commits**: `get_db` owns the
transaction boundary (ADR 0015).

This is an ordinary, transaction-agnostic business service — *not* a
security-critical side effect: ADR 0015's commit-inside-service derogation
deliberately does **not** apply (the criterion "the client must not be able to
undo the side effect by triggering an exception" is not met). On the contrary we
*want* the whole request to roll back if any step — including a future event
subscriber that raises — fails.

Internal to the transactions module (import-linter contract `2-transactions`);
cross-module callers go through `backend.modules.transactions.public`. No
cross-module import is added in S07.4 (the transfer predicate is structural,
D6): validating that each `account_id` belongs to the household is deferred to
the route boundary S07.5 (D13).

P07.4.1 lays the draft-creation + split-editing surface; transitions/events
(P07.4.2) and post-confirmed editing (P07.4.3) extend this same module.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.transactions import domain
from backend.modules.transactions.models import Split as SplitModel
from backend.modules.transactions.models import Transaction as TxModel
from backend.shared.money import Money


class TransactionNotFoundError(domain.TransactionError):
    """A transaction id does not resolve to a row (D8).

    "Not found" is a persistence concern, not a pure invariant, so it lives in
    the service — but it subclasses `domain.TransactionError` to keep the family
    unified (a single `except TransactionError` maps to 404 at the boundary).
    The id is carried by the typed `transaction_id` attribute (safe channel),
    not only in `str(exc)`.
    """

    code: ClassVar[str] = "transaction_not_found"

    def __init__(self, transaction_id: UUID) -> None:
        super().__init__(f"transaction introuvable : {transaction_id}")
        self.transaction_id = transaction_id


class SplitNotFoundError(domain.TransactionError):
    """A split id does not resolve to a row of the loaded transaction (D8).

    Distinct from `TransactionNotFoundError`: reusing the latter for a missing
    split would mislabel a `split_id` as a `transaction_id` (and map S07.5 onto a
    bogus "transaction not found" 404). Its own `code`/`split_id` keep the signal
    honest.
    """

    code: ClassVar[str] = "split_not_found"

    def __init__(self, split_id: UUID) -> None:
        super().__init__(f"split introuvable : {split_id}")
        self.split_id = split_id


# --- Mapping ORM ↔ domain (private, D11) ------------------------------------


def _to_domain(tx: TxModel, splits: Sequence[SplitModel]) -> domain.Transaction:
    """Build the domain aggregate via the VALIDATING constructor (D11).

    Loading through the constructor (not `model_construct`) re-checks the
    invariant — a `confirmed` row that became unbalanced in the DB would raise on
    read, which is the wanted defense-in-depth signal. `Money(amount_cents,
    currency) ↔ (split.amount_cents, split.currency)`; `tuple(tx.tags)` for the
    domain's immutable `tags`.
    """
    return domain.Transaction(
        id=tx.id,
        account_id=tx.account_id,
        date=tx.date,
        state=domain.TransactionState(tx.state),
        payee=tx.payee,
        created_by=tx.created_by,
        splits=tuple(
            domain.Split(
                account_id=s.account_id,
                category_id=s.category_id,
                amount=Money(s.amount_cents, s.currency),  # type: ignore[arg-type]
            )
            for s in splits
        ),
        category_id=tx.category_id,
        description=tx.description,
        tags=tuple(tx.tags),
        debt_generation_override=tx.debt_generation_override,  # type: ignore[arg-type]
        share_request_id=tx.share_request_id,
    )


async def _load_aggregate(session: AsyncSession, tx_id: UUID) -> tuple[TxModel, list[SplitModel]]:
    """Load the `Transaction` row + its splits (ordered by `id`), or raise.

    `order_by(id)` gives a deterministic split order so `check_mutation_allowed`
    compares structurally (S07.3). Raises `TransactionNotFoundError` if the id is
    unknown. NOTE (D8 non-disclosure): this does NOT collapse inaccessible→404 —
    the household-membership filter lives at the route boundary (S07.5), which
    must make "unknown" and "inaccessible" indistinguishable (a uniform 404,
    gabarit `accounts.get_accessible`) to avoid a tx-id enumeration oracle.
    """
    tx = await session.get(TxModel, tx_id)
    if tx is None:
        raise TransactionNotFoundError(tx_id)
    splits = (
        (
            await session.execute(
                select(SplitModel).where(SplitModel.transaction_id == tx_id).order_by(SplitModel.id)
            )
        )
        .scalars()
        .all()
    )
    return tx, list(splits)


# --- Draft creation + split editing (P07.4.1) -------------------------------


async def create_draft(
    session: AsyncSession,
    *,
    account_id: UUID,
    by_user_id: UUID,
    date: dt.date | None = None,
) -> domain.Transaction:
    """Create a `draft` transaction with 0 split, atomically (D9).

    `created_by = by_user_id` is server-derived at the route boundary (S07.5),
    **never** from a client body (same discipline as `owner_id`, S05.3). `date`
    defaults to today (the column is NOT NULL). Flushes to surface the PK; does
    **not** commit (`get_db` owns the boundary, ADR 0015).
    """
    tx = TxModel(
        account_id=account_id,
        created_by=by_user_id,
        date=date or datetime.now(UTC).date(),
        state=domain.TransactionState.DRAFT.value,
    )
    session.add(tx)
    await session.flush()  # surface PK here; no commit (get_db owns it, ADR 0015)
    return _to_domain(tx, [])


async def add_split(  # noqa: PLR0913 — split fields are a flat, keyword-only API
    session: AsyncSession,
    *,
    tx_id: UUID,
    account_id: UUID,
    amount_cents: int,
    currency: str,
    category_id: UUID | None = None,
) -> domain.Transaction:
    """Append a split to a `draft` transaction (D5).

    Splits are editable ONLY while `draft` (ADR 0001: correcting a non-draft
    transaction goes through `void` + recreate, never a reopening). Any other
    state raises `ImmutableFieldViolation("splits")`. Flush-only (ADR 0015).

    ⚠️ `account_id` is persisted AS-IS — its membership of the household is NOT
    validated here in V1 (D6/D13: the service imports no `accounts.public`). The
    route boundary (S07.5) must validate it before calling, otherwise a foreign
    `account_id` would inflate the distinct-account count → `is_transfer` True →
    the expense escapes `assert_expenses_categorized` (see `domain.is_transfer`).
    """
    tx, splits = await _load_aggregate(session, tx_id)
    if tx.state != domain.TransactionState.DRAFT.value:
        raise domain.ImmutableFieldViolation("splits")
    split = SplitModel(
        transaction_id=tx_id,
        account_id=account_id,
        amount_cents=amount_cents,
        currency=currency,
        category_id=category_id,
    )
    session.add(split)
    await session.flush()
    return _to_domain(tx, [*splits, split])


async def remove_split(session: AsyncSession, *, tx_id: UUID, split_id: UUID) -> domain.Transaction:
    """Remove a split from a `draft` transaction (D5).

    `draft`-only, like `add_split`. Raises `SplitNotFoundError` if the split does
    not belong to the transaction (D8). Flush-only (ADR 0015).
    """
    tx, splits = await _load_aggregate(session, tx_id)
    if tx.state != domain.TransactionState.DRAFT.value:
        raise domain.ImmutableFieldViolation("splits")
    target = next((s for s in splits if s.id == split_id), None)
    if target is None:
        raise SplitNotFoundError(split_id)
    await session.delete(target)
    await session.flush()
    return _to_domain(tx, [s for s in splits if s.id != split_id])
