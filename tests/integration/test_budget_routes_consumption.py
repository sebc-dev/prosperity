"""Integration tests for `GET /budgets/{id}/consumption` (S08.4, P08.4.2).

Tests the **HTTP contract** only — status, schema, `percent` Decimal
serialisation, RBAC 404 (gabarit watertight D3). The business filter matrix
(canonical form E15, `force_full_debt`, currency mismatch, subtree, contributors,
`confirmed`-only) is already covered exhaustively at the service level by
`test_budget_consumption.py`; re-deriving it here would be redundant
(anti-pattern §528). Seeds always pass an explicit `as_of` (no implicit
`date.today()` → no temporal fragility), except the single "as_of omitted →
default" path which asserts only a coherent 200, never an exact value.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.modules.accounts.models import Household
from backend.modules.auth.service.jwt import issue_access_token
from backend.modules.budget.models import Budget, BudgetContributor, Category
from backend.modules.transactions.models import Split, Transaction
from tests.factories.sqlalchemy import UserFactory

_settings = get_settings()

FactoryBundle = Callable[[], Awaitable[tuple[type, type, type]]]

_PERIOD_START = date(2026, 6, 1)
_AS_OF = "2026-06-15"
_IN_WINDOW = date(2026, 6, 10)
_NOT_FOUND_DETAIL = "Budget not found."


@pytest_asyncio.fixture(loop_scope="session")
async def initialized_household(auth_schema: AsyncSession) -> AsyncSession:
    def _seed(s: Session) -> None:
        s.add(
            Household(
                name="Test Household",
                base_currency="EUR",
                initialized_at=datetime.now(tz=UTC),
            )
        )

    await auth_schema.run_sync(_seed)
    return auth_schema


def _bearer(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


def _add_expense(  # noqa: PLR0913 — parametrable seed helper
    s: Session,
    *,
    account_id: UUID,
    category_id: UUID,
    amount: int,
    created_by: UUID,
    on: date,
) -> None:
    tx = Transaction(
        account_id=account_id,
        date=on,
        state="confirmed",
        created_by=created_by,
        debt_generation_override="default",
    )
    s.add(tx)
    s.flush()
    s.add_all(
        [
            Split(
                transaction_id=tx.id,
                account_id=account_id,
                category_id=None,
                amount_cents=-amount,
                currency="EUR",
            ),
            Split(
                transaction_id=tx.id,
                account_id=account_id,
                category_id=category_id,
                amount_cents=amount,
                currency="EUR",
            ),
        ]
    )
    s.flush()


def _make_personal_budget(
    s: Session, *, owner_id: UUID, category_id: UUID, amount_cents: int = 40000
) -> UUID:
    budget = Budget(
        category_id=category_id,
        period_kind="monthly",
        period_start=_PERIOD_START,
        amount_cents=amount_cents,
        currency="EUR",
        scope="personal",
        created_by=owner_id,
    )
    s.add(budget)
    s.flush()
    s.add(BudgetContributor(budget_id=budget.id, user_id=owner_id))
    s.flush()
    return budget.id


# ---------------------------------------------------------------------------
# 200 — HTTP contract
# ---------------------------------------------------------------------------


async def test_consumption_200_shape_and_values(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="cons-200@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        _add_expense(
            s,
            account_id=acc.id,
            category_id=cat.id,
            amount=20000,
            created_by=owner.id,
            on=_IN_WINDOW,
        )
        return owner.id, _make_personal_budget(s, owner_id=owner.id, category_id=cat.id)

    owner_id, budget_id = await initialized_household.run_sync(_seed)

    resp = await async_client.get(
        f"/budgets/{budget_id}/consumption", params={"as_of": _AS_OF}, headers=_bearer(owner_id)
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"consumed_cents", "remaining_cents", "percent", "splits_count"}
    assert body["consumed_cents"] == 20000
    assert body["remaining_cents"] == 20000
    assert body["splits_count"] == 1
    # `percent` is the raw ratio (0.5), serialised from a Decimal.
    assert Decimal(str(body["percent"])) == Decimal("0.5")


async def test_consumption_200_other_period_window(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # An explicit as_of in a different month sees that month's consumption only.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="cons-window@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        _add_expense(
            s,
            account_id=acc.id,
            category_id=cat.id,
            amount=5000,
            created_by=owner.id,
            on=date(2026, 6, 10),
        )
        _add_expense(
            s,
            account_id=acc.id,
            category_id=cat.id,
            amount=8000,
            created_by=owner.id,
            on=date(2026, 7, 10),
        )
        return owner.id, _make_personal_budget(s, owner_id=owner.id, category_id=cat.id)

    owner_id, budget_id = await initialized_household.run_sync(_seed)

    resp = await async_client.get(
        f"/budgets/{budget_id}/consumption",
        params={"as_of": "2026-07-15"},
        headers=_bearer(owner_id),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["consumed_cents"] == 8000  # July window only


async def test_consumption_200_as_of_default_today(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # as_of omitted → route defaults to date.today(); assert a coherent 200, no
    # exact value (avoids clock fragility — covers the default path only).
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="cons-today@example.com")
        account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        return owner.id, _make_personal_budget(s, owner_id=owner.id, category_id=cat.id)

    owner_id, budget_id = await initialized_household.run_sync(_seed)

    resp = await async_client.get(f"/budgets/{budget_id}/consumption", headers=_bearer(owner_id))

    assert resp.status_code == 200, resp.text
    assert resp.json()["splits_count"] >= 0


# ---------------------------------------------------------------------------
# RBAC 404 + 401
# ---------------------------------------------------------------------------


async def test_consumption_404_non_contributor(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        a = user_factory(email="cons-rbac-a@example.com")
        b = user_factory(email="cons-rbac-b@example.com")
        common = account_factory(owner_id=None, name="Commun")
        member_factory(account_id=common.id, user_id=a.id)
        member_factory(account_id=common.id, user_id=b.id)
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        budget = Budget(
            category_id=cat.id,
            period_kind="monthly",
            period_start=_PERIOD_START,
            amount_cents=40000,
            currency="EUR",
            scope="shared",
            created_by=a.id,
        )
        s.add(budget)
        s.flush()
        s.add_all(
            [
                BudgetContributor(budget_id=budget.id, user_id=a.id),
                BudgetContributor(budget_id=budget.id, user_id=b.id),
            ]
        )
        s.flush()
        return a.id, budget.id

    _a_id, budget_id = await initialized_household.run_sync(_seed)

    def _make_outsider(s: Session) -> UUID:
        UserFactory._meta.sqlalchemy_session = s  # type: ignore[attr-defined]
        return UserFactory(email="cons-outsider@example.com").id

    outsider_id = await initialized_household.run_sync(_make_outsider)

    resp = await async_client.get(f"/budgets/{budget_id}/consumption", headers=_bearer(outsider_id))

    assert resp.status_code == 404
    assert resp.json()["detail"] == _NOT_FOUND_DETAIL


async def test_consumption_404_unknown(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, _a, _m = await bound_account_factories()
    user = await initialized_household.run_sync(
        lambda _s: user_factory(email="cons-unk@example.com")
    )

    resp = await async_client.get(f"/budgets/{uuid4()}/consumption", headers=_bearer(user.id))
    assert resp.status_code == 404
    assert resp.json()["detail"] == _NOT_FOUND_DETAIL


async def test_consumption_404_archived(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, _a, _m = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="cons-arch@example.com")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        budget = Budget(
            category_id=cat.id,
            period_kind="monthly",
            period_start=_PERIOD_START,
            amount_cents=40000,
            currency="EUR",
            scope="personal",
            created_by=owner.id,
            archived_at=datetime.now(UTC),
        )
        s.add(budget)
        s.flush()
        s.add(BudgetContributor(budget_id=budget.id, user_id=owner.id))
        s.flush()
        return owner.id, budget.id

    owner_id, budget_id = await initialized_household.run_sync(_seed)

    resp = await async_client.get(f"/budgets/{budget_id}/consumption", headers=_bearer(owner_id))
    assert resp.status_code == 404
    assert resp.json()["detail"] == _NOT_FOUND_DETAIL


async def test_consumption_401_anonymous(
    async_client: AsyncClient, initialized_household: AsyncSession
) -> None:
    resp = await async_client.get(f"/budgets/{uuid4()}/consumption")
    assert resp.status_code == 401
