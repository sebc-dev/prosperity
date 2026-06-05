"""HTTP transport for the debts module (S09.3).

Exposes the two share-request acts over HTTP:

- `POST /transactions/{tx_id}/share-requests` — create a `ShareRequest` AND
  materialise the corresponding `Debt` (201). The route is *nested* under
  `/transactions/{tx_id}` but **owned by debts**: `tx_id` is read from the path
  and the tx is loaded via the service (`transactions.public`); no internals of
  the transactions module are imported.
- `DELETE /share-requests/{id}` — revoke a `ShareRequest` and hard-delete its
  materialised `Debt` (204, idempotent).

Both routers are guarded by `Depends(get_current_user)`: `by_user_id` is always
the token's user (D7), never the body. Service/domain rejections map to curated
4xx (never `str(exc)`, C-SEC-1; never a 500) via the `_EXC_STATUS`/`_EXC_DETAIL`
tables. No `commit()` here — `get_db` owns the transaction boundary (ADR 0015 —
the insert SR + insert Debt sequence is one DB transaction). 404 bodies are
uniform (no id echoed), so no path is an existence oracle (anti-oracle, review #22).

Internal to the debts module; cross-module callers go through
`backend.modules.debts.public`. Importing `auth.public` (`get_current_user`) is
legal downward and whitelisted as a second-hop in the `2-debts` `ignore_imports`
block.
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.public import User, get_current_user
from backend.modules.debts.domain import (
    DebtCalculationError,
    NonPositiveDebtAmountError,
    NonPositiveExpenseError,
    RatioOutOfBoundsError,
    SelfDebtError,
    SettlementLineInput,
    SettlementValidationError,
)
from backend.modules.debts.public import (
    CrossHouseholdError,
    DebtDirection,
    DuplicateActiveShareRequestError,
    LinkedTransactionNotAccessibleError,
    LinkedTransactionNotConfirmedError,
    LinkedTransactionNotTransferError,
    RequestedFromNotMemberError,
    SelfShareError,
    SettlementDebtNotAccessibleError,
    SettlementServiceError,
    ShareRequestError,
    ShareRequestNotFoundError,
    SourceAccountNotShareableError,
    SourceTransactionNotConfirmedError,
    SourceTransactionNotFoundError,
    aggregate_by_counterparty,
    create_settlement,
    create_share_request,
    list_debts_for_user,
    revoke_share_request,
)
from backend.modules.debts.schemas import (
    CounterpartyListResponse,
    CounterpartyNetResponse,
    DebtListResponse,
    DebtResponse,
    SettlementCreate,
    SettlementListResponse,
    SettlementResponse,
    ShareRequestCreate,
    ShareRequestResponse,
)
from backend.modules.debts.service.settlement import list_settlements_between
from backend.shared.db import get_db

logger = logging.getLogger(__name__)

# Nested under `/transactions/{tx_id}` but owned by debts (a second router on the
# `/transactions` prefix, distinct from `transactions_router`).
tx_share_requests_router = APIRouter(prefix="/transactions", tags=["debts"])
share_requests_router = APIRouter(prefix="/share-requests", tags=["debts"])
# Read-only dashboard surface (S09.4): `GET /debts` + `GET /debts/by-counterparty`.
# Scope is ALWAYS derived from the token (anti-IDOR) — there is no `/{id}` route
# nor any mutation route on `Debt` (projection read-only, ADR 0002).
debts_router = APIRouter(prefix="/debts", tags=["debts"])
# Settlement write + read surface (S10.4): `POST /settlements`,
# `GET /settlements?with=<user>`, `GET /settlements/{id}`. The scope is ALWAYS
# derived from the token (anti-IDOR); `by_user_id` is the token's user, never the
# body (D7). Owned by debts, mounted at the app level.
settlements_router = APIRouter(prefix="/settlements", tags=["debts"])

CurrentUser = Annotated[User, Depends(get_current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_db)]

# Uniform 404 bodies — same string for "doesn't exist" and "not yours", so no
# path is an existence oracle (anti-oracle, review #22).
_TX_NOT_FOUND_DETAIL = "Transaction not found."
_SR_NOT_FOUND_DETAIL = "Share request not found."
_SETTLEMENT_TARGET_NOT_FOUND_DETAIL = "Settlement target not found."

# Race lost (D12): under engine-wide REPEATABLE READ, a settlement that loses a
# serialisation race aborts with `40001` (a `DBAPIError`). Mapped to 409 as a
# backstop (gabarit `share_request._RACE_LOST_SQLSTATES`). NB the insert-only
# over-settlement write-skew is NOT prevented by RR — accepted in V1, follow-up
# tracked (escalate SERIALIZABLE / DB guard at multi-couple unlock).
_RACE_LOST_SQLSTATES = frozenset({"40001"})

# Curated mapping of every typed rejection → HTTP status (never `str(exc)`,
# C-SEC-1). Two families: the service `ShareRequestError` taxonomy (access/state)
# and the pure domain `DebtCalculationError` family (fail-safe guards).
# `SelfDebtError` is mapped for family completeness but is UNREACHABLE via the
# service (vérif v short-circuits before the DebtCalculator) — kept by coherence
# of the `DebtCalculationError` family, no test possible.
_EXC_STATUS: dict[type[Exception], int] = {
    SourceTransactionNotFoundError: status.HTTP_404_NOT_FOUND,
    ShareRequestNotFoundError: status.HTTP_404_NOT_FOUND,
    SourceAccountNotShareableError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    SourceTransactionNotConfirmedError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    RequestedFromNotMemberError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    SelfShareError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    NonPositiveExpenseError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    RatioOutOfBoundsError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    NonPositiveDebtAmountError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    SelfDebtError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    DuplicateActiveShareRequestError: status.HTTP_409_CONFLICT,
    # Settlement service taxonomy (S10.4). The debt-not-accessible family
    # (incl. CrossHouseholdError, a subclass) + the inaccessible linked tx are a
    # uniform 404 (anti-oracle); state/shape rejections are 422.
    SettlementDebtNotAccessibleError: status.HTTP_404_NOT_FOUND,
    CrossHouseholdError: status.HTTP_404_NOT_FOUND,
    LinkedTransactionNotAccessibleError: status.HTTP_404_NOT_FOUND,
    LinkedTransactionNotConfirmedError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    LinkedTransactionNotTransferError: status.HTTP_422_UNPROCESSABLE_ENTITY,
}
_EXC_DETAIL: dict[type[Exception], str] = {
    SourceTransactionNotFoundError: _TX_NOT_FOUND_DETAIL,
    ShareRequestNotFoundError: _SR_NOT_FOUND_DETAIL,
    SourceAccountNotShareableError: "The source account cannot be shared.",
    SourceTransactionNotConfirmedError: "The source transaction is not confirmed.",
    RequestedFromNotMemberError: "The requested user is not a foyer member.",
    SelfShareError: "You cannot share an expense with yourself.",
    NonPositiveExpenseError: "The transaction has no shareable expense.",
    RatioOutOfBoundsError: "The ratio must be within (0, 1].",
    NonPositiveDebtAmountError: "The shared amount rounds to zero.",
    SelfDebtError: "A debt cannot point to its own creditor.",
    DuplicateActiveShareRequestError: "An active share request already exists.",
    SettlementDebtNotAccessibleError: _SETTLEMENT_TARGET_NOT_FOUND_DETAIL,
    CrossHouseholdError: _SETTLEMENT_TARGET_NOT_FOUND_DETAIL,
    LinkedTransactionNotAccessibleError: _TX_NOT_FOUND_DETAIL,
    LinkedTransactionNotConfirmedError: "The linked transaction is not confirmed.",
    LinkedTransactionNotTransferError: "The linked transaction is not a transfer.",
}
_DEFAULT_EXC_DETAIL = "Share request error."
# Every SettlementValidationError subclass (S10.2 ×8) → a single generic 422
# (the PII-free `code` is logged for observability, never echoed).
_SETTLEMENT_INVALID_DETAIL = "Settlement is invalid."


def _map_exc(exc: Exception) -> HTTPException:
    """Curated HTTP mapping for a typed rejection (never `str(exc)`, C-SEC-1).

    An unmapped exception would surface as 500 via the default — never a leaked
    message. The PII-free `code` is logged for observability (never `note`, an
    amount, or a UUID — S-M5).

    The `SettlementValidationError` family (S10.2 ×8) is collapsed to a single
    generic 422 via `isinstance` (no per-subclass enumeration): all eight share
    the same curated detail; only the `code` distinguishes them in the log.
    """
    if isinstance(exc, SettlementValidationError):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        detail = _SETTLEMENT_INVALID_DETAIL
    else:
        status_code = _EXC_STATUS.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
        detail = _EXC_DETAIL.get(type(exc), _DEFAULT_EXC_DETAIL)
    logger.info(
        "debts_request_rejected",
        extra={
            "error": type(exc).__name__,
            "code": getattr(exc, "code", None),
        },
    )
    return HTTPException(status_code, detail=detail)


@tx_share_requests_router.post(
    "/{tx_id}/share-requests",
    response_model=ShareRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_share_request_route(
    tx_id: UUID,
    body: ShareRequestCreate,
    user: CurrentUser,
    session: SessionDep,
) -> ShareRequestResponse:
    """Create a `ShareRequest` + materialise its `Debt` in one DB transaction.

    `by_user_id` is the token's user (D7), never the body. Every rejection maps
    to a curated 4xx (404 inaccessible/unknown tx; 422 non-shareable account /
    non-confirmed tx / non-member / self-share / ratio / label / non-positive
    expense / degenerate rounding; 409 active duplicate) — never a 500.
    """
    try:
        sr = await create_share_request(
            session,
            transaction_id=tx_id,
            requested_from=body.requested_from,
            ratio=body.ratio,
            short_label=body.short_label,
            by_user_id=user.id,
        )
    except (ShareRequestError, DebtCalculationError) as exc:
        raise _map_exc(exc) from exc
    return ShareRequestResponse.from_model(sr)


@share_requests_router.delete("/{share_request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_share_request_route(
    share_request_id: UUID,
    user: CurrentUser,
    session: SessionDep,
) -> None:
    """Revoke a `ShareRequest` + hard-delete its `Debt` (idempotent, 204).

    Only the `requested_by` (creditor) may revoke; anyone else gets a uniform
    404 (anti-oracle — never confirm another user's SR exists). Re-revoking an
    already-revoked SR is a no-op (still 204).
    """
    try:
        await revoke_share_request(session, share_request_id=share_request_id, by_user_id=user.id)
    except ShareRequestError as exc:
        raise _map_exc(exc) from exc


# ---------------------------------------------------------------------------
# Dashboard read routes (S09.4) — scope derived from the token, no mutation.
# `/by-counterparty` is declared BEFORE the list route by hygiene (static before
# any future dynamic segment); there is no `/{id}` route on this router.
# ---------------------------------------------------------------------------


@debts_router.get("/by-counterparty", response_model=CounterpartyListResponse)
async def debts_by_counterparty_route(
    user: CurrentUser,
    session: SessionDep,
) -> CounterpartyListResponse:
    """Net orienté par contrepartie pour le user courant (périmètre dérivé du token).

    Passe par le MÊME helper de bornage/masquage que `GET /debts`
    (`aggregate_by_counterparty` → `list_debts_for_user`) — aucun champ source
    ne transite dans l'agrégat (non-fuite par construction).
    """
    nets = await aggregate_by_counterparty(session, user_id=user.id)
    return CounterpartyListResponse(items=[CounterpartyNetResponse.from_net(n) for n in nets])


@debts_router.get("", response_model=DebtListResponse)
async def list_debts_route(
    user: CurrentUser,
    session: SessionDep,
    direction: DebtDirection = DebtDirection.ALL,
    with_: Annotated[UUID | None, Query(alias="with")] = None,  # `with` est un mot-clé Python
) -> DebtListResponse:
    """Dettes du user courant (périmètre dérivé du token, D7/D9).

    `direction` borne le sens (`all`/`owed_to_me`/`owed_by_me`) ; `with` filtre la
    contrepartie APRÈS bornage — jamais un sélecteur de propriétaire (anti-IDOR).
    `source_transaction_id`/`account_id` sont `null` quand le caller est débiteur ;
    `materialization_trace` n'apparaît jamais (allowlist). Une `direction` invalide
    → 422 natif FastAPI (validation enum).
    """
    debts = await list_debts_for_user(
        session, user_id=user.id, direction=direction, counterparty=with_
    )
    return DebtListResponse(items=[DebtResponse.from_context(d) for d in debts])


# ---------------------------------------------------------------------------
# Settlement routes (S10.4) — POST create + GET list (scope from the token).
# ---------------------------------------------------------------------------


@settlements_router.post(
    "", response_model=SettlementResponse, status_code=status.HTTP_201_CREATED
)
async def create_settlement_route(
    body: SettlementCreate,
    user: CurrentUser,
    session: SessionDep,
) -> SettlementResponse:
    """Create a multi-debt settlement (201) in one DB transaction.

    `by_user_id` is the token's user (D7), never the body. Every rejection maps to
    a curated 4xx (404 inaccessible/unknown debt or linked tx, incl. cross-foyer;
    422 non-confirmed / non-transfer tx + every `SettlementValidator` invariant;
    409 on a lost serialisation race) — never a 500.
    """
    try:
        s = await create_settlement(
            session,
            settlement_type=body.type,
            linked_transaction_id=body.linked_transaction_id,
            settled_at=body.settled_at,
            note=body.note,
            lines=[
                SettlementLineInput(debt_id=line.debt_id, amount_cents=line.amount_cents)
                for line in body.lines
            ],
            by_user_id=user.id,  # D7: from the token, never the body
        )
    except (SettlementServiceError, SettlementValidationError) as exc:
        raise _map_exc(exc) from exc
    except DBAPIError as exc:  # D12: lost serialisation race (40001) → 409
        if getattr(exc.orig, "sqlstate", None) in _RACE_LOST_SQLSTATES:
            raise HTTPException(
                status.HTTP_409_CONFLICT, detail="Settlement conflicted, retry."
            ) from exc
        raise
    return SettlementResponse.from_model(s)


@settlements_router.get("", response_model=SettlementListResponse)
async def list_settlements_route(
    user: CurrentUser,
    session: SessionDep,
    with_: Annotated[UUID, Query(alias="with")],
) -> SettlementListResponse:
    """Settlements between the caller and `with` (scope derived from the token).

    The perimeter is bounded by the token (`caller = user.id`); `with` is a
    counterparty filter applied AFTER bounding (anti-IDOR) — never a selector of
    someone else's settlements. Includes settlements of fully-settled debts (D9).
    """
    rows = await list_settlements_between(session, caller_id=user.id, with_user_id=with_)
    return SettlementListResponse(items=[SettlementResponse.from_model(s) for s in rows])
