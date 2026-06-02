"""Integration tests for `list_active_budgets_for_user` (S08.2, P08.2.3).

Lists every non-archived budget a user takes part in (contributor) — personal
and shared — each with its `BudgetConsumption`. Driven against a real Postgres
so the `BudgetContributor` join, the archived-exclusion and the deterministic
`(created_at, id)` order fire. Gabarit `test_budget_consumption.py` (direct ORM
seed in `run_sync`).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.modules.budget.models import Budget, BudgetContributor, Category
from backend.modules.budget.service.budgets import list_active_budgets_for_user
from backend.modules.budget.service.consumption import compute_consumption
from backend.modules.transactions.models import Split, Transaction

FactoryBundle = Callable[[], Awaitable[tuple[type, type, type]]]

_PERIOD_START = date(2026, 6, 1)
_AS_OF = date(2026, 6, 15)


def _make_budget(  # noqa: PLR0913 — helper paramétrable de seed (scope/contrib/archivé)
    session: Session,
    *,
    category_id: UUID,
    created_by: UUID,
    contributor_ids: tuple[UUID, ...],
    scope: str = "personal",
    archived: bool = False,
) -> UUID:
    budget = Budget(
        category_id=category_id,
        period_kind="monthly",
        period_start=_PERIOD_START,
        amount_cents=40000,
        currency="EUR",
        scope=scope,
        created_by=created_by,
        archived_at=datetime.now(tz=UTC) if archived else None,
    )
    session.add(budget)
    session.flush()
    for uid in contributor_ids:
        session.add(BudgetContributor(budget_id=budget.id, user_id=uid))
    session.flush()
    return budget.id


async def test_lists_personal_and_shared_budgets_of_user(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID, UUID]:
        a = user_factory(email="la-a@example.com")
        b = user_factory(email="la-b@example.com")
        account_factory(owner_id=a.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        perso = _make_budget(s, category_id=cat.id, created_by=a.id, contributor_ids=(a.id,))
        shared = _make_budget(
            s, category_id=cat.id, created_by=a.id, scope="shared", contributor_ids=(a.id, b.id)
        )
        return a.id, perso, shared

    user_id, perso_id, shared_id = await household_singleton.run_sync(_seed)

    rows = await list_active_budgets_for_user(household_singleton, user_id=user_id, as_of=_AS_OF)
    assert {r.budget.id for r in rows} == {perso_id, shared_id}
    assert all(r.consumption is not None for r in rows)


async def test_excludes_archived_budgets(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    user_factory, _account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        a = user_factory(email="arch@example.com")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        active = _make_budget(s, category_id=cat.id, created_by=a.id, contributor_ids=(a.id,))
        _make_budget(s, category_id=cat.id, created_by=a.id, contributor_ids=(a.id,), archived=True)
        return a.id, active

    user_id, active_id = await household_singleton.run_sync(_seed)

    rows = await list_active_budgets_for_user(household_singleton, user_id=user_id, as_of=_AS_OF)
    assert [r.budget.id for r in rows] == [active_id]


async def test_excludes_budgets_of_other_user(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    user_factory, _account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> UUID:
        a = user_factory(email="me@example.com")
        b = user_factory(email="other@example.com")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        # Budget de B uniquement : A n'en est pas contributeur.
        _make_budget(s, category_id=cat.id, created_by=b.id, contributor_ids=(b.id,))
        return a.id

    user_id = await household_singleton.run_sync(_seed)

    rows = await list_active_budgets_for_user(household_singleton, user_id=user_id, as_of=_AS_OF)
    assert rows == []


async def test_consumption_attached_is_correct(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        a = user_factory(email="cons@example.com")
        acc = account_factory(owner_id=a.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        tx = Transaction(
            account_id=acc.id, date=date(2026, 6, 10), state="confirmed", created_by=a.id
        )
        s.add(tx)
        s.flush()
        s.add_all(
            [
                Split(
                    transaction_id=tx.id,
                    account_id=acc.id,
                    category_id=None,
                    amount_cents=-5000,
                    currency="EUR",
                ),
                Split(
                    transaction_id=tx.id,
                    account_id=acc.id,
                    category_id=cat.id,
                    amount_cents=5000,
                    currency="EUR",
                ),
            ]
        )
        s.flush()
        budget_id = _make_budget(s, category_id=cat.id, created_by=a.id, contributor_ids=(a.id,))
        return a.id, budget_id

    user_id, budget_id = await household_singleton.run_sync(_seed)

    rows = await list_active_budgets_for_user(household_singleton, user_id=user_id, as_of=_AS_OF)
    direct = await compute_consumption(household_singleton, budget_id=budget_id, as_of=_AS_OF)
    assert len(rows) == 1
    assert rows[0].consumption == direct
    assert rows[0].consumption.consumed_cents == 5000


async def test_deterministic_order(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    user_factory, _account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, list[UUID]]:
        a = user_factory(email="order@example.com")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        ids = [
            _make_budget(s, category_id=cat.id, created_by=a.id, contributor_ids=(a.id,))
            for _ in range(3)
        ]
        return a.id, ids

    user_id, _ids = await household_singleton.run_sync(_seed)

    first = await list_active_budgets_for_user(household_singleton, user_id=user_id, as_of=_AS_OF)
    second = await list_active_budgets_for_user(household_singleton, user_id=user_id, as_of=_AS_OF)
    assert [r.budget.id for r in first] == [r.budget.id for r in second]
    assert len(first) == 3


async def test_empty_when_no_budget(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    user_factory, _account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> UUID:
        return user_factory(email="nobudget@example.com").id

    user_id = await household_singleton.run_sync(_seed)

    assert (
        await list_active_budgets_for_user(household_singleton, user_id=user_id, as_of=_AS_OF) == []
    )
