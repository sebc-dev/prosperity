"""Integration tests for `budget.models.Category` (S06.1, P06.1.2).

Exercise the persisted behaviour the unit tier and the snapshot cannot
reach: the self-FK accepts a valid parent, rejects a non-existent one,
and the `ON DELETE RESTRICT` refuses deleting a category that still has
children. Also pins the D4/D7 decisions: `color` accepts a non-hex
7-char value (no DB CHECK) and `parent_id`/`color`/`icon` are nullable.
Pure `flush` + rollback isolation (`auth_schema`).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.budget.models import Category


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
