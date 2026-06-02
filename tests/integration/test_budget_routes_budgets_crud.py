"""Integration tests for the budget CRUD routes (S08.4, P08.4.1).

Drives `POST/GET/PATCH/DELETE /budgets` over httpx against a real Postgres
(`async_client` + savepoint rollback). The contract under test is **watertight**
(D3, gabarit `accounts`/`transactions`, NOT `categories`): a `shared` budget is
confidential, so a non-contributor — admin included — gets a uniform **404**
(never 403, never a differentiating detail). Covers:

- `POST` 201 (personal owner-only / shared ≥2 members), `created_by` from the
  token, `currency` from the household; the contributor invariant (personal ⇒
  owner, shared ⇒ ≥2, member-of-common-account) → 422, nothing persisted;
- the server-derived fields (`id`/`created_by`/`currency`) rejected at the
  schema; an unknown `category_id` → 422 via FK 23503;
- `GET` listing scoped to the caller (personal owned ∪ shared contributor), with
  consumption, ordered `(created_at, id)`;
- the watertight 404 on detail/patch/delete for a non-contributor, with an
  explicit "404, never 403, detail == _NOT_FOUND_DETAIL" assertion;
- `PATCH` editing amount/carry_over and replacing the contributor set (exact-set
  assertion in DB), the security-relevant order (visibility before validation);
- `DELETE` archiving (row preserved, 0 deletion), re-DELETE → 404;
- the cross-invariant pin (D4): a `shared` {A,B} budget validated while the only
  common account is {A,B,C} consumes 0.

The `transactions`/`splits` ORM models are imported **only in the test** (tests
sit outside the import-linter root); the service reads them via Core.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select
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


@pytest.fixture(autouse=True)
def _reset_household_cache() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Cold household cache around every test (process-local, survives rollback)."""
    invalidate_household_cache()
    yield
    invalidate_household_cache()


@pytest_asyncio.fixture(loop_scope="session")
async def initialized_household(auth_schema: AsyncSession) -> AsyncSession:
    """Seed an *initialised* singleton household so `get_household` resolves.

    Like `household_singleton` (same singleton row, needed for the `accounts`
    FK) but with `initialized_at` set — the budget CRUD route derives `currency`
    via `get_household`, which raises until `/setup` has run (S03.2).
    """

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


FactoryBundle = Callable[[], Awaitable[tuple[type, type, type]]]

_PERIOD_START = "2026-06-01"
_AS_OF = "2026-06-15"
_IN_WINDOW = date(2026, 6, 10)
_NOT_FOUND_DETAIL = "Budget not found."


def _bearer(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


def _payload(*, category_id: UUID, contributor_ids: list[UUID], **over: object) -> dict:
    payload: dict = {
        "category_id": str(category_id),
        "period_kind": "monthly",
        "period_start": _PERIOD_START,
        "amount_cents": 40000,
        "scope": "personal",
        "contributor_ids": [str(c) for c in contributor_ids],
    }
    payload.update(over)
    return payload


async def _budget_count(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(Budget))).scalar_one()


async def _contributor_ids(session: AsyncSession, budget_id: UUID) -> set[UUID]:
    rows = (
        await session.execute(
            select(BudgetContributor.user_id).where(BudgetContributor.budget_id == budget_id)
        )
    ).scalars()
    return set(rows.all())


async def _make_outsider(session: AsyncSession, email: str) -> UUID:
    """Create a user who is not bound to any budget (a non-contributor)."""

    def _make(s: Session) -> UUID:
        UserFactory._meta.sqlalchemy_session = s  # type: ignore[attr-defined]
        return UserFactory(email=email).id

    return await session.run_sync(_make)


def _add_expense(
    s: Session, *, account_id: UUID, category_id: UUID, amount: int, created_by: UUID
) -> None:
    """Persist a canonical expense (account leg + category leg) in the window."""
    tx = Transaction(
        account_id=account_id,
        date=_IN_WINDOW,
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


# ---------------------------------------------------------------------------
# POST /budgets
# ---------------------------------------------------------------------------


async def test_post_201_personal(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, _account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="post-perso@example.com")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        return owner.id, cat.id

    owner_id, cat_id = await initialized_household.run_sync(_seed)

    resp = await async_client.post(
        "/budgets",
        json=_payload(category_id=cat_id, contributor_ids=[owner_id]),
        headers=_bearer(owner_id),
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["created_by"] == str(owner_id)  # from the token, never the body
    assert body["currency"] == "EUR"  # from the household
    assert body["scope"] == "personal"
    assert body["contributor_ids"] == [str(owner_id)]
    assert UUID(body["id"])


async def test_post_201_shared(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # shared with Alice+Bob, both members of a common account.
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID, UUID]:
        alice = user_factory(email="sh-alice@example.com")
        bob = user_factory(email="sh-bob@example.com")
        common = account_factory(owner_id=None, name="Commun")
        member_factory(account_id=common.id, user_id=alice.id)
        member_factory(account_id=common.id, user_id=bob.id)
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        return alice.id, bob.id, cat.id

    alice_id, bob_id, cat_id = await initialized_household.run_sync(_seed)

    resp = await async_client.post(
        "/budgets",
        json=_payload(category_id=cat_id, contributor_ids=[alice_id, bob_id], scope="shared"),
        headers=_bearer(alice_id),
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["scope"] == "shared"
    assert set(body["contributor_ids"]) == {str(alice_id), str(bob_id)}


async def test_post_401_anonymous(
    async_client: AsyncClient, initialized_household: AsyncSession
) -> None:
    resp = await async_client.post(
        "/budgets", json=_payload(category_id=uuid4(), contributor_ids=[uuid4()])
    )
    assert resp.status_code == 401


async def test_post_422_server_derived_fields(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, _a, _m = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="post-srv@example.com")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        return owner.id, cat.id

    owner_id, cat_id = await initialized_household.run_sync(_seed)

    for field, value in (
        ("id", str(uuid4())),
        ("created_by", str(uuid4())),
        ("currency", "USD"),
    ):
        resp = await async_client.post(
            "/budgets",
            json=_payload(category_id=cat_id, contributor_ids=[owner_id], **{field: value}),
            headers=_bearer(owner_id),
        )
        assert resp.status_code == 422, f"{field}: {resp.text}"
    assert await _budget_count(initialized_household) == 0


async def test_post_422_bad_amount_and_enums(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, _a, _m = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="post-enum@example.com")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        return owner.id, cat.id

    owner_id, cat_id = await initialized_household.run_sync(_seed)

    for over in ({"amount_cents": 0}, {"period_kind": "weekly"}, {"scope": "team"}):
        resp = await async_client.post(
            "/budgets",
            json=_payload(category_id=cat_id, contributor_ids=[owner_id], **over),
            headers=_bearer(owner_id),
        )
        assert resp.status_code == 422, f"{over}: {resp.text}"
    assert await _budget_count(initialized_household) == 0


async def test_post_422_personal_wrong_contributors(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # personal with 2 contributors, and personal with a non-owner contributor.
    user_factory, _a, _m = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID, UUID]:
        owner = user_factory(email="post-p2@example.com")
        other = user_factory(email="post-p2-other@example.com")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        return owner.id, other.id, cat.id

    owner_id, other_id, cat_id = await initialized_household.run_sync(_seed)

    two = await async_client.post(
        "/budgets",
        json=_payload(category_id=cat_id, contributor_ids=[owner_id, other_id]),
        headers=_bearer(owner_id),
    )
    assert two.status_code == 422, two.text

    wrong = await async_client.post(
        "/budgets",
        json=_payload(category_id=cat_id, contributor_ids=[other_id]),
        headers=_bearer(owner_id),
    )
    assert wrong.status_code == 422, wrong.text
    assert await _budget_count(initialized_household) == 0


async def test_post_422_shared_one_contributor(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, _a, _m = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="post-sh1@example.com")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        return owner.id, cat.id

    owner_id, cat_id = await initialized_household.run_sync(_seed)

    resp = await async_client.post(
        "/budgets",
        json=_payload(category_id=cat_id, contributor_ids=[owner_id], scope="shared"),
        headers=_bearer(owner_id),
    )
    assert resp.status_code == 422, resp.text
    assert await _budget_count(initialized_household) == 0


async def test_post_422_shared_contributor_not_common_member(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # shared {A,B} but B is not a member of any common account → 422.
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID, UUID]:
        a = user_factory(email="post-shx-a@example.com")
        b = user_factory(email="post-shx-b@example.com")
        # A common account with only A (B is not a member of any common account).
        common = account_factory(owner_id=None, name="Commun")
        member_factory(account_id=common.id, user_id=a.id)
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        return a.id, b.id, cat.id

    a_id, b_id, cat_id = await initialized_household.run_sync(_seed)

    resp = await async_client.post(
        "/budgets",
        json=_payload(category_id=cat_id, contributor_ids=[a_id, b_id], scope="shared"),
        headers=_bearer(a_id),
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "Invalid budget contributors."
    assert await _budget_count(initialized_household) == 0


async def test_post_422_unknown_category(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # Unknown category_id → FK 23503 at flush → curated 422, nothing persisted.
    user_factory, _a, _m = await bound_account_factories()
    owner = await initialized_household.run_sync(
        lambda _s: user_factory(email="post-nocat@example.com")
    )

    resp = await async_client.post(
        "/budgets",
        json=_payload(category_id=uuid4(), contributor_ids=[owner.id]),
        headers=_bearer(owner.id),
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "The category does not exist."
    assert await _budget_count(initialized_household) == 0


# ---------------------------------------------------------------------------
# GET /budgets (listing)
# ---------------------------------------------------------------------------


async def test_get_list_scoped_to_user_with_consumption(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID, UUID]:
        owner = user_factory(email="list-owner@example.com")
        other = user_factory(email="list-other@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        other_acc = account_factory(owner_id=other.id, name="Other perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        _add_expense(s, account_id=acc.id, category_id=cat.id, amount=5000, created_by=owner.id)
        # owner's budget
        b_owner = Budget(
            category_id=cat.id,
            period_kind="monthly",
            period_start=date(2026, 6, 1),
            amount_cents=40000,
            currency="EUR",
            scope="personal",
            created_by=owner.id,
        )
        s.add(b_owner)
        s.flush()
        s.add(BudgetContributor(budget_id=b_owner.id, user_id=owner.id))
        # other user's budget (must NOT appear for owner)
        b_other = Budget(
            category_id=cat.id,
            period_kind="monthly",
            period_start=date(2026, 6, 1),
            amount_cents=10000,
            currency="EUR",
            scope="personal",
            created_by=other.id,
        )
        s.add(b_other)
        s.flush()
        s.add(BudgetContributor(budget_id=b_other.id, user_id=other.id))
        # owner's archived budget (excluded)
        b_arch = Budget(
            category_id=cat.id,
            period_kind="monthly",
            period_start=date(2026, 6, 1),
            amount_cents=10000,
            currency="EUR",
            scope="personal",
            created_by=owner.id,
            archived_at=datetime.now(UTC),
        )
        s.add(b_arch)
        s.flush()
        s.add(BudgetContributor(budget_id=b_arch.id, user_id=owner.id))
        return owner.id, b_owner.id, other_acc.id

    owner_id, b_owner_id, _other_acc = await initialized_household.run_sync(_seed)

    resp = await async_client.get("/budgets", params={"as_of": _AS_OF}, headers=_bearer(owner_id))

    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["budget"]["id"] == str(b_owner_id)
    assert item["consumption"]["consumed_cents"] == 5000
    assert item["consumption"]["remaining_cents"] == 35000


async def test_get_list_ordered_created_at_then_id(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # Two budgets in the same transaction share created_at → (created_at, id) order.
    user_factory, _a, _m = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID, UUID]:
        owner = user_factory(email="list-order@example.com")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        lo = Budget(
            id=UUID(int=1),
            category_id=cat.id,
            period_kind="monthly",
            period_start=date(2026, 6, 1),
            amount_cents=1,
            currency="EUR",
            scope="personal",
            created_by=owner.id,
        )
        hi = Budget(
            id=UUID(int=2),
            category_id=cat.id,
            period_kind="monthly",
            period_start=date(2026, 6, 1),
            amount_cents=1,
            currency="EUR",
            scope="personal",
            created_by=owner.id,
        )
        s.add_all([hi, lo])
        s.flush()
        s.add_all(
            [
                BudgetContributor(budget_id=lo.id, user_id=owner.id),
                BudgetContributor(budget_id=hi.id, user_id=owner.id),
            ]
        )
        s.flush()
        return owner.id, lo.id, hi.id

    owner_id, lo_id, hi_id = await initialized_household.run_sync(_seed)

    resp = await async_client.get("/budgets", params={"as_of": _AS_OF}, headers=_bearer(owner_id))

    assert resp.status_code == 200, resp.text
    ids = [it["budget"]["id"] for it in resp.json()["items"]]
    assert ids == [str(lo_id), str(hi_id)]


async def test_get_list_empty_for_user_without_budgets(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # A user who contributes to no budget gets an empty list (no N+1 query fires
    # on an empty page — the batched contributor load short-circuits).
    user_factory, _a, _m = await bound_account_factories()
    user = await initialized_household.run_sync(
        lambda _s: user_factory(email="list-empty@example.com")
    )

    resp = await async_client.get("/budgets", params={"as_of": _AS_OF}, headers=_bearer(user.id))

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"items": []}


async def test_get_list_401_anonymous(
    async_client: AsyncClient, initialized_household: AsyncSession
) -> None:
    resp = await async_client.get("/budgets")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /budgets/{id}  (watertight 404)
# ---------------------------------------------------------------------------


async def _seed_shared_budget(
    session: AsyncSession, factories: FactoryBundle
) -> tuple[UUID, UUID, UUID]:
    """Seed a shared budget {A,B} + a non-contributor C. Returns (a, b, budget)."""
    user_factory, account_factory, member_factory = await factories()

    def _seed(s: Session) -> tuple[UUID, UUID, UUID]:
        a = user_factory(email=f"vis-a-{uuid4().hex[:6]}@example.com")
        b = user_factory(email=f"vis-b-{uuid4().hex[:6]}@example.com")
        common = account_factory(owner_id=None, name="Commun")
        member_factory(account_id=common.id, user_id=a.id)
        member_factory(account_id=common.id, user_id=b.id)
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        budget = Budget(
            category_id=cat.id,
            period_kind="monthly",
            period_start=date(2026, 6, 1),
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
        return a.id, b.id, budget.id

    return await session.run_sync(_seed)


async def test_get_detail_visible_200(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    a_id, _b_id, budget_id = await _seed_shared_budget(
        initialized_household, bound_account_factories
    )

    resp = await async_client.get(f"/budgets/{budget_id}", headers=_bearer(a_id))

    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == str(budget_id)


async def test_get_detail_non_contributor_404_never_403(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # A shared budget is confidential: a non-contributor must not learn it exists.
    _a_id, _b_id, budget_id = await _seed_shared_budget(
        initialized_household, bound_account_factories
    )
    outsider_id = await _make_outsider(initialized_household, "vis-outsider@example.com")

    resp = await async_client.get(f"/budgets/{budget_id}", headers=_bearer(outsider_id))

    assert resp.status_code == 404
    assert resp.json()["detail"] == _NOT_FOUND_DETAIL  # never 403, never differentiating


async def test_get_detail_unknown_404(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, _a, _m = await bound_account_factories()
    user = await initialized_household.run_sync(lambda _s: user_factory(email="unk@example.com"))

    resp = await async_client.get(f"/budgets/{uuid4()}", headers=_bearer(user.id))

    assert resp.status_code == 404
    assert resp.json()["detail"] == _NOT_FOUND_DETAIL


async def test_get_detail_archived_404(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, _a, _m = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="arch-detail@example.com")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        budget = Budget(
            category_id=cat.id,
            period_kind="monthly",
            period_start=date(2026, 6, 1),
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

    resp = await async_client.get(f"/budgets/{budget_id}", headers=_bearer(owner_id))

    assert resp.status_code == 404
    assert resp.json()["detail"] == _NOT_FOUND_DETAIL


# ---------------------------------------------------------------------------
# PATCH /budgets/{id}
# ---------------------------------------------------------------------------


async def test_patch_edits_amount_and_carry_over(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, _a, _m = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="patch-amt@example.com")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        budget = Budget(
            category_id=cat.id,
            period_kind="monthly",
            period_start=date(2026, 6, 1),
            amount_cents=40000,
            currency="EUR",
            scope="personal",
            created_by=owner.id,
        )
        s.add(budget)
        s.flush()
        s.add(BudgetContributor(budget_id=budget.id, user_id=owner.id))
        s.flush()
        return owner.id, budget.id

    owner_id, budget_id = await initialized_household.run_sync(_seed)

    resp = await async_client.patch(
        f"/budgets/{budget_id}",
        json={"amount_cents": 55000, "carry_over_remainder": True},
        headers=_bearer(owner_id),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["amount_cents"] == 55000
    assert body["carry_over_remainder"] is True


async def test_patch_replaces_contributor_set(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # shared {A,B} → replace with {A,C}: B is removed, C added, no stray remains.
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID, UUID, UUID]:
        a = user_factory(email="patch-c-a@example.com")
        b = user_factory(email="patch-c-b@example.com")
        c = user_factory(email="patch-c-c@example.com")
        common = account_factory(owner_id=None, name="Commun")
        for u in (a, b, c):
            member_factory(account_id=common.id, user_id=u.id)
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        budget = Budget(
            category_id=cat.id,
            period_kind="monthly",
            period_start=date(2026, 6, 1),
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
        return a.id, b.id, c.id, budget.id

    a_id, b_id, c_id, budget_id = await initialized_household.run_sync(_seed)

    resp = await async_client.patch(
        f"/budgets/{budget_id}",
        json={"contributor_ids": [str(a_id), str(c_id)]},
        headers=_bearer(a_id),
    )

    assert resp.status_code == 200, resp.text
    assert set(resp.json()["contributor_ids"]) == {str(a_id), str(c_id)}
    # Exact set in DB: B is gone, no stray contributor survives.
    assert await _contributor_ids(initialized_household, budget_id) == {a_id, c_id}


async def test_patch_422_frozen_scope(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, _a, _m = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="patch-scope@example.com")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        budget = Budget(
            category_id=cat.id,
            period_kind="monthly",
            period_start=date(2026, 6, 1),
            amount_cents=40000,
            currency="EUR",
            scope="personal",
            created_by=owner.id,
        )
        s.add(budget)
        s.flush()
        s.add(BudgetContributor(budget_id=budget.id, user_id=owner.id))
        s.flush()
        return owner.id, budget.id

    owner_id, budget_id = await initialized_household.run_sync(_seed)

    resp = await async_client.patch(
        f"/budgets/{budget_id}", json={"scope": "shared"}, headers=_bearer(owner_id)
    )
    assert resp.status_code == 422


async def test_patch_422_shared_reduced_below_two(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    a_id, _b_id, budget_id = await _seed_shared_budget(
        initialized_household, bound_account_factories
    )

    resp = await async_client.patch(
        f"/budgets/{budget_id}",
        json={"contributor_ids": [str(a_id)]},
        headers=_bearer(a_id),
    )
    assert resp.status_code == 422


async def test_patch_non_contributor_404(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    _a_id, _b_id, budget_id = await _seed_shared_budget(
        initialized_household, bound_account_factories
    )
    outsider_id = await _make_outsider(initialized_household, "patch-outsider@example.com")

    resp = await async_client.patch(
        f"/budgets/{budget_id}", json={"amount_cents": 99}, headers=_bearer(outsider_id)
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == _NOT_FOUND_DETAIL


async def test_patch_non_contributor_with_invalid_body_still_404(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # Security-relevant order pin (D3): a non-contributor sends a body that is
    # ALSO invalid (shared reduced to 1 contributor). Visibility precedes
    # validation → 404, never 422 (which would reveal the budget exists).
    a_id, _b_id, budget_id = await _seed_shared_budget(
        initialized_household, bound_account_factories
    )
    outsider_id = await _make_outsider(initialized_household, "patch-order@example.com")

    resp = await async_client.patch(
        f"/budgets/{budget_id}",
        json={"contributor_ids": [str(a_id)]},  # would be a 422 if visible
        headers=_bearer(outsider_id),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == _NOT_FOUND_DETAIL


# ---------------------------------------------------------------------------
# DELETE /budgets/{id}  (archive)
# ---------------------------------------------------------------------------


async def test_delete_archives_preserves_rows(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, _a, _m = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="del@example.com")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        budget = Budget(
            category_id=cat.id,
            period_kind="monthly",
            period_start=date(2026, 6, 1),
            amount_cents=40000,
            currency="EUR",
            scope="personal",
            created_by=owner.id,
        )
        s.add(budget)
        s.flush()
        s.add(BudgetContributor(budget_id=budget.id, user_id=owner.id))
        s.flush()
        return owner.id, budget.id

    owner_id, budget_id = await initialized_household.run_sync(_seed)

    resp = await async_client.delete(f"/budgets/{budget_id}", headers=_bearer(owner_id))
    assert resp.status_code == 204, resp.text

    # Row preserved with archived_at set; contributor preserved; 0 deletion.
    budget = await initialized_household.get(Budget, budget_id)
    assert budget is not None
    assert budget.archived_at is not None
    assert await _contributor_ids(initialized_household, budget_id) == {owner_id}

    # Re-DELETE of an already-archived budget → 404.
    again = await async_client.delete(f"/budgets/{budget_id}", headers=_bearer(owner_id))
    assert again.status_code == 404


async def test_delete_non_contributor_404(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    _a_id, _b_id, budget_id = await _seed_shared_budget(
        initialized_household, bound_account_factories
    )
    outsider_id = await _make_outsider(initialized_household, "del-outsider@example.com")

    resp = await async_client.delete(f"/budgets/{budget_id}", headers=_bearer(outsider_id))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Cross-invariant pin (D4): validation (member-of-any) vs consumption (subset)
# ---------------------------------------------------------------------------


async def test_shared_budget_without_subset_account_consumes_zero(
    async_client: AsyncClient,
    initialized_household: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # A shared {A,B} budget is valid (both members of a common account) even when
    # the ONLY common account is {A,B,C}. The consumption filter uses
    # subset-of-members, so {A,B} ⊄ {A,B,C} → no eligible account → 0. Pins the
    # intentional divergence (D4) so a future predicate change cannot silently
    # break the validation⟺consumption coherence.
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID, UUID]:
        a = user_factory(email="d4-a@example.com")
        b = user_factory(email="d4-b@example.com")
        c = user_factory(email="d4-c@example.com")
        abc = account_factory(owner_id=None, name="ABC")
        member_factory(account_id=abc.id, user_id=a.id, default_share_ratio="0.3333")
        member_factory(account_id=abc.id, user_id=b.id, default_share_ratio="0.3333")
        member_factory(account_id=abc.id, user_id=c.id, default_share_ratio="0.3334")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        _add_expense(s, account_id=abc.id, category_id=cat.id, amount=9000, created_by=a.id)
        return a.id, b.id, cat.id

    a_id, b_id, cat_id = await initialized_household.run_sync(_seed)

    created = await async_client.post(
        "/budgets",
        json=_payload(category_id=cat_id, contributor_ids=[a_id, b_id], scope="shared"),
        headers=_bearer(a_id),
    )
    assert created.status_code == 201, created.text  # validation passes (member-of-any)
    budget_id = created.json()["id"]

    listed = await async_client.get("/budgets", params={"as_of": _AS_OF}, headers=_bearer(a_id))
    item = next(it for it in listed.json()["items"] if it["budget"]["id"] == budget_id)
    assert item["consumption"]["splits_count"] == 0  # subset filter → 0
    assert item["consumption"]["consumed_cents"] == 0
