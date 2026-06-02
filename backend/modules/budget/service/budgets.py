"""Budget listing service (S08.2): budgets concerning a user, with consumption.

`list_active_budgets_for_user` returns every non-archived budget the user takes
part in — both `personal` (the user is its sole contributor, the owner — S08.1)
and `shared` (the user is one of its contributors) — each paired with its
`BudgetConsumption` at `as_of`. Membership is read uniformly through the
`BudgetContributor` association, so the two scopes need no special-casing
(S08.1 guarantees a `personal` budget has exactly one contributor: its owner).

Read-only (ADR 0015): no flush/commit. `as_of` is a required keyword (the route
S08.4 supplies the default) so the listing stays deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.budget.domain import BudgetConsumption
from backend.modules.budget.models import Budget, BudgetContributor
from backend.modules.budget.service.consumption import compute_consumption


@dataclass(frozen=True, slots=True)
class BudgetWithConsumption:
    """Un budget concernant l'utilisateur + sa consommation à `as_of`.

    Tuple typé (dataclass, pas dict) pour le typage strict de la route S08.4 qui
    mappe ensuite vers `Money` + applique le RBAC.
    """

    budget: Budget
    consumption: BudgetConsumption


async def list_active_budgets_for_user(
    session: AsyncSession, *, user_id: UUID, as_of: date
) -> list[BudgetWithConsumption]:
    """Budgets non archivés concernant `user_id` (contributeur), + consommation.

    L'appartenance par `BudgetContributor` couvre `personal` (owner = unique
    contributeur, S08.1) **et** `shared`. Ordre déterministe `(created_at, id)`
    (le tie-breaker `id` stabilise l'ordre de deux budgets au même `created_at`,
    gabarit `list_categories`). Lecture seule (ADR 0015).
    """
    stmt = (
        select(Budget)
        .join(BudgetContributor, BudgetContributor.budget_id == Budget.id)
        .where(BudgetContributor.user_id == user_id, Budget.archived_at.is_(None))
        .order_by(Budget.created_at, Budget.id)
    )
    budgets = (await session.execute(stmt)).scalars().all()
    result: list[BudgetWithConsumption] = []
    for budget in budgets:
        consumption = await compute_consumption(session, budget_id=budget.id, as_of=as_of)
        if consumption is not None:  # budget chargé → jamais None ; garde défensive
            result.append(BudgetWithConsumption(budget=budget, consumption=consumption))
    return result
