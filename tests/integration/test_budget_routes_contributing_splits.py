"""Integration tests for `GET /budgets/{id}/contributing-splits` (S08.4, P08.4.3).

Drill-down of the splits feeding a budget's consumption, cursor-paginated
(gabarit `GET /transactions` S07.5). Covers the **new** query's own filters
(`list_contributing_splits` is a fresh SELECT, not the SUM aggregate — so its
filters deserve their own tests, no duplication with `test_budget_consumption.py`)
and the pagination contract: keyset stability, the `limit+1` boundary, `limit`
bounds, same-date tie-break by `id`, opaque/malformed cursors, and the
cross-budget cursor non-widening (D3). Coherence with `splits_count` is pinned
(D13: same `_consumption_filters`).

The `transactions`/`splits` ORM models are imported **only in the test**; the
service reads them via Core. Split ids are set explicitly (`UUID(int=k)`) where
ordering is asserted, so `(date, id)` is deterministic.
"""

from __future__ import annotations

import base64
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.modules.accounts.models import Household
from backend.modules.accounts.service.household import invalidate_household_cache
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


@pytest.fixture(autouse=True)
def _reset_household_cache() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    invalidate_household_cache()
    yield
    invalidate_household_cache()


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


def _add_split(  # noqa: PLR0913 — parametrable seed helper
    s: Session,
    *,
    account_id: UUID,
    category_id: UUID | None,
    amount: int,
    created_by: UUID,
    split_id: UUID | None = None,
    on: date = _IN_WINDOW,
    state: str = "confirmed",
    override: str = "default",
    currency: str = "EUR",
) -> UUID:
    """Persist a canonical expense (account leg + ONE category leg). Returns the
    category-leg split id (the counted one; its id drives the cursor)."""
    tx = Transaction(
        account_id=account_id,
        date=on,
        state=state,
        created_by=created_by,
        debt_generation_override=override,
    )
    s.add(tx)
    s.flush()
    s.add(
        Split(
            transaction_id=tx.id,
            account_id=account_id,
            category_id=None,
            amount_cents=-amount,
            currency="EUR",
        )
    )
    leg = Split(
        transaction_id=tx.id,
        account_id=account_id,
        category_id=category_id,
        amount_cents=amount,
        currency=currency,
    )
    if split_id is not None:
        leg.id = split_id
    s.add(leg)
    s.flush()
    return leg.id


def _make_personal_budget(s: Session, *, owner_id: UUID, category_id: UUID) -> UUID:
    budget = Budget(
        category_id=category_id,
        period_kind="monthly",
        period_start=_PERIOD_START,
        amount_cents=10_000_000,
        currency="EUR",
        scope="personal",
        created_by=owner_id,
    )
    s.add(budget)
    s.flush()
    s.add(BudgetContributor(budget_id=budget.id, user_id=owner_id))
    s.flush()
    return budget.id


async def _make_outsider(session: AsyncSession, email: str) -> UUID:
    def _make(s: Session) -> UUID:
        UserFactory._meta.sqlalchemy_session = s  # type: ignore[attr-defined]
        return UserFactory(email=email).id

    return await session.run_sync(_make)


def _ids(resp_json: dict) -> list[str]:
    return [it["id"] for it in resp_json["items"]]


# ---------------------------------------------------------------------------
# Content / coherence with splits_count
# ---------------------------------------------------------------------------


async def test_lists_only_counted_splits_matches_splits_count(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="csplit-content@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        budget_cat = Category(name="Budgétée")
        sibling = Category(name="Hors budget")
        s.add_all([budget_cat, sibling])
        s.flush()
        # 3 counted splits + noise that must NOT appear.
        for amt in (1000, 2000, 3000):
            _add_split(
                s, account_id=acc.id, category_id=budget_cat.id, amount=amt, created_by=owner.id
            )
        _add_split(s, account_id=acc.id, category_id=sibling.id, amount=9999, created_by=owner.id)
        return owner.id, _make_personal_budget(s, owner_id=owner.id, category_id=budget_cat.id)

    owner_id, budget_id = await initialized_household.run_sync(_seed)

    splits = await async_client.get(
        f"/budgets/{budget_id}/contributing-splits",
        params={"as_of": _AS_OF},
        headers=_bearer(owner_id),
    )
    assert splits.status_code == 200, splits.text
    body = splits.json()
    assert len(body["items"]) == 3
    assert body["next_cursor"] is None
    # Each item carries a non-NULL category_id (canonical form, account leg excluded).
    assert all(it["category_id"] is not None for it in body["items"])

    cons = await async_client.get(
        f"/budgets/{budget_id}/consumption", params={"as_of": _AS_OF}, headers=_bearer(owner_id)
    )
    assert cons.json()["splits_count"] == len(body["items"])  # coherence (D13)


async def test_cross_invariant_empty_drill_down(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # D4 re-affirmed on the drill-down side: shared {A,B} validated while the only
    # common account is {A,B,C} → subset filter → [] AND splits_count == 0.
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        a = user_factory(email="csplit-d4-a@example.com")
        b = user_factory(email="csplit-d4-b@example.com")
        c = user_factory(email="csplit-d4-c@example.com")
        abc = account_factory(owner_id=None, name="ABC")
        for u, r in ((a, "0.3333"), (b, "0.3333"), (c, "0.3334")):
            member_factory(account_id=abc.id, user_id=u.id, default_share_ratio=r)
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        _add_split(s, account_id=abc.id, category_id=cat.id, amount=9000, created_by=a.id)
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

    a_id, budget_id = await initialized_household.run_sync(_seed)

    resp = await async_client.get(
        f"/budgets/{budget_id}/contributing-splits",
        params={"as_of": _AS_OF},
        headers=_bearer(a_id),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == []
    assert resp.json()["next_cursor"] is None


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


async def _seed_personal_with_n_splits(
    session: AsyncSession,
    factories: FactoryBundle,
    *,
    email: str,
    n: int,
    same_date: bool = False,
) -> tuple[UUID, UUID, list[UUID]]:
    """Seed a personal budget + N counted splits with explicit ids `UUID(int=1..N)`.

    Distinct dates (descending id ⇒ descending date) unless `same_date`, in which
    case all share `_IN_WINDOW` so the `(date, id)` total order rests on `id`.
    Returns (owner_id, budget_id, split_ids sorted ascending).
    """
    user_factory, account_factory, _ = await factories()

    def _seed(s: Session) -> tuple[UUID, UUID, list[UUID]]:
        owner = user_factory(email=email)
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        ids = []
        for k in range(1, n + 1):
            on = _IN_WINDOW if same_date else date(2026, 6, k)
            sid = _add_split(
                s,
                account_id=acc.id,
                category_id=cat.id,
                amount=100 * k,
                created_by=owner.id,
                split_id=UUID(int=k),
                on=on,
            )
            ids.append(sid)
        return owner.id, _make_personal_budget(s, owner_id=owner.id, category_id=cat.id), ids

    return await session.run_sync(_seed)


async def test_pagination_two_pages_no_overlap(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    owner_id, budget_id, _ids_seed = await _seed_personal_with_n_splits(
        initialized_household, bound_account_factories, email="csplit-pg@example.com", n=5
    )

    page1 = await async_client.get(
        f"/budgets/{budget_id}/contributing-splits",
        params={"as_of": _AS_OF, "limit": 3},
        headers=_bearer(owner_id),
    )
    assert page1.status_code == 200, page1.text
    b1 = page1.json()
    assert len(b1["items"]) == 3
    assert b1["next_cursor"] is not None

    page2 = await async_client.get(
        f"/budgets/{budget_id}/contributing-splits",
        params={"as_of": _AS_OF, "limit": 3, "cursor": b1["next_cursor"]},
        headers=_bearer(owner_id),
    )
    assert page2.status_code == 200, page2.text
    b2 = page2.json()
    assert len(b2["items"]) == 2
    assert b2["next_cursor"] is None
    # No overlap, no skip: the union is exactly the 5 splits.
    assert set(_ids(b1)) | set(_ids(b2)) == {str(UUID(int=k)) for k in range(1, 6)}
    assert set(_ids(b1)) & set(_ids(b2)) == set()


async def test_pagination_boundary_limit_equals_n(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # N == limit ⇒ full page WITH next_cursor null (no superfluous empty page —
    # exercises the `len(rows) > limit` branch).
    owner_id, budget_id, _ids_seed = await _seed_personal_with_n_splits(
        initialized_household, bound_account_factories, email="csplit-bound@example.com", n=3
    )

    resp = await async_client.get(
        f"/budgets/{budget_id}/contributing-splits",
        params={"as_of": _AS_OF, "limit": 3},
        headers=_bearer(owner_id),
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["items"]) == 3
    assert resp.json()["next_cursor"] is None


@pytest.mark.parametrize("limit", [0, 101])
async def test_pagination_limit_out_of_bounds(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
    limit: int,
) -> None:
    owner_id, budget_id, _ids_seed = await _seed_personal_with_n_splits(
        initialized_household, bound_account_factories, email=f"csplit-lim{limit}@example.com", n=1
    )

    resp = await async_client.get(
        f"/budgets/{budget_id}/contributing-splits",
        params={"as_of": _AS_OF, "limit": limit},
        headers=_bearer(owner_id),
    )
    assert resp.status_code == 422


async def test_pagination_same_date_tiebreak_by_id(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # Several splits sharing the SAME transactions.date → the total order rests on
    # `id`; following the cursor across that frontier neither skips nor repeats.
    owner_id, budget_id, _ids_seed = await _seed_personal_with_n_splits(
        initialized_household,
        bound_account_factories,
        email="csplit-samedate@example.com",
        n=4,
        same_date=True,
    )

    page1 = await async_client.get(
        f"/budgets/{budget_id}/contributing-splits",
        params={"as_of": _AS_OF, "limit": 2},
        headers=_bearer(owner_id),
    )
    b1 = page1.json()
    assert b1["next_cursor"] is not None
    page2 = await async_client.get(
        f"/budgets/{budget_id}/contributing-splits",
        params={"as_of": _AS_OF, "limit": 2, "cursor": b1["next_cursor"]},
        headers=_bearer(owner_id),
    )
    b2 = page2.json()
    # DESC by id (all same date): [4,3] then [2,1], total order, no overlap.
    assert _ids(b1) == [str(UUID(int=4)), str(UUID(int=3))]
    assert _ids(b2) == [str(UUID(int=2)), str(UUID(int=1))]
    assert b2["next_cursor"] is None


# ---------------------------------------------------------------------------
# Cursor: opaque + malformed + cross-budget non-widening
# ---------------------------------------------------------------------------


async def test_cursor_is_opaque_base64(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    owner_id, budget_id, _ids_seed = await _seed_personal_with_n_splits(
        initialized_household, bound_account_factories, email="csplit-opaque@example.com", n=2
    )
    resp = await async_client.get(
        f"/budgets/{budget_id}/contributing-splits",
        params={"as_of": _AS_OF, "limit": 1},
        headers=_bearer(owner_id),
    )
    cursor = resp.json()["next_cursor"]
    assert cursor is not None
    # Opaque but base64-decodable (no internal structure leaked beyond the encoding).
    base64.urlsafe_b64decode(cursor.encode())


async def test_cursor_malformed_422(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    owner_id, budget_id, _ids_seed = await _seed_personal_with_n_splits(
        initialized_household, bound_account_factories, email="csplit-bad@example.com", n=1
    )
    resp = await async_client.get(
        f"/budgets/{budget_id}/contributing-splits",
        params={"as_of": _AS_OF, "cursor": "not-a-valid-cursor!!!"},
        headers=_bearer(owner_id),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Malformed pagination cursor."


async def test_cursor_from_other_budget_does_not_widen(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # A cursor lifted from budget X, replayed on budget Y, returns only Y's splits
    # (the query is bounded to Y's budget_id + the visibility guard). Gabarit
    # `test_list_cursor_does_not_widen_perimeter`.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID, UUID]:
        owner = user_factory(email="csplit-widen@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat_x = Category(name="X")
        cat_y = Category(name="Y")
        s.add_all([cat_x, cat_y])
        s.flush()
        # Budget X: splits on a late date so its cursor is "high".
        for k in range(1, 4):
            _add_split(
                s,
                account_id=acc.id,
                category_id=cat_x.id,
                amount=100,
                created_by=owner.id,
                split_id=UUID(int=100 + k),
                on=date(2026, 6, 20),
            )
        budget_x = _make_personal_budget(s, owner_id=owner.id, category_id=cat_x.id)
        # Budget Y: distinct category, its own splits on an early date.
        for k in range(1, 3):
            _add_split(
                s,
                account_id=acc.id,
                category_id=cat_y.id,
                amount=100,
                created_by=owner.id,
                split_id=UUID(int=200 + k),
                on=date(2026, 6, 5),
            )
        budget_y = _make_personal_budget(s, owner_id=owner.id, category_id=cat_y.id)
        return owner.id, budget_x, budget_y

    owner_id, budget_x, budget_y = await initialized_household.run_sync(_seed)

    x_page = await async_client.get(
        f"/budgets/{budget_x}/contributing-splits",
        params={"as_of": _AS_OF, "limit": 1},
        headers=_bearer(owner_id),
    )
    x_cursor = x_page.json()["next_cursor"]
    assert x_cursor is not None

    y_page = await async_client.get(
        f"/budgets/{budget_y}/contributing-splits",
        params={"as_of": _AS_OF, "cursor": x_cursor},
        headers=_bearer(owner_id),
    )
    assert y_page.status_code == 200, y_page.text
    returned = set(_ids(y_page.json()))
    # Exact set: the cursor neither widens (no X split) nor shrinks (both Y splits
    # predate X's cursor date, so the keyset keeps them) the perimeter.
    assert returned == {str(UUID(int=201)), str(UUID(int=202))}  # only Y's splits


# ---------------------------------------------------------------------------
# Filters proper to this query
# ---------------------------------------------------------------------------


async def test_filters_exclude_force_full_debt_and_non_confirmed(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="csplit-filters@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        # Counted.
        _add_split(s, account_id=acc.id, category_id=cat.id, amount=1000, created_by=owner.id)
        # Excluded: force_full_debt.
        _add_split(
            s,
            account_id=acc.id,
            category_id=cat.id,
            amount=9000,
            created_by=owner.id,
            override="force_full_debt",
        )
        # Excluded: non-confirmed states.
        for bad in ("draft", "planned", "void"):
            _add_split(
                s,
                account_id=acc.id,
                category_id=cat.id,
                amount=9000,
                created_by=owner.id,
                state=bad,
            )
        return owner.id, _make_personal_budget(s, owner_id=owner.id, category_id=cat.id)

    owner_id, budget_id = await initialized_household.run_sync(_seed)

    resp = await async_client.get(
        f"/budgets/{budget_id}/contributing-splits",
        params={"as_of": _AS_OF},
        headers=_bearer(owner_id),
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["items"]) == 1


async def test_filters_exclude_ineligible_account(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # A personal budget counts only the owner's personal-account splits.
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="csplit-acc@example.com")
        other = user_factory(email="csplit-acc-other@example.com")
        perso = account_factory(owner_id=owner.id, name="Perso")
        common = account_factory(owner_id=None, name="Commun")
        member_factory(account_id=common.id, user_id=owner.id)
        member_factory(account_id=common.id, user_id=other.id)
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        _add_split(s, account_id=perso.id, category_id=cat.id, amount=1000, created_by=owner.id)
        _add_split(s, account_id=common.id, category_id=cat.id, amount=9000, created_by=owner.id)
        return owner.id, _make_personal_budget(s, owner_id=owner.id, category_id=cat.id)

    owner_id, budget_id = await initialized_household.run_sync(_seed)

    resp = await async_client.get(
        f"/budgets/{budget_id}/contributing-splits",
        params={"as_of": _AS_OF},
        headers=_bearer(owner_id),
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["amount_cents"] == 1000


# ---------------------------------------------------------------------------
# RBAC 404 + 401
# ---------------------------------------------------------------------------


async def test_contributing_splits_404_non_contributor(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(s: Session) -> UUID:
        a = user_factory(email="csplit-rbac-a@example.com")
        b = user_factory(email="csplit-rbac-b@example.com")
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
        return budget.id

    budget_id = await initialized_household.run_sync(_seed)
    outsider_id = await _make_outsider(initialized_household, "csplit-outsider@example.com")

    resp = await async_client.get(
        f"/budgets/{budget_id}/contributing-splits", headers=_bearer(outsider_id)
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == _NOT_FOUND_DETAIL


async def test_contributing_splits_404_unknown(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, _a, _m = await bound_account_factories()
    user = await initialized_household.run_sync(
        lambda _s: user_factory(email="csplit-unk@example.com")
    )
    resp = await async_client.get(
        f"/budgets/{uuid4()}/contributing-splits", headers=_bearer(user.id)
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == _NOT_FOUND_DETAIL


async def test_contributing_splits_404_archived(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, _a, _m = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="csplit-arch@example.com")
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
    resp = await async_client.get(
        f"/budgets/{budget_id}/contributing-splits", headers=_bearer(owner_id)
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == _NOT_FOUND_DETAIL


async def test_contributing_splits_401_anonymous(
    async_client: AsyncClient, initialized_household: AsyncSession
) -> None:
    resp = await async_client.get(f"/budgets/{uuid4()}/contributing-splits")
    assert resp.status_code == 401
