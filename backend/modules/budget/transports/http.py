"""HTTP transport for the budget module — `/categories` CRUD (S06.3).

Categories are **household-global referentials** (bucket `household`,
CONTEXT.md §Catégorie): every authenticated member manages them. Hence the
deliberate contrast with `accounts`:

* AuthZ is `Depends(get_current_user)` alone — never `require_admin` /
  `require_member`, never a per-resource watertight filter (D3). An anonymous
  caller is 401; there is no IDOR in V1 mono-household (E13 will add a
  `household_id` filter for the multi-household path, §7).
* A `CategoryNotFoundError` maps to a real 404 and `CategoryCycleError` to 422
  — the existence oracle is *acceptable* here (D4), because any member may list
  every category via `GET /categories` anyway, so 404-vs-422 leaks nothing
  beyond what the list already shows.

This module hosts the **first** `budget → auth.public` arc (`User` /
`get_current_user`); the import-linter contract `2-budget` carries the matching
`ignore_imports` block (the same nine `auth.public → auth.X` second-hops as
`2-accounts`).

We never echo `str(exc)` on an error branch (C-SEC-1): the curated detail goes
to the client, the precise condition to the server `logger` (gabarit
`accounts.transports.http`).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.public import (
    AdminAction,
    User,
    get_current_user,
    log_admin_action,
)
from backend.modules.budget.domain import CategoryCycleError, CategoryNotFoundError
from backend.modules.budget.models import Category
from backend.modules.budget.schemas import (
    CategoryCreate,
    CategoryMove,
    CategoryResponse,
    CategoryUpdate,
)
from backend.modules.budget.service.categories import (
    archive_category,
    create_category,
    list_categories,
    move_category,
    update_category,
)
from backend.shared.db import get_db

logger = logging.getLogger(__name__)

categories_router = APIRouter(prefix="/categories", tags=["categories"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]

# Curated 4xx bodies — never `str(exc)` (C-SEC-1).
_CYCLE_DETAIL = "Category parent would create a cycle."
_UNKNOWN_PARENT_DETAIL = "The parent category does not exist."
_NOT_FOUND_DETAIL = "Category not found."
_RETRY_DETAIL = "Concurrent category move, please retry."

# serialization_failure + deadlock_detected: a concurrent mover lost the
# REPEATABLE READ / advisory-lock race (D7). Mapped to 409 (retryable), never
# a 500 — and distinct from IntegrityError, which Postgres raises as a sibling
# of DBAPIError.
_SERIALIZE_SQLSTATES = frozenset({"40001", "40P01"})


@categories_router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category_route(
    body: CategoryCreate,
    user: CurrentUser,
    session: SessionDep,
) -> Category:
    """Create a category (optional `parent_id`); 422 on cycle / unknown parent.

    The cycle guard is vacuous on create (the id is server-side, the node has
    no descendants), but kept symmetric with the move route. An unknown
    `parent_id` trips the self-FK at flush (23503) → 422, since `parent_id` is
    a body reference (gabarit accounts "unknown member"). Any other SQLSTATE is
    a real bug → re-raise → 500.
    """
    try:
        return await create_category(
            session,
            name=body.name,
            color=body.color,
            icon=body.icon,
            parent_id=body.parent_id,
        )
    except CategoryCycleError as exc:
        logger.info("category_create_rejected", extra={"error": type(exc).__name__})
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_CYCLE_DETAIL) from exc
    except IntegrityError as exc:
        sqlstate = getattr(exc.orig, "sqlstate", None)
        if sqlstate == "23503":
            logger.info("category_create_rejected", extra={"error": "unknown_parent"})
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_UNKNOWN_PARENT_DETAIL
            ) from exc
        logger.error("category_create_failed", extra={"sqlstate": sqlstate})
        raise


@categories_router.get("", response_model=list[CategoryResponse])
async def list_categories_route(
    user: CurrentUser,
    session: SessionDep,
    include_archived: bool = False,
) -> Sequence[Category]:
    """List categories (flat). `include_archived=false` (default) excludes tombstones."""
    return await list_categories(session, include_archived=include_archived)


@categories_router.patch("/{category_id}", response_model=CategoryResponse)
async def patch_category_route(
    category_id: UUID,
    body: CategoryUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> Category:
    """Edit `name`/`color`/`icon` (partial); 404 if unknown or archived.

    A `parent_id` in the body is a 422 (`extra="forbid"` — re-parenting has its
    own route). An archived category is invisible → uniform 404 (D10).
    """
    category = await update_category(
        session, category_id=category_id, fields=body.model_dump(exclude_unset=True)
    )
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)
    return category


@categories_router.patch("/{category_id}/parent", response_model=CategoryResponse)
async def move_category_route(
    category_id: UUID,
    body: CategoryMove,
    user: CurrentUser,
    session: SessionDep,
) -> Category:
    """Re-parent a category and audit the move in the **same** transaction (D5/D6).

    The cycle check runs *before* the write, so a rejected move (422) raises
    before the audit call — no audit row, no mutation (critère #4). On success
    `move_category` and `log_admin_action` share the transaction `get_db`
    owns: if the audit INSERT fails, the move rolls back too (atomic pair).
    A concurrent mover that loses the serialisation race surfaces as 40001 →
    409 retry, never a 500 or a silently-created cycle (D7).
    """
    try:
        category, from_parent = await move_category(
            session, category_id=category_id, new_parent_id=body.parent_id
        )
    except CategoryNotFoundError as exc:
        logger.info("category_move_rejected", extra={"error": type(exc).__name__})
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL) from exc
    except CategoryCycleError as exc:  # raised BEFORE the write ⇒ no audit row (D6)
        logger.info("category_move_rejected", extra={"error": type(exc).__name__})
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_CYCLE_DETAIL) from exc
    except IntegrityError as exc:  # unknown new parent (FK 23503)
        if getattr(exc.orig, "sqlstate", None) == "23503":
            logger.info("category_move_rejected", extra={"error": "unknown_parent"})
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_UNKNOWN_PARENT_DETAIL
            ) from exc
        logger.error(
            "category_move_failed", extra={"sqlstate": getattr(exc.orig, "sqlstate", None)}
        )
        raise
    except DBAPIError as exc:
        sqlstate = getattr(exc.orig, "sqlstate", None)
        if sqlstate in _SERIALIZE_SQLSTATES:
            logger.warning("category_move_serialize_retry", extra={"sqlstate": sqlstate})
            raise HTTPException(status.HTTP_409_CONFLICT, detail=_RETRY_DETAIL) from exc
        logger.error("category_move_failed", extra={"sqlstate": sqlstate})
        raise

    # Audit in the SAME transaction (D5/D6). UUID-string metadata only — none
    # of these keys trips `log_admin_action`'s secret-key blacklist; `target`
    # stays NULL (the moved thing is a category, not a user).
    await log_admin_action(
        session,
        action=AdminAction.CATEGORY_MOVED,
        by=user.id,
        target=None,
        metadata={
            "category_id": str(category_id),
            "from_parent_id": str(from_parent) if from_parent is not None else None,
            "to_parent_id": str(body.parent_id) if body.parent_id is not None else None,
        },
    )
    return category


@categories_router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category_route(
    category_id: UUID,
    user: CurrentUser,
    session: SessionDep,
) -> Response:
    """Soft-delete (archive) a category; never a hard delete (D9).

    The row is preserved with `archived_at` set, and drops out of the default
    listing. A re-DELETE of an already-archived category → 404 (idempotent in
    the "no corruption" sense, gabarit `accounts.archive`). The hard-delete
    service (`delete_category`) is deliberately NOT routed (D8): a category
    with children is archived here, never refused.
    """
    if not await archive_category(session, category_id=category_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_DETAIL)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
