"""HTTP transport for the transactions module (S07.5).

Exposes the aggregate over HTTP with F03 watertightness by **membership**, never
RBAC (gabarit `accounts/transports/http.py` S05.3, NOT the categories S06.3
template): a member of an account creates/reads/confirms/voids/edits the
transactions of *their* accounts; a non-member — admin included — gets a uniform
**404** (non-disclosure, never 403). Access is computed on account membership
(`accounts.public.account_is_accessible` / `accessible_account_ids`), never via
`require_admin` — the admin is NOT exempt (invariant F03).

Two routers: `transactions_router` (`/transactions/...`) for the per-transaction
routes, and `account_tx_router` (`/accounts/{id}/transactions`) for creation
(nested under the owning account). Both are guarded by `Depends(get_current_user)`
only. Domain rejections map to curated 4xx (never `str(exc)`, C-SEC-1; never a
500) via the `_EXC_STATUS`/`_EXC_DETAIL` tables. No `commit()` here — `get_db`
owns the transaction boundary (ADR 0015); the service's `publish` runs inside it.

Internal to the transactions module; cross-module callers go through
`backend.modules.transactions.public`. Importing `auth.public` (`get_current_user`)
and `accounts.public` (membership) is legal downward and whitelisted as
second-hops in the `2-transactions` `ignore_imports` block.
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.public import (
    accessible_account_ids,
    account_is_accessible,
)
from backend.modules.auth.public import User, get_current_user
from backend.modules.transactions import domain
from backend.modules.transactions.public import (
    ImmutableFieldViolation,
    InvalidStateTransitionError,
    TransactionError,
    UnbalancedTransactionError,
    UncategorizedExpenseError,
    add_split,
    create_draft,
    get_transaction,
    transition_to_confirmed,
    transition_to_planned,
    update_editable_fields,
    void,
)
from backend.modules.transactions.schemas import (
    TransactionCreate,
    TransactionResponse,
    VoidRequest,
)
from backend.shared.db import get_db
from backend.shared.money import IncompatibleCurrencyError

logger = logging.getLogger(__name__)

transactions_router = APIRouter(prefix="/transactions", tags=["transactions"])
# Creation lives under the owning account, so a second router on `/accounts`
# (distinct from `accounts_router`; FastAPI allows multiple routers per prefix).
account_tx_router = APIRouter(prefix="/accounts", tags=["transactions"])

CurrentUser = Annotated[User, Depends(get_current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_db)]

# Uniform 404 body for every inaccessible/unknown transaction or account — the
# same string for "doesn't exist" and "not yours", so no path is an existence
# oracle (D4 non-disclosure).
_NOT_FOUND_DETAIL = "Transaction not found."
# 422 body when a split references an account the caller cannot reach (D5).
# Generic on purpose — it never echoes the offending id (C-SEC-1).
_INACCESSIBLE_SPLIT_DETAIL = "A split references an inaccessible account."
_BAD_DEBT_OVERRIDE_DETAIL = "Invalid debt generation override."


@account_tx_router.post(
    "/{account_id}/transactions",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_transaction(
    account_id: UUID,
    body: TransactionCreate,
    user: CurrentUser,
    session: SessionDep,
) -> TransactionResponse:
    """Create a `draft` + its splits + editable metadata from the payload.

    `created_by` is the token's user (D6), never the body. The route `account_id`
    is checked for membership first — inaccessible → 404 (admin included, D4/D5).
    Every split `account_id` must also be accessible (D5): a foreign account would
    inflate the distinct-account count → `is_transfer` True → the expense escapes
    `assert_expenses_categorized`; an inaccessible one is a 422 (body data, generic
    detail). The editable metadata is posted on the draft via `update_editable_fields`
    (a no-op `check_mutation_allowed` below `confirmed`, D10).
    """
    if not await account_is_accessible(session, account_id=account_id, user_id=user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)
    reachable = await accessible_account_ids(session, user_id=user.id)
    if any(s.account_id not in reachable for s in body.splits):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_INACCESSIBLE_SPLIT_DETAIL)
    try:
        tx = await create_draft(session, account_id=account_id, by_user_id=user.id, date=body.date)
        for s in body.splits:
            tx = await add_split(
                session,
                tx_id=tx.id,
                account_id=s.account_id,
                amount_cents=s.amount_cents,
                currency=s.currency,
                category_id=s.category_id,
            )
        tx = await update_editable_fields(
            session,
            tx_id=tx.id,
            category_id=body.category_id,
            description=body.description,
            tags=tuple(body.tags),
            debt_generation_override=body.debt_generation_override,
        )
    except IntegrityError as exc:
        # Fail-closed backstops → 422 (never a 500 on body data). Both are nearly
        # unreachable here (the schema `Literal` pre-empts 23514; D5 pre-validates
        # split accounts, which are archived-not-deleted so the FK target persists),
        # but mirror the `accounts` template (FK 23503 → 422) rather than leak a 500.
        sqlstate = getattr(exc.orig, "sqlstate", None)
        if sqlstate == "23514":  # CHECK ck_transactions_debt_generation_override (S07.4)
            logger.info("tx_create_rejected", extra={"error": "bad_debt_override"})
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_BAD_DEBT_OVERRIDE_DETAIL
            ) from exc
        if sqlstate == "23503":  # FK splits.account_id (TOCTOU) — gabarit accounts
            logger.info("tx_create_rejected", extra={"error": "inaccessible_split_account"})
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_INACCESSIBLE_SPLIT_DETAIL
            ) from exc
        logger.error("tx_create_unexpected_integrity", extra={"sqlstate": sqlstate})
        raise
    return TransactionResponse.from_domain(tx)


# --- Per-transaction routes: access guard + domain-error mapping (P07.5.2) ---
#
# Every per-transaction route confirms membership of the transaction's account
# BEFORE mutating (D4): `_require_accessible_tx` collapses unknown + inaccessible
# into one uniform 404, so a non-member — admin included — cannot probe a tx's
# existence. Domain rejections map to curated 4xx via the tables below (never
# `str(exc)`, C-SEC-1; never a 500). `IncompatibleCurrencyError` is bordered
# explicitly (it is OUTSIDE the `TransactionError` family, raised by `Money.__add__`).

_EXC_STATUS: dict[type[Exception], int] = {
    InvalidStateTransitionError: status.HTTP_409_CONFLICT,
    ImmutableFieldViolation: status.HTTP_409_CONFLICT,
    UnbalancedTransactionError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    UncategorizedExpenseError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    IncompatibleCurrencyError: status.HTTP_422_UNPROCESSABLE_ENTITY,
}
_EXC_DETAIL: dict[type[Exception], str] = {
    InvalidStateTransitionError: "Transaction state does not allow this transition.",
    ImmutableFieldViolation: "This field is frozen on a confirmed transaction.",
    UnbalancedTransactionError: "Transaction splits must sum to zero.",
    UncategorizedExpenseError: "Every expense split must have a category.",
    IncompatibleCurrencyError: "All splits must share one currency.",
}
_DEFAULT_EXC_DETAIL = "Transaction error."


async def _require_accessible_tx(
    session: AsyncSession, tx_id: UUID, user: User
) -> domain.Transaction:
    """Load the tx + verify membership of ITS account; uniform 404 otherwise (D4).

    Merges "unknown id" and "inaccessible" into one 404 (`get_transaction` → None,
    or `account_is_accessible` → False), so neither path is an enumeration oracle.
    """
    tx = await get_transaction(session, tx_id=tx_id)
    if tx is None or not await account_is_accessible(
        session, account_id=tx.account_id, user_id=user.id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)
    return tx


def _map_domain_exc(exc: Exception) -> HTTPException:
    """Curated HTTP mapping for a domain rejection (never `str(exc)`, C-SEC-1).

    An unmapped exception (should not happen — the routes catch only the known
    families) would surface as 500 via the default, never as a leaked message.
    """
    code = _EXC_STATUS.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
    logger.info(
        "tx_transition_rejected",
        extra={
            "error": type(exc).__name__,
            "code": exc.code if isinstance(exc, TransactionError) else None,
        },
    )
    return HTTPException(code, detail=_EXC_DETAIL.get(type(exc), _DEFAULT_EXC_DETAIL))


@transactions_router.post("/{tx_id}/confirm", response_model=TransactionResponse)
async def confirm_transaction(
    tx_id: UUID, user: CurrentUser, session: SessionDep
) -> TransactionResponse:
    """`planned → confirmed`: zero-sum + every expense split categorised.

    A gate failure (unbalanced/uncategorized/mixed currency) → 422; an illegal
    transition (e.g. `draft → confirmed`) → 409 — never a 500.
    """
    await _require_accessible_tx(session, tx_id, user)
    try:
        tx = await transition_to_confirmed(session, tx_id=tx_id)
    except (TransactionError, IncompatibleCurrencyError) as exc:
        raise _map_domain_exc(exc) from exc
    return TransactionResponse.from_domain(tx)


@transactions_router.post("/{tx_id}/plan", response_model=TransactionResponse)
async def plan_transaction(
    tx_id: UUID, user: CurrentUser, session: SessionDep
) -> TransactionResponse:
    """`draft → planned`, refusing an unbalanced transaction (422).

    `confirmed → planned` is refused with 409 (ADR 0001 — reopening a confirmed
    transaction's amounts is forbidden).
    """
    await _require_accessible_tx(session, tx_id, user)
    try:
        tx = await transition_to_planned(session, tx_id=tx_id)
    except (TransactionError, IncompatibleCurrencyError) as exc:
        raise _map_domain_exc(exc) from exc
    return TransactionResponse.from_domain(tx)


@transactions_router.post("/{tx_id}/void", response_model=TransactionResponse)
async def void_transaction(
    tx_id: UUID,
    user: CurrentUser,
    session: SessionDep,
    body: VoidRequest | None = None,
) -> TransactionResponse:
    """`* → void` (terminal). A `void → void` re-void is a 409 (terminal state).

    `reason` (optional, bounded) rides the event payload only (no V1 column);
    the boundary never logs it raw (PII / log-injection).
    """
    await _require_accessible_tx(session, tx_id, user)
    reason = body.reason if body is not None else ""
    try:
        tx = await void(session, tx_id=tx_id, reason=reason)
    except (TransactionError, IncompatibleCurrencyError) as exc:
        raise _map_domain_exc(exc) from exc
    return TransactionResponse.from_domain(tx)
