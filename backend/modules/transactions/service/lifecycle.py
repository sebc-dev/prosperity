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
subscriber that raises — fails. The transition, the event `publish`, and the
persistence all share the **same** transaction opened by the request dependency,
so atomicity is free.

The S05.4 in-process mini-bus runs **inside the caller's transaction, before
`get_db` commits**. `confirm` uses `dispatch` (sync + async channels): the E08
budget threshold detector subscribes on the async channel and does DB I/O in this
same transaction. `void` stays on `publish` (no async subscriber — `void` is not
handled by E08). The concrete event types live in `transactions.events` (never in
`shared`, which only owns the `DomainEvent` base — import-linter contract #3).

Internal to the transactions module (import-linter contract `2-transactions`);
cross-module callers go through `backend.modules.transactions.public`. No
cross-module import is added in S07.4 (the transfer predicate is structural,
D6): validating that each `account_id` belongs to the household is deferred to
the route boundary S07.5 (D13).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.transactions import domain, events
from backend.modules.transactions.models import Split as SplitModel
from backend.modules.transactions.models import Transaction as TxModel
from backend.shared.events import dispatch, publish
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
                # Mapped[str] → LegRole (gabarit debt_generation_override) ;
                # valeur autoritative du SGBD, le mapper ne re-dérive pas.
                leg_role=s.leg_role,  # type: ignore[arg-type]
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


# --- Transitions + events (P07.4.2) -----------------------------------------


async def transition_to_planned(session: AsyncSession, *, tx_id: UUID) -> domain.Transaction:
    """`draft → planned`, refusing an unbalanced transaction (AC).

    `assert_transition` runs **before** the zero-sum check (the state-machine
    guard is the first gate). Flush-only (ADR 0015).
    """
    tx, splits = await _load_aggregate(session, tx_id)
    agg = _to_domain(tx, splits)
    domain.assert_transition(agg.state, domain.TransactionState.PLANNED)
    domain.assert_zero_sum(agg)  # AC: refuse if sum(splits) != 0
    tx.state = domain.TransactionState.PLANNED.value
    await session.flush()
    return _to_domain(tx, splits)


async def transition_to_confirmed(session: AsyncSession, *, tx_id: UUID) -> domain.Transaction:
    """`planned → confirmed`: zero-sum + every expense split categorised (D4).

    `model_copy(update={"state": CONFIRMED})` would bypass the validator (domain
    contract), so the service calls the standalone helpers explicitly. A mixed
    currency surfaces `IncompatibleCurrencyError` (outside `TransactionError`),
    propagated to the S07.5 boundary which catches both families. `dispatch` runs
    **after** the flush but **before** `get_db` commits → same transaction: it
    replays the sync subscribers (spies) *and* awaits the async ones (the E08
    budget threshold detector), so a subscriber that raises rolls everything back.
    Flush-only.
    """
    tx, splits = await _load_aggregate(session, tx_id)
    agg = _to_domain(tx, splits)
    domain.assert_transition(agg.state, domain.TransactionState.CONFIRMED)
    domain.assert_zero_sum(agg)
    domain.assert_expenses_categorized(agg)
    domain.assert_at_most_one_funding_leg(agg)  # D2 : ≤ 1 jambe funding (non-transfert)
    tx.state = domain.TransactionState.CONFIRMED.value
    tx.confirmed_at = datetime.now(UTC)
    await session.flush()
    # `dispatch` (not `publish`): the E08 budget threshold detector subscribes on
    # the ASYNC channel and recalculates consumption + an idempotent INSERT inside
    # this same transaction (a subscriber that raises rolls the confirm back).
    # `dispatch` subsumes `publish` (it replays the sync spies) — never both.
    await dispatch(
        session, events.TransactionConfirmedEvent(transaction_id=tx.id, account_id=tx.account_id)
    )
    return _to_domain(tx, splits)


async def void(session: AsyncSession, *, tx_id: UUID, reason: str) -> domain.Transaction:
    """`* → void` (terminal): mark voided and emit `TransactionVoidedEvent` (D7).

    `void` is reachable from any non-`void` state (ADR 0001). `reason` is carried
    by the event payload only — there is no `void_reason` column in V1; the audit
    trail follow-up rides on the first bus subscriber (E08), which must bound /
    sanitise `reason` (PII / log-injection) before logging or persisting it.
    `publish` runs after the flush, before `get_db` commits (same transaction).
    Flush-only (ADR 0015).
    """
    tx, splits = await _load_aggregate(session, tx_id)
    agg = _to_domain(tx, splits)
    domain.assert_transition(agg.state, domain.TransactionState.VOID)
    tx.state = domain.TransactionState.VOID.value
    tx.voided_at = datetime.now(UTC)
    await session.flush()
    publish(
        events.TransactionVoidedEvent(transaction_id=tx.id, account_id=tx.account_id, reason=reason)
    )
    return _to_domain(tx, splits)


# --- Post-confirmed editing (P07.4.3) ---------------------------------------


async def update_editable_fields(
    session: AsyncSession, *, tx_id: UUID, **fields: object
) -> domain.Transaction:
    """Edit allowed fields of a transaction; freeze the rest once `confirmed`.

    `check_mutation_allowed` is a no-op below `confirmed` (free editing in
    `draft`/`planned`); on a `confirmed` transaction any divergence on a field ∉
    `EDITABLE_AFTER_CONFIRMED` (including `splits`, compared by value) raises
    `ImmutableFieldViolation(field)`. Only the editable scalars are written back
    (so on a non-`confirmed` transaction a frozen field passed here is a silent
    no-op — neither error nor effect, consistent with the function's name).

    ⚠️ `model_copy(update=...)` bypasses Pydantic validation (the `Literal` of
    `debt_generation_override` included): an out-of-enum value is not rejected
    here. The route schema (S07.5) is the primary guard (422); the DB
    `CHECK ck_transactions_debt_generation_override` (migration 0010) is the
    fail-closed backstop — a flush with a bad value raises `IntegrityError`.
    Flush-only (ADR 0015).
    """
    tx, splits = await _load_aggregate(session, tx_id)
    old = _to_domain(tx, splits)
    unknown = set(fields) - set(domain.Transaction.model_fields)
    if unknown:
        raise ValueError(f"champs inconnus : {sorted(unknown)}")
    new = old.model_copy(update=fields)  # bypasses the validator (OK, D11)
    domain.check_mutation_allowed(old, new)  # raises ImmutableFieldViolation if frozen
    for key, raw in fields.items():
        if key in domain.EDITABLE_AFTER_CONFIRMED:  # write ONLY the editable scalars
            value = list(raw) if key == "tags" else raw  # type: ignore[call-overload]  # tags: tuple→list(ORM ARRAY)
            setattr(tx, key, value)
    await session.flush()
    return _to_domain(tx, splits)
