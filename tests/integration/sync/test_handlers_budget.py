"""Intégration — sous-handler `budget` (categories + budgets, S13.4 / P13.4.3, delta D5).

Route `categories` ET `budgets` vers `budget.public`. Vérifie les allowlists FERMÉES
(aucun `setattr` aveugle hors `{name,color,icon}` / `{amount_cents,carry_over_remainder}`),
le routage `update→move_category` sur changement de parent, le forçage `created_by`/
`user_id`. Oracle = état DB / code d'erreur / `pytest.raises` (cas « propage »).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.models import User
from backend.modules.budget.domain import CategoryCycleError
from backend.modules.budget.models import Budget, BudgetContributor, Category
from backend.modules.sync.public import BatchUpload, Mutation, WriteResult
from backend.modules.sync.service.dispatcher import process_batch

_CategoryFactory = Callable[..., Awaitable[Category]]
_UserFactory = Callable[..., Awaitable[User]]


def _mut(table: str, op: str, payload: Mapping[str, object]) -> Mutation:
    return Mutation(client_request_id=uuid.uuid4(), table=table, op=op, payload=dict(payload))  # type: ignore[arg-type]


async def _run(session: AsyncSession, user: User, mutation: Mutation) -> WriteResult:
    [result] = await process_batch(session, user, BatchUpload(mutations=[mutation]))
    return result


# ── categories ──────────────────────────────────────────────────────────────
async def test_category_insert_creates(
    initialized_household: AsyncSession, bound_user_factory: _UserFactory
) -> None:
    user = await bound_user_factory(email="cat@ex.com")
    result = await _run(
        initialized_household, user, _mut("categories", "insert", {"name": "Courses"})
    )

    assert result.success is True
    cat = (
        await initialized_household.execute(select(Category).where(Category.name == "Courses"))
    ).scalar_one()
    assert cat.archived_at is None


async def test_category_update_renames(
    initialized_household: AsyncSession,
    bound_user_factory: _UserFactory,
    bound_category_factory: _CategoryFactory,
) -> None:
    user = await bound_user_factory(email="cat2@ex.com")
    cat = await bound_category_factory(name="Avant")
    await _run(
        initialized_household,
        user,
        _mut("categories", "update", {"id": str(cat.id), "name": "Après"}),
    )
    refreshed = await initialized_household.get(Category, cat.id)
    assert refreshed is not None
    assert refreshed.name == "Après"


async def test_category_update_parent_routes_move(
    initialized_household: AsyncSession,
    bound_user_factory: _UserFactory,
    bound_category_factory: _CategoryFactory,
) -> None:
    user = await bound_user_factory(email="cat3@ex.com")
    parent = await bound_category_factory(name="Parent")
    child = await bound_category_factory(name="Child")
    await _run(
        initialized_household,
        user,
        _mut("categories", "update", {"id": str(child.id), "parent_id": str(parent.id)}),
    )
    refreshed = await initialized_household.get(Category, child.id)
    assert refreshed is not None
    assert refreshed.parent_id == parent.id


async def test_category_move_cycle_raises(
    initialized_household: AsyncSession,
    bound_user_factory: _UserFactory,
    bound_category_factory: _CategoryFactory,
) -> None:
    """Un re-parentage qui fermerait un cycle PROPAGE `CategoryCycleError` (D-I)."""
    user = await bound_user_factory(email="cat4@ex.com")
    a = await bound_category_factory(name="A")
    b = await bound_category_factory(name="B", parent_id=a.id)
    with pytest.raises(CategoryCycleError):
        await _run(
            initialized_household,
            user,
            _mut("categories", "update", {"id": str(a.id), "parent_id": str(b.id)}),
        )


async def test_category_update_rejects_non_allowlisted(
    initialized_household: AsyncSession,
    bound_user_factory: _UserFactory,
    bound_category_factory: _CategoryFactory,
) -> None:
    """Un champ hors allowlist (`archived_at`) → `ValidationError` — jamais un
    `setattr` aveugle (mass-assignment fermé, D-L)."""
    user = await bound_user_factory(email="cat5@ex.com")
    cat = await bound_category_factory(name="C")
    payload = {"id": str(cat.id), "archived_at": "2026-01-01T00:00:00Z"}
    with pytest.raises(ValidationError):
        await _run(initialized_household, user, _mut("categories", "update", payload))


async def test_category_delete_archives(
    initialized_household: AsyncSession,
    bound_user_factory: _UserFactory,
    bound_category_factory: _CategoryFactory,
) -> None:
    user = await bound_user_factory(email="cat6@ex.com")
    cat = await bound_category_factory(name="ToArchive")
    result = await _run(
        initialized_household, user, _mut("categories", "delete", {"id": str(cat.id)})
    )

    assert result.success is True
    refreshed = await initialized_household.get(Category, cat.id)
    assert refreshed is not None
    assert refreshed.archived_at is not None


# ── budgets ───────────────────────────────────────────────────────────────────
def _budget_payload(category_id: uuid.UUID) -> dict[str, object]:
    return {
        "category_id": str(category_id),
        "period_kind": "monthly",
        "period_start": "2026-06-01",
        "amount_cents": 30000,
        "scope": "personal",
        "carry_over_remainder": False,
        "contributor_ids": [],  # rempli par l'appelant avec user.id
    }


async def test_budget_insert_creates_with_contributors(
    initialized_household: AsyncSession,
    bound_user_factory: _UserFactory,
    bound_category_factory: _CategoryFactory,
) -> None:
    user = await bound_user_factory(email="bud@ex.com")
    cat = await bound_category_factory(name="BudCat")
    payload = _budget_payload(cat.id) | {"contributor_ids": [str(user.id)]}
    result = await _run(initialized_household, user, _mut("budgets", "insert", payload))

    assert result.success is True
    budget = (
        await initialized_household.execute(select(Budget).where(Budget.category_id == cat.id))
    ).scalar_one()
    assert budget.created_by == user.id
    contributors = (
        await initialized_household.execute(
            select(func.count())
            .select_from(BudgetContributor)
            .where(BudgetContributor.budget_id == budget.id)
        )
    ).scalar_one()
    assert contributors == 1


async def test_budget_insert_rejects_created_by_in_payload(
    initialized_household: AsyncSession,
    bound_user_factory: _UserFactory,
    bound_category_factory: _CategoryFactory,
) -> None:
    user = await bound_user_factory(email="bud2@ex.com")
    cat = await bound_category_factory(name="BudCat2")
    payload = _budget_payload(cat.id) | {
        "contributor_ids": [str(user.id)],
        "created_by": str(user.id),
    }
    with pytest.raises(ValidationError):
        await _run(initialized_household, user, _mut("budgets", "insert", payload))


async def test_budget_update_amount(
    initialized_household: AsyncSession,
    bound_user_factory: _UserFactory,
    bound_category_factory: _CategoryFactory,
) -> None:
    user = await bound_user_factory(email="bud3@ex.com")
    cat = await bound_category_factory(name="BudCat3")
    await _run(
        initialized_household,
        user,
        _mut("budgets", "insert", _budget_payload(cat.id) | {"contributor_ids": [str(user.id)]}),
    )
    budget = (
        await initialized_household.execute(select(Budget).where(Budget.category_id == cat.id))
    ).scalar_one()

    await _run(
        initialized_household,
        user,
        _mut("budgets", "update", {"id": str(budget.id), "amount_cents": 45000}),
    )
    await initialized_household.refresh(budget)
    assert budget.amount_cents == 45000


async def test_budget_delete_archives(
    initialized_household: AsyncSession,
    bound_user_factory: _UserFactory,
    bound_category_factory: _CategoryFactory,
) -> None:
    user = await bound_user_factory(email="bud4@ex.com")
    cat = await bound_category_factory(name="BudCat4")
    await _run(
        initialized_household,
        user,
        _mut("budgets", "insert", _budget_payload(cat.id) | {"contributor_ids": [str(user.id)]}),
    )
    budget = (
        await initialized_household.execute(select(Budget).where(Budget.category_id == cat.id))
    ).scalar_one()

    result = await _run(
        initialized_household, user, _mut("budgets", "delete", {"id": str(budget.id)})
    )
    assert result.success is True
    await initialized_household.refresh(budget)
    assert budget.archived_at is not None


async def test_categories_and_budgets_both_routed(
    initialized_household: AsyncSession,
    bound_user_factory: _UserFactory,
    bound_category_factory: _CategoryFactory,
) -> None:
    """Batch mixte `categories/insert` + `budgets/insert` → les deux tables routées
    par le même module handler (D5)."""
    user = await bound_user_factory(email="mix@ex.com")
    cat = await bound_category_factory(name="MixCat")
    batch = BatchUpload(
        mutations=[
            _mut("categories", "insert", {"name": "MixNew"}),
            _mut(
                "budgets", "insert", _budget_payload(cat.id) | {"contributor_ids": [str(user.id)]}
            ),
        ]
    )
    cat_res, bud_res = await process_batch(initialized_household, user, batch)
    assert cat_res.success is True
    assert bud_res.success is True
