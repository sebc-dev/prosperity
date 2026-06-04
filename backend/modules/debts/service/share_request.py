"""Share-request service: validate the act, insert the `ShareRequest`, and
materialise the `Debt` — in ONE DB transaction (S09.3).

This is where `debts` first consumes `transactions.public`, `accounts.public`,
and `auth.public` (contract `2-debts`). The flow is **transaction-agnostic**:
both `create_share_request` and `revoke_share_request` `flush()` but never
`commit()` — the transaction boundary belongs to `get_db` (ADR 0015 — D1). These
are ordinary business operations: if they fail, we *want* the rollback (insert
`ShareRequest` + insert `Debt` are indivisible). They do NOT meet the ADR 0015
commit-inside-service criterion ("the client must not be able to undo the side
effect by triggering the exception that carries it").

The error taxonomy below is DB/access-world (gabarit `TransactionNotFoundError`),
distinct from the pure `DebtCalculationError` family (`debts.domain`) which the
route boundary maps separately. `code` (ClassVar) is the stable, PII-free client
channel — the boundary never copies `str(exc)` (C-SEC-1).
"""

from __future__ import annotations

import operator
from datetime import UTC, datetime
from decimal import Decimal
from functools import reduce
from typing import ClassVar
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.public import (
    account_is_accessible,
    owned_personal_account_ids,
)
from backend.modules.auth.public import user_is_active_member
from backend.modules.debts.domain import Debt as DomainDebt
from backend.modules.debts.domain import DebtCalculator, ShareRequestData
from backend.modules.debts.models import Debt, ShareRequest
from backend.modules.transactions.public import TransactionState, get_transaction
from backend.shared.currency import Currency
from backend.shared.money import Money


class ShareRequestError(Exception):
    """Base of every share-request access/state rejection (gabarit `TransactionError`).

    A common base lets the route boundary map the whole family with one
    `except ShareRequestError`. `code` is stable and PII-free (copied as-is to
    the client; never `str(exc)`).
    """

    code: ClassVar[str] = "share_request_error"


class SourceTransactionNotFoundError(ShareRequestError):
    """Source tx unknown OR inaccessible to `by_user_id` → uniform 404 (anti-oracle)."""

    code: ClassVar[str] = "source_transaction_not_found"


class SourceAccountNotShareableError(ShareRequestError):
    """Source account not a personal account owned by `by_user_id` → 422."""

    code: ClassVar[str] = "source_account_not_shareable"


class SourceTransactionNotConfirmedError(ShareRequestError):
    """Source tx not `confirmed` (ADR 0001: expense_total frozen) → 422."""

    code: ClassVar[str] = "source_transaction_not_confirmed"


class RequestedFromNotMemberError(ShareRequestError):
    """`requested_from` is not an active foyer member → 422 (indistinct, anti-oracle)."""

    code: ClassVar[str] = "requested_from_not_member"


class SelfShareError(ShareRequestError):
    """`requested_from == by_user_id` → 422 (no self-share)."""

    code: ClassVar[str] = "self_share"


class DuplicateActiveShareRequestError(ShareRequestError):
    """An active `ShareRequest` already exists for `(tx, requested_from)` → 409."""

    code: ClassVar[str] = "duplicate_active_share_request"


class ShareRequestNotFoundError(ShareRequestError):
    """SR unknown OR not owned by `by_user_id` (revoke) → uniform 404 (anti-oracle)."""

    code: ClassVar[str] = "share_request_not_found"


# Race lost at flush (D10): under the engine-wide REPEATABLE READ isolation
# (`shared/db.py`), the loser of a concurrent race on the partial-unique
# `uq_share_requests_active` is aborted by `40001 serialization_failure` — raised
# as a `DBAPIError` (parent of `IntegrityError`), BEFORE the unique check fires
# its `23505`. Catching `IntegrityError`/`23505` alone would leak a 500 on
# exactly the race this backstop closes. Mirror of `/setup`
# (`accounts/transports/http.py:_RACE_LOST_SQLSTATES`, minus `23514`: no
# triggerable CHECK on this path). Both SQLSTATEs ⇒ "race lost" → 409.
_RACE_LOST_SQLSTATES = frozenset({"23505", "40001"})


def _to_orm_debt(d: DomainDebt) -> Debt:
    """Map a pure domain `Debt` to its ORM row, stamping `materialization_trace`.

    The `DebtCalculator` returns the pure projection (`Money`, no DB-generated
    columns); the service maps `amount.amount_cents`/`.currency` → columns and
    posts the server-only `materialization_trace` (D8 — never exposed via API).
    Symmetry with `transactions.service._to_domain` (mapper internal to the
    service layer).
    """
    return Debt(
        from_user_id=d.from_user_id,
        to_user_id=d.to_user_id,
        amount_cents=d.amount.amount_cents,
        currency=d.amount.currency,
        account_id=d.account_id,
        source_transaction_id=d.source_transaction_id,
        origin=d.origin,
        share_ratio=d.share_ratio,
        materialization_trace=f"personal_share_request:{datetime.now(UTC).isoformat()}",
    )


async def create_share_request(  # noqa: PLR0913 — flat keyword-only act params
    session: AsyncSession,
    *,
    transaction_id: UUID,
    requested_from: UUID,
    ratio: Decimal,
    short_label: str,
    by_user_id: UUID,
) -> ShareRequest:
    """Validate the act, insert the `ShareRequest` AND materialise the `Debt`,
    in ONE DB transaction (commit by `get_db`, ADR 0015 — D1).

    Verification order (404 first, anti-oracle):
    (i) source tx accessible & existing for `by_user_id` → else uniform 404;
    (ii) source account ∈ `owned_personal_account_ids(by_user_id)` (covers owner
    AND personal in one call) → else 422; (iii) source tx `confirmed` (ADR 0001:
    `expense_total` frozen) → else 422; (iv) `requested_from` is an active foyer
    member → else 422 (indistinct); (v) `requested_from != by_user_id` → else
    422; (vi)/(vii) `ratio`/`short_label` validated at the Pydantic boundary
    (P09.3.3), the `DebtCalculator` being the ultimate fail-safe guard; (ix) no
    active SR already on `(tx, requested_from)` → else 409; (viii) `expense_total`
    = sum of classification legs (funding excluded, ADR 0017) > 0 → else 422
    (via the `DebtCalculator`).

    ⚠️ Order delta (assumed): (ix) duplicate pre-check runs BEFORE (viii)
    `expense_total`, short-circuiting an unnecessary computation on a path bound
    to 409 (a duplicate implies a first SR already created with `expense_total > 0`).
    """
    # (i) source tx accessible & existing for by_user_id → uniform 404
    tx = await get_transaction(session, tx_id=transaction_id)
    if tx is None or not await account_is_accessible(
        session, account_id=tx.account_id, user_id=by_user_id
    ):
        raise SourceTransactionNotFoundError

    # (ii) source account ∈ owned personal accounts (owner + personal) → 422
    if tx.account_id not in await owned_personal_account_ids(session, owner_id=by_user_id):
        raise SourceAccountNotShareableError

    # (iii) source tx confirmed (ADR 0001: expense_total frozen) → 422
    if tx.state is not TransactionState.CONFIRMED:
        raise SourceTransactionNotConfirmedError

    # (iv) requested_from = active foyer member → 422 (indistinct, anti-oracle)
    if not await user_is_active_member(session, user_id=requested_from):
        raise RequestedFromNotMemberError

    # (v) no self-share → 422
    if requested_from == by_user_id:
        raise SelfShareError

    # (ix) no active SR already on (tx, requested_from) → 409 (pre-check).
    #      Placed BEFORE (viii) expense_total — short-circuit, assumed delta.
    existing = await session.execute(
        select(ShareRequest.id).where(
            ShareRequest.source_transaction_id == transaction_id,
            ShareRequest.requested_from == requested_from,
            ShareRequest.revoked_at.is_(None),
        )
    )
    if existing.first() is not None:
        raise DuplicateActiveShareRequestError

    # (viii) expense_total = sum of classification legs (funding excluded, D3).
    classification = [s.amount for s in tx.splits if s.leg_role == "classification"]
    expense_total = reduce(operator.add, classification) if classification else Money(0, _ccy(tx))

    sr = ShareRequest(
        source_transaction_id=transaction_id,
        requested_by=by_user_id,
        requested_from=requested_from,
        ratio=ratio,
        short_label=short_label,
    )
    session.add(sr)

    # DebtCalculator (pure) guards expense_total>0 (NonPositiveExpenseError → viii),
    # ratio (RatioOutOfBoundsError, fail-safe), self (SelfDebtError, unreachable
    # via the service — vérif v short-circuits), and amount>0 (NonPositiveDebtAmount).
    debts = DebtCalculator.compute_for_share_request(
        share_request=ShareRequestData(
            source_transaction_id=transaction_id,
            requested_by=by_user_id,
            requested_from=requested_from,
            ratio=ratio,
            short_label=short_label,
        ),
        expense_total=expense_total,
        source_account_id=tx.account_id,
    )
    for d in debts:
        session.add(_to_orm_debt(d))

    try:
        await session.flush()  # surface 23505/40001 (real race ix) inside the service
    except DBAPIError as exc:
        # Under engine-wide REPEATABLE READ (shared/db.py), the loser of a
        # concurrent race is aborted by 40001 serialization_failure — a DBAPIError
        # raised BEFORE the partial-unique 23505. IntegrityError/23505 alone would
        # leak a 500 on this race (gabarit /setup). Both SQLSTATEs ⇒ 409.
        if getattr(exc.orig, "sqlstate", None) in _RACE_LOST_SQLSTATES:
            raise DuplicateActiveShareRequestError from exc
        raise
    return sr


async def revoke_share_request(
    session: AsyncSession, *, share_request_id: UUID, by_user_id: UUID
) -> None:
    """Revoke the SR (set `revoked_at`) + hard-delete the materialised `Debt`.

    Authorisation: `by_user_id == requested_by` else uniform 404 (anti-oracle —
    do not confirm the existence of another user's SR). Idempotent: an
    already-revoked SR → no-op (no crash, no `Debt` recreation). Transaction-
    agnostic (commit by `get_db`, D1).

    The `Debt` is targeted by `(source_transaction_id, from_user_id=requested_from,
    to_user_id=requested_by)` — the triplet that materialises exactly the debt
    this SR created (there is no FK `debt → share_request`). Uniqueness is
    guaranteed by composition (D12): the partial unique
    `uq_share_requests_active (source_transaction_id, requested_from)` forbids two
    *active* SRs on the pair, and `requested_by` is *derived* — the source account
    is personal, so it has a unique owner ⇒ for a given `(tx, requested_from)`,
    `requested_by` can only take one value. Thus at most one live `Debt` matches
    the triplet (0 rows if never materialised). The ">1 row" case is structurally
    impossible under these invariants (locked by the "no orphan Debt" test).
    """
    sr = await session.get(ShareRequest, share_request_id)
    if sr is None or sr.requested_by != by_user_id:
        raise ShareRequestNotFoundError
    if sr.revoked_at is not None:  # idempotence: already revoked → no-op
        return
    sr.revoked_at = datetime.now(UTC)
    await session.execute(
        delete(Debt).where(
            Debt.source_transaction_id == sr.source_transaction_id,
            Debt.from_user_id == sr.requested_from,
            Debt.to_user_id == sr.requested_by,
        )
    )
    await session.flush()


def _ccy(tx: object) -> Currency:
    """Currency of the source tx (first split) for a zero-classification `Money(0)`.

    Mono-currency V1 (ADR 0008): a confirmed tx is zero-sum with a single
    currency, so the first split's currency is authoritative. Only consulted when
    there is no classification leg (transfer) → `Money(0, ccy)` →
    `NonPositiveExpenseError` (vérif viii).
    """
    return tx.splits[0].amount.currency  # type: ignore[attr-defined]
