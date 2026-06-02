"""HTTP transport for the budget module — `/budgets` CRUD + consumption + drill-down (S08.4).

Deliberately a **separate** transport from `http.py` (which hosts
`categories_router`): the two have **opposite AuthZ contracts**. Categories are
a household-global referential where the 404-vs-422 existence oracle is
*acceptable* (any member lists them all anyway). Budgets are **watertight**: a
`shared` budget is confidential, so a non-contributor — admin included — gets a
uniform **404** (never 403, never a differentiating detail), exactly like
`accounts`/`transactions`. Mixing the two contracts in one module docstring
would be incoherent, hence `budgets_http.py` (the issue allows "même fichier ou
`budgets_http.py`"). Both routers register side by side in `main.py`.

RBAC funnels through `get_visible_budget` (contributor ∪ owner, live), so list
and detail can never diverge on what a user may see. The admin is NOT exempt
(`get_current_user` only — never `require_admin`). We never echo `str(exc)` on
an error branch (C-SEC-1): the curated detail goes to the client, the precise
condition (sqlstate / error type) to the server `logger`.

Cross-module imports are downward + whitelisted second-hops (`2-budget`, D11):
`auth.public` (`get_current_user`/`User`) and `accounts.public` (via the service
layer). The cursor helpers are re-implemented locally (D10): `transactions`'
cursor helpers are module-internal and a peer (contract 1) → import forbidden.
"""

from __future__ import annotations

import base64
import binascii
import logging
from collections.abc import Sequence
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.public import User, get_current_user
from backend.modules.budget.domain import BudgetContributorError
from backend.modules.budget.models import Budget, BudgetContributor
from backend.modules.budget.schemas import (
    BudgetConsumptionResponse,
    BudgetCreate,
    BudgetListResponse,
    BudgetResponse,
    BudgetUpdate,
    BudgetWithConsumptionResponse,
    ContributingSplitResponse,
    ContributingSplitsListResponse,
)
from backend.modules.budget.service.budget_crud import (
    archive_budget,
    create_budget,
    update_budget,
)
from backend.modules.budget.service.budgets import (
    get_visible_budget,
    list_active_budgets_for_user,
)
from backend.modules.budget.service.consumption import (
    compute_consumption,
    list_contributing_splits,
)
from backend.shared.db import get_db

logger = logging.getLogger(__name__)

budgets_router = APIRouter(prefix="/budgets", tags=["budgets"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]

# Curated 4xx bodies — never `str(exc)` (C-SEC-1). The 404 is uniform across
# unknown / archived / non-contributor so no path is an existence oracle (D3).
_NOT_FOUND_DETAIL = "Budget not found."
_UNKNOWN_CATEGORY_DETAIL = "The category does not exist."
_BAD_CONTRIBUTORS_DETAIL = "Invalid budget contributors."
_BAD_CURSOR_DETAIL = "Malformed pagination cursor."
_DEFAULT_LIMIT = 50
_MAX_LIMIT = 100
_CURSOR_SEP = "|"


def _encode_cursor(when: date, split_id: UUID) -> str:
    """Opaque base64 keyset cursor over `(transactions.date, splits.id)` (D10).

    Re-implemented locally rather than imported from `transactions` (the cursor
    helpers there are module-internal and a peer — import forbidden, contract 1;
    same arbitrage as `transactions.queries._to_domain`).
    """
    raw = f"{when.isoformat()}{_CURSOR_SEP}{split_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(raw: str) -> tuple[date, UUID]:
    """Decode an opaque cursor, or raise `ValueError` if malformed.

    Every decode failure is normalised to `ValueError` (base64 → `binascii.Error`,
    non-UTF8 → `UnicodeDecodeError`, missing separator / bad `date.fromisoformat`
    / bad `UUID` → `ValueError`) so the boundary maps a single `ValueError` to
    422 — never a 500 (gabarit `transactions`).
    """
    try:
        decoded = base64.urlsafe_b64decode(raw.encode()).decode()
        raw_date, raw_id = decoded.split(_CURSOR_SEP, 1)
        return date.fromisoformat(raw_date), UUID(raw_id)
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("malformed cursor") from exc


async def _contributor_ids_by_budget(
    session: AsyncSession, budget_ids: Sequence[UUID]
) -> dict[UUID, list[UUID]]:
    """Contributeurs de plusieurs budgets en UNE requête (anti N+1, D14).

    `SELECT budget_id, user_id WHERE budget_id IN (...)` regroupé côté Python.
    Le listing `GET /budgets` fait déjà N `compute_consumption` ; charger les
    contributeurs un budget à la fois doublerait le N+1 — ici borné à O(1) requête.
    """
    if not budget_ids:
        return {}
    rows = (
        await session.execute(
            select(BudgetContributor.budget_id, BudgetContributor.user_id).where(
                BudgetContributor.budget_id.in_(budget_ids)
            )
        )
    ).all()
    out: dict[UUID, list[UUID]] = {bid: [] for bid in budget_ids}
    for budget_id, user_id in rows:
        out[budget_id].append(user_id)
    return out


def _budget_response(budget: Budget, contributor_ids: list[UUID]) -> BudgetResponse:
    """Assemble a `BudgetResponse` from an ORM budget + its contributor ids."""
    return BudgetResponse(
        id=budget.id,
        category_id=budget.category_id,
        period_kind=budget.period_kind,  # type: ignore[arg-type]
        period_start=budget.period_start,
        amount_cents=budget.amount_cents,
        currency=budget.currency,
        scope=budget.scope,  # type: ignore[arg-type]
        created_by=budget.created_by,
        carry_over_remainder=budget.carry_over_remainder,
        contributor_ids=contributor_ids,
        created_at=budget.created_at,
        archived_at=budget.archived_at,
    )


async def _to_response(session: AsyncSession, budget: Budget) -> BudgetResponse:
    """Vue d'UN budget (routes unitaires). Le listing passe par le chargement groupé."""
    contributor_ids = list(
        (
            await session.execute(
                select(BudgetContributor.user_id).where(BudgetContributor.budget_id == budget.id)
            )
        )
        .scalars()
        .all()
    )
    return _budget_response(budget, contributor_ids)


@budgets_router.post("", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
async def create_budget_route(
    body: BudgetCreate,
    user: CurrentUser,
    session: SessionDep,
) -> BudgetResponse:
    """Create a budget + its contributors; `created_by`/`currency` server-derived.

    A bad contributor list (count/shape or a `shared` contributor who is not a
    member of any common account) → 422. An unknown `category_id` trips the FK
    (23503) at flush → 422 (body reference, gabarit `create_category`). Any other
    SQLSTATE is a real bug → re-raise → 500 (never `str(exc)`, C-SEC-1).
    """
    try:
        budget = await create_budget(
            session,
            category_id=body.category_id,
            period_kind=body.period_kind,
            period_start=body.period_start,
            amount_cents=body.amount_cents,
            scope=body.scope,
            carry_over_remainder=body.carry_over_remainder,
            contributor_ids=body.contributor_ids,
            created_by=user.id,
        )
    except BudgetContributorError as exc:
        logger.info("budget_create_rejected", extra={"error": type(exc).__name__})
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_BAD_CONTRIBUTORS_DETAIL
        ) from exc
    except IntegrityError as exc:
        sqlstate = getattr(exc.orig, "sqlstate", None)
        if sqlstate == "23503":  # unknown category_id (FK)
            logger.info("budget_create_rejected", extra={"error": "unknown_category"})
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_UNKNOWN_CATEGORY_DETAIL
            ) from exc
        logger.error("budget_create_failed", extra={"sqlstate": sqlstate})
        raise
    return await _to_response(session, budget)


@budgets_router.get("", response_model=BudgetListResponse)
async def list_budgets_route(
    user: CurrentUser,
    session: SessionDep,
    as_of: date | None = None,
) -> BudgetListResponse:
    """List the budgets concerning the caller (personal owned ∪ shared contributor),
    non-archived, each with its consumption at `as_of` (default = today, D9).

    Contributors are loaded in ONE grouped query for the whole page (D14), so the
    listing is not N+1 on contributors (the N `compute_consumption` calls stay,
    a conscious V1 debt — few budgets per household, §7).
    """
    items = await list_active_budgets_for_user(
        session, user_id=user.id, as_of=as_of or date.today()
    )
    by_budget = await _contributor_ids_by_budget(session, [it.budget.id for it in items])
    return BudgetListResponse(
        items=[
            BudgetWithConsumptionResponse(
                budget=_budget_response(it.budget, by_budget[it.budget.id]),
                consumption=BudgetConsumptionResponse.model_validate(it.consumption),
            )
            for it in items
        ]
    )


@budgets_router.get("/{budget_id}", response_model=BudgetResponse)
async def get_budget_route(
    budget_id: UUID,
    user: CurrentUser,
    session: SessionDep,
) -> BudgetResponse:
    """Detail of a visible budget; uniform 404 if unknown / archived / not yours (D3)."""
    budget = await get_visible_budget(session, budget_id=budget_id, user_id=user.id)
    if budget is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)
    return await _to_response(session, budget)


@budgets_router.patch("/{budget_id}", response_model=BudgetResponse)
async def patch_budget_route(
    budget_id: UUID,
    body: BudgetUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> BudgetResponse:
    """Edit `amount_cents`/`carry_over_remainder`/`contributor_ids` (D7/D8).

    Visibility is checked first (`update_budget` → 404 before any validation), so
    a non-contributor sending an invalid body gets 404, never a 422 that would
    reveal the budget exists (D3 — order is security-relevant). A frozen field
    (`scope`/`category_id`/`period_*`) is a 422 at the schema (`extra="forbid"`).
    """
    fields = body.model_dump(exclude_unset=True)
    contributor_ids = fields.pop("contributor_ids", None)
    try:
        budget = await update_budget(
            session,
            budget_id=budget_id,
            user_id=user.id,
            fields=fields,
            contributor_ids=contributor_ids,
        )
    except BudgetContributorError as exc:
        logger.info("budget_patch_rejected", extra={"error": type(exc).__name__})
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_BAD_CONTRIBUTORS_DETAIL
        ) from exc
    if budget is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)
    return await _to_response(session, budget)


@budgets_router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget_route(
    budget_id: UUID,
    user: CurrentUser,
    session: SessionDep,
) -> Response:
    """Soft-delete (archive) a visible budget; never a hard delete.

    The row is preserved with `archived_at` set (contributors survive) and drops
    out of the listing / detail. A re-DELETE of an already-archived budget → 404
    (idempotent in the "no corruption" sense, gabarit `accounts.archive`). A
    non-contributor → 404 (watertight, D3).
    """
    if not await archive_budget(session, budget_id=budget_id, user_id=user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@budgets_router.get("/{budget_id}/consumption", response_model=BudgetConsumptionResponse)
async def get_budget_consumption_route(
    budget_id: UUID,
    user: CurrentUser,
    session: SessionDep,
    as_of: date | None = None,
) -> BudgetConsumptionResponse:
    """Detailed consumption of a visible budget at `as_of` (default = today, D9).

    Visibility is checked first (`get_visible_budget` → 404 watertight, D3), then
    the read delegates to `compute_consumption` (RBAC-blind, gabarit S08.2). The
    `consumption is None` branch is structurally unreachable here — after a
    non-`None` `get_visible_budget` in the same transaction, `compute_consumption`
    only returns `None` for an unknown id — so it is a documented defensive guard
    (`# pragma: no cover`), not a tested 404 path.
    """
    if await get_visible_budget(session, budget_id=budget_id, user_id=user.id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)
    consumption = await compute_consumption(
        session, budget_id=budget_id, as_of=as_of or date.today()
    )
    if consumption is None:  # pragma: no cover — defensive: visible ⇒ exists
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)
    return BudgetConsumptionResponse.model_validate(consumption)


@budgets_router.get(
    "/{budget_id}/contributing-splits", response_model=ContributingSplitsListResponse
)
async def list_contributing_splits_route(  # noqa: PLR0913 — flat query params
    budget_id: UUID,
    user: CurrentUser,
    session: SessionDep,
    as_of: date | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
) -> ContributingSplitsListResponse:
    """Paginated drill-down of the splits contributing to the budget's consumption.

    Visibility is checked first (`get_visible_budget` → 404 watertight, D3) — the
    cursor is decoded only after, and the query stays bounded to `budget_id`, so a
    cursor lifted from another budget cannot widen the perimeter. A malformed
    cursor → 422 (never a 500). The page is consistent with `splits_count` of the
    consumption (same `_consumption_filters`, D13).
    """
    if await get_visible_budget(session, budget_id=budget_id, user_id=user.id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)
    try:
        after = _decode_cursor(cursor) if cursor else None
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_BAD_CURSOR_DETAIL
        ) from exc
    rows, next_cursor = await list_contributing_splits(
        session, budget_id=budget_id, as_of=as_of or date.today(), after=after, limit=limit
    )
    return ContributingSplitsListResponse(
        items=[ContributingSplitResponse.model_validate(r) for r in rows],
        next_cursor=_encode_cursor(*next_cursor) if next_cursor else None,
    )
