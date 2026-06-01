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

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.public import User, get_current_user
from backend.modules.budget.domain import CategoryCycleError
from backend.modules.budget.models import Category
from backend.modules.budget.schemas import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
)
from backend.modules.budget.service.categories import (
    create_category,
    list_categories,
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
