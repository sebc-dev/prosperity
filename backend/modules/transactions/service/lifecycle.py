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
*want* the whole request to roll back if any step — including an event subscriber
that raises — fails. The transition, the event `dispatch`, and the persistence all
share the **same** transaction opened by the request dependency, so atomicity is
free.

The S05.4 in-process mini-bus runs **inside the caller's transaction, before
`get_db` commits**. `confirm` uses `dispatch` (sync + async channels): the E08
budget threshold detector subscribes on the async channel and does DB I/O in this
same transaction. `void` ALSO uses `dispatch` (S11.3, D14): the `debts` overflow
materializer subscribes async on `TransactionVoidedEvent` to delete the tx's
overflow debts, and an async handler only fires via `dispatch` (which subsumes
`publish`). The concrete event types live in `transactions.events` (never in
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
from backend.shared.events import dispatch
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
    trail follow-up rides on the first bus subscriber, which must bound /
    sanitise `reason` (PII / log-injection) before logging or persisting it.
    `dispatch` runs after the flush, before `get_db` commits (same transaction).

    `dispatch` (sync + async, like `transition_to_confirmed`), NOT `publish`: the
    S11.3 `debts` overflow materializer subscribes ASYNC on `TransactionVoidedEvent`
    to delete the tx's overflow debts, and an async handler only fires via
    `dispatch`. `dispatch` subsumes `publish` (it replays the sync spies), so this
    is back-compatible — there is no sync subscriber on this event, hence no
    double-dispatch. Atomicity: an async handler that raises rolls the void back
    (no voided tx left with phantom overflow debts — a wanted safety property).
    Flush-only (ADR 0015).
    """
    tx, splits = await _load_aggregate(session, tx_id)
    agg = _to_domain(tx, splits)
    domain.assert_transition(agg.state, domain.TransactionState.VOID)
    tx.state = domain.TransactionState.VOID.value
    tx.voided_at = datetime.now(UTC)
    await session.flush()
    await dispatch(
        session,
        events.TransactionVoidedEvent(
            transaction_id=tx.id, account_id=tx.account_id, reason=reason
        ),
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
    # S11.4 (reclassement F10): a `category_id` edit on a CONFIRMED tx must reach the
    # SOURCE OF TRUTH of consumption/overflow — the classification leg (E08.5), not
    # just the tx column. The budget consumption (`_consumption_filters`) and the
    # overflow (`_classification_total_and_categories`) read `splits.category_id` of
    # the classification leg, so propagating the new category there is what makes the
    # reclassement visible. Write BOUNDED to the category field — neither amount nor
    # split structure changes — so the double-entry (sum = 0) and ADR 0001 immutability
    # hold (note S11.4). GUARDED on `confirmed`: below it the splits are still edited
    # via `add_split`/`remove_split` and the header `tx.category_id` (which the create
    # route passes here, possibly NULL) is independent of the leg — propagating then
    # would clobber a categorised leg. A transfer (no classification leg) is a no-op.
    # V1 mono-category (canonical expense form): exactly ONE classification leg, so the
    # loop writes a single leg. A future multi-category form would be flattened to one
    # category here — out of scope V1, revisit with the split-level edit story.
    if old.state is domain.TransactionState.CONFIRMED and "category_id" in fields:
        for split in splits:
            if split.leg_role == "classification":
                # `fields["category_id"]` is typed `object` (**fields: object); the
                # caller passes the validated `UUID | None` from `TransactionPatch`.
                split.category_id = fields["category_id"]  # type: ignore[assignment]
    await session.flush()
    after = _to_domain(tx, splits)
    # S11.1: feeds the overflow re-materialisation (`debts`, wired at the
    # composition root in S11.3, P11.3.4). Emit ONLY on a `confirmed` transaction
    # AND when an editable field really changed — `changed` is the diff `old` vs
    # the domain REBUILT post-flush (`after`), so types are normalised
    # (`tags` is a `tuple` on both sides) and a `description="idem"` no-op emits
    # nothing. `dispatch` (sync+async, like `transition_to_confirmed`): the S11.3
    # subscriber does DB I/O inside THIS transaction. On a `confirmed` tx only
    # editable fields can diverge (frozen ones already raised above), so iterating
    # `EDITABLE_AFTER_CONFIRMED` is safe and exhaustive.
    if old.state is domain.TransactionState.CONFIRMED:
        changed = frozenset(
            field
            for field in domain.EDITABLE_AFTER_CONFIRMED
            if getattr(old, field) != getattr(after, field)
        )
        if changed:
            # S11.4: the classification categories BEFORE the edit — the one value the
            # subscriber cannot re-read (gone post-edit), needed to recompute the
            # neighbours of the FORMER covering budget (P11.4.4). Read from `old`
            # (built before the mutation). `changed` is computed on the HEADER
            # `category_id`, while this reads the classification LEG — the two stay in
            # sync post-confirm (E08.5, ADR 0001 note S11.4), which is why a header
            # change reliably signals a leg change. Empty unless `category_id` changed.
            previous_category_ids: frozenset[UUID] = (
                frozenset(
                    s.category_id
                    for s in old.splits
                    if s.leg_role == "classification" and s.category_id is not None
                )
                if "category_id" in changed
                else frozenset()
            )
            await dispatch(
                session,
                events.TransactionEditableFieldsChangedEvent(
                    transaction_id=tx.id,
                    changed_fields=changed,
                    previous_category_ids=previous_category_ids,
                ),
            )
    return after
