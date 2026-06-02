"""Integration tests for `budget.models` (S06.1 `Category`, S08.1 `Budget` /
`BudgetContributor`).

Exercise the persisted behaviour the unit tier and the snapshot cannot
reach: the self-FK accepts a valid parent, rejects a non-existent one,
and the `ON DELETE RESTRICT` refuses deleting a category that still has
children. Also pins the D4/D7 decisions: `color` accepts a non-hex
7-char value (no DB CHECK) and `parent_id`/`color`/`icon` are nullable.

For `Budget`/`BudgetContributor` (S08.1): the CASCADE/RESTRICT matrix
actually fires, the `(budget_id, user_id)` unique rejects a duplicate
contributor, and `period_kind`/`scope` accept arbitrary strings (no DB
CHECK — the closed set lives at the Pydantic boundary, S08.4). The
`archived` case pins the decision that `ix_budgets_category_id` is a
*full* index: an archived budget still blocks the category DELETE.
Pure `flush` + rollback isolation (`auth_schema`).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.models import User
from backend.modules.budget.models import Budget, BudgetContributor, Category


async def test_category_factory_builds_root_and_child(
    auth_schema: AsyncSession,
    bound_category_factory: Callable[..., Awaitable[Category]],
) -> None:
    # Livrable observable (issue #102): the `Category`-factory instantiates a
    # root and a child end to end. Exercises the factory + its session binding
    # (the other tests build `Category(...)` directly), gabarit
    # `test_account_member_factory_builds_shared_account`.
    root = await bound_category_factory(name="Maison")
    child = await bound_category_factory(name="Énergie", parent_id=root.id)
    assert root.parent_id is None
    assert child.parent_id == root.id


async def test_root_and_child_persist(auth_schema: AsyncSession) -> None:
    root = Category(name="Maison")
    auth_schema.add(root)
    await auth_schema.flush()
    child = Category(name="Énergie", parent_id=root.id)
    auth_schema.add(child)
    await auth_schema.flush()

    # Capture ids before `expire_all()`: it expires `root`/`child` too, so
    # re-reading `root.id` afterwards would emit a sync lazy-load IO in an
    # async context (MissingGreenlet) — gabarit `test_accounts_models`.
    root_id = root.id
    child_id = child.id
    auth_schema.expire_all()
    reloaded = (
        await auth_schema.execute(select(Category).where(Category.id == child_id))
    ).scalar_one()
    assert reloaded.parent_id == root_id
    assert reloaded.created_at is not None
    assert reloaded.archived_at is None
    assert reloaded.color is None
    assert reloaded.icon is None


async def test_nonexistent_parent_violates_fk(auth_schema: AsyncSession) -> None:
    orphan = Category(name="Orpheline", parent_id=uuid.uuid4())
    auth_schema.add(orphan)
    with pytest.raises(IntegrityError):
        await auth_schema.flush()


async def test_delete_parent_with_child_is_restricted(
    auth_schema: AsyncSession,
) -> None:
    root = Category(name="Loisirs")
    auth_schema.add(root)
    await auth_schema.flush()
    auth_schema.add(Category(name="Sport", parent_id=root.id))
    await auth_schema.flush()

    await auth_schema.delete(root)
    with pytest.raises(IntegrityError):  # ON DELETE RESTRICT
        await auth_schema.flush()


async def test_color_accepts_non_hex_value(auth_schema: AsyncSession) -> None:
    # D4: no DB CHECK on color — the #RRGGBB format is a Pydantic-boundary
    # concern (S06.3). A 7-char non-hex string must persist here.
    c = Category(name="Brute", color="zzzzzzz")
    auth_schema.add(c)
    await auth_schema.flush()  # no IntegrityError
    assert c.color == "zzzzzzz"


async def test_root_has_null_parent(auth_schema: AsyncSession) -> None:
    root = Category(name="Racine", color="#A1B2C3", icon="home")
    auth_schema.add(root)
    await auth_schema.flush()
    assert root.parent_id is None
    assert root.color == "#A1B2C3"
    assert root.icon == "home"


# ---------------------------------------------------------------------------
# Budget / BudgetContributor (S08.1, P08.1.3)
# ---------------------------------------------------------------------------


async def _make_category(auth_schema: AsyncSession, name: str = "Courses") -> uuid.UUID:
    category = Category(name=name)
    auth_schema.add(category)
    await auth_schema.flush()
    return category.id


async def test_budget_and_contributors_persist(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # Livrable observable: a shared budget with two contributors persists end
    # to end; `created_at`/`archived_at`/`carry_over_remainder` round-trip the
    # server_default (False) without an explicit value.
    u1 = await bound_user_factory()
    u2 = await bound_user_factory()
    category_id = await _make_category(auth_schema)

    budget = Budget(
        category_id=category_id,
        period_kind="monthly",
        period_start=date(2026, 6, 1),
        amount_cents=40000,
        currency="EUR",
        scope="shared",
        created_by=u1.id,
    )
    auth_schema.add(budget)
    await auth_schema.flush()
    budget_id = budget.id
    auth_schema.add_all(
        [
            BudgetContributor(budget_id=budget_id, user_id=u1.id),
            BudgetContributor(budget_id=budget_id, user_id=u2.id),
        ]
    )
    await auth_schema.flush()

    auth_schema.expire_all()
    reloaded = (
        await auth_schema.execute(select(Budget).where(Budget.id == budget_id))
    ).scalar_one()
    assert reloaded.amount_cents == 40000
    assert reloaded.period_start == date(2026, 6, 1)
    assert reloaded.created_at is not None
    assert reloaded.archived_at is None
    assert reloaded.carry_over_remainder is False

    count = (
        await auth_schema.execute(
            text("SELECT count(*) FROM budget_contributors WHERE budget_id = :id"),
            {"id": budget_id},
        )
    ).scalar_one()
    assert count == 2


async def test_delete_budget_cascades_contributors(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # Critère d'acceptation: deleting a budget deletes its contributors
    # (`budget_id` ON DELETE CASCADE).
    user = await bound_user_factory()
    category_id = await _make_category(auth_schema)
    budget = Budget(
        category_id=category_id,
        period_kind="monthly",
        period_start=date(2026, 6, 1),
        amount_cents=10000,
        currency="EUR",
        scope="personal",
        created_by=user.id,
    )
    auth_schema.add(budget)
    await auth_schema.flush()
    budget_id = budget.id
    auth_schema.add(BudgetContributor(budget_id=budget_id, user_id=user.id))
    await auth_schema.flush()

    await auth_schema.delete(budget)
    await auth_schema.flush()

    count = (
        await auth_schema.execute(
            text("SELECT count(*) FROM budget_contributors WHERE budget_id = :id"),
            {"id": budget_id},
        )
    ).scalar_one()
    assert count == 0


async def test_delete_category_referenced_by_budget_is_restricted(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # Critère d'acceptation: deleting a category still referenced by a budget
    # is refused at the DB (`category_id` ON DELETE RESTRICT).
    user = await bound_user_factory()
    category_id = await _make_category(auth_schema)
    budget = Budget(
        category_id=category_id,
        period_kind="monthly",
        period_start=date(2026, 6, 1),
        amount_cents=10000,
        currency="EUR",
        scope="personal",
        created_by=user.id,
    )
    auth_schema.add(budget)
    await auth_schema.flush()

    category = (
        await auth_schema.execute(select(Category).where(Category.id == category_id))
    ).scalar_one()
    await auth_schema.delete(category)
    with pytest.raises(IntegrityError):  # ON DELETE RESTRICT
        await auth_schema.flush()


async def test_delete_category_referenced_by_archived_budget_is_restricted(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # Cas-limite ciblant la justification de l'index *plein*
    # `ix_budgets_category_id` (§1): an archived budget (`archived_at IS NOT
    # NULL`) referencing the category STILL blocks the category DELETE. The
    # RESTRICT FK is insensitive to `archived_at` — so the referential guard
    # (and thus a full, non-partial index) must cover archived budgets too.
    user = await bound_user_factory()
    category_id = await _make_category(auth_schema)
    budget = Budget(
        category_id=category_id,
        period_kind="monthly",
        period_start=date(2026, 6, 1),
        amount_cents=10000,
        currency="EUR",
        scope="personal",
        created_by=user.id,
        archived_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    auth_schema.add(budget)
    await auth_schema.flush()
    assert budget.archived_at is not None

    category = (
        await auth_schema.execute(select(Category).where(Category.id == category_id))
    ).scalar_one()
    await auth_schema.delete(category)
    with pytest.raises(IntegrityError):  # ON DELETE RESTRICT, archived or not
        await auth_schema.flush()


async def test_delete_user_referenced_by_budget_is_restricted(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # `created_by` ON DELETE RESTRICT (F02): a creator user is disabled, never
    # hard-deleted — the DB guard refuses the delete.
    user = await bound_user_factory()
    category_id = await _make_category(auth_schema)
    budget = Budget(
        category_id=category_id,
        period_kind="monthly",
        period_start=date(2026, 6, 1),
        amount_cents=10000,
        currency="EUR",
        scope="personal",
        created_by=user.id,
    )
    auth_schema.add(budget)
    await auth_schema.flush()

    await auth_schema.delete(user)
    with pytest.raises(IntegrityError):
        await auth_schema.flush()


async def test_delete_user_referenced_by_contributor_is_restricted(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # `budget_contributors.user_id` ON DELETE RESTRICT (F02).
    u1 = await bound_user_factory()
    u2 = await bound_user_factory()
    category_id = await _make_category(auth_schema)
    budget = Budget(
        category_id=category_id,
        period_kind="monthly",
        period_start=date(2026, 6, 1),
        amount_cents=10000,
        currency="EUR",
        scope="shared",
        created_by=u1.id,
    )
    auth_schema.add(budget)
    await auth_schema.flush()
    auth_schema.add(BudgetContributor(budget_id=budget.id, user_id=u2.id))
    await auth_schema.flush()

    await auth_schema.delete(u2)
    with pytest.raises(IntegrityError):
        await auth_schema.flush()


async def test_duplicate_contributor_violates_unique(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # `(budget_id, user_id)` unique forbids a duplicate contributor.
    user = await bound_user_factory()
    category_id = await _make_category(auth_schema)
    budget = Budget(
        category_id=category_id,
        period_kind="monthly",
        period_start=date(2026, 6, 1),
        amount_cents=10000,
        currency="EUR",
        scope="personal",
        created_by=user.id,
    )
    auth_schema.add(budget)
    await auth_schema.flush()
    auth_schema.add(BudgetContributor(budget_id=budget.id, user_id=user.id))
    await auth_schema.flush()
    auth_schema.add(BudgetContributor(budget_id=budget.id, user_id=user.id))
    with pytest.raises(IntegrityError):
        await auth_schema.flush()


async def test_distinct_users_same_budget_ok(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # The unique is on the *pair*: two distinct users on the same budget flush
    # cleanly.
    u1 = await bound_user_factory()
    u2 = await bound_user_factory()
    category_id = await _make_category(auth_schema)
    budget = Budget(
        category_id=category_id,
        period_kind="monthly",
        period_start=date(2026, 6, 1),
        amount_cents=10000,
        currency="EUR",
        scope="shared",
        created_by=u1.id,
    )
    auth_schema.add(budget)
    await auth_schema.flush()
    auth_schema.add_all(
        [
            BudgetContributor(budget_id=budget.id, user_id=u1.id),
            BudgetContributor(budget_id=budget.id, user_id=u2.id),
        ]
    )
    await auth_schema.flush()  # no IntegrityError


async def test_period_kind_and_scope_accept_arbitrary_string(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # No DB CHECK on `period_kind`/`scope`: the closed set lives at the
    # Pydantic boundary (S08.4). Arbitrary strings persist here — the
    # behavioural twin of the unit `test_no_check_on_budgets_or_contributors`.
    user = await bound_user_factory()
    category_id = await _make_category(auth_schema)
    budget = Budget(
        category_id=category_id,
        period_kind="weekly",
        period_start=date(2026, 6, 1),
        amount_cents=10000,
        currency="EUR",
        scope="project",
        created_by=user.id,
    )
    auth_schema.add(budget)
    await auth_schema.flush()  # no IntegrityError
    assert budget.period_kind == "weekly"
    assert budget.scope == "project"
