"""Integration tests for `budget.service.categories` (S06.2, P06.2.2).

Drives `create_category` / `move_category` against a real Postgres so the
DB-level behaviour fires: the `Category` INSERTs/UPDATEs, the recursive-CTE
ancestor walk (`_load_ancestor_chain`), the self-FK `RESTRICT` on a missing
parent, and — on `committed_engine` — the no-commit contract (flush-only,
ADR 0015) plus the "no cycle is ever persisted" guarantee verified from an
independent session.

Two tiers (gabarit `test_accounts_service.py`):

* Rollback-isolated (`auth_schema` / `bound_category_factory`): persistence,
  accepted/rejected moves, and the FK behaviour. `Category` has no FK to
  `household`/`users`, so a direct seed suffices (no `household_singleton`).
* Real-commit (`committed_engine` / `_clean_committed_db`): no-commit,
  rollback-discards, and the strong "cycle rejected persists nothing" proof,
  checked from a fresh session.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.modules.budget.domain import (
    CategoryCycleError,
    CategoryInUseError,
    CategoryNotFoundError,
)
from backend.modules.budget.models import Category
from backend.modules.budget.service.categories import (
    _load_ancestor_chain,  # pyright: ignore[reportPrivateUsage]
    archive_category,
    create_category,
    delete_category,
    move_category,
)


async def _count(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(Category))).scalar_one()


async def _parent_id_of(sm: async_sessionmaker[AsyncSession], category_id: UUID) -> UUID | None:
    """Re-read `parent_id` from a fresh committed session (independent read)."""
    async with sm() as session:
        return (
            await session.execute(select(Category.parent_id).where(Category.id == category_id))
        ).scalar_one()


# ---------------------------------------------------------------------------
# Rollback-isolated tier — create
# ---------------------------------------------------------------------------


async def test_create_root_persists(auth_schema: AsyncSession) -> None:
    category = await create_category(auth_schema, name="Logement", parent_id=None)

    assert category.id is not None  # PK assigned at flush
    assert category.parent_id is None
    assert await _count(auth_schema) == 1


async def test_create_child_persists(auth_schema: AsyncSession) -> None:
    root = await create_category(auth_schema, name="Root", parent_id=None)

    child = await create_category(auth_schema, name="Sub", parent_id=root.id)

    assert child.parent_id == root.id


async def test_create_under_parent_accepted(auth_schema: AsyncSession) -> None:
    # Pins D6: creating a node with a parent passes the detector (vacuously,
    # since a fresh id has no descendants) rather than spuriously raising.
    root = await create_category(auth_schema, name="Parent", parent_id=None)

    child = await create_category(auth_schema, name="Child", parent_id=root.id)

    assert child.parent_id == root.id


async def test_create_with_unknown_parent_raises_integrity_error(
    auth_schema: AsyncSession,
) -> None:
    # Detector sees an empty ancestor chain → OK; the FK RESTRICT fires at
    # flush. Clean 404/422 mapping is S06.3 (D6); here we pin the raw FK guard.
    # A SAVEPOINT contains the IntegrityError so it rolls back only the inner
    # work, leaving the outer test transaction healthy for teardown (gabarit
    # `test_auth_users_service` begin_nested).
    savepoint = await auth_schema.begin_nested()
    with pytest.raises(IntegrityError):
        await create_category(auth_schema, name="Orphan", parent_id=uuid4())
    await savepoint.rollback()


# ---------------------------------------------------------------------------
# Rollback-isolated tier — move (accepted)
# ---------------------------------------------------------------------------


async def test_move_to_new_parent_accepted(auth_schema: AsyncSession) -> None:
    # A→B→C; move C under A (A is not a descendant of C) → accepted.
    a = await create_category(auth_schema, name="A", parent_id=None)
    b = await create_category(auth_schema, name="B", parent_id=a.id)
    c = await create_category(auth_schema, name="C", parent_id=b.id)

    # move_category returns (category, previous_parent_id) since S06.3 (P06.3.3).
    moved, previous = await move_category(auth_schema, category_id=c.id, new_parent_id=a.id)

    assert moved.parent_id == a.id
    assert previous == b.id


async def test_move_to_root_accepted(auth_schema: AsyncSession) -> None:
    a = await create_category(auth_schema, name="A", parent_id=None)
    child = await create_category(auth_schema, name="Child", parent_id=a.id)

    moved, previous = await move_category(auth_schema, category_id=child.id, new_parent_id=None)

    assert moved.parent_id is None
    assert previous == a.id


# ---------------------------------------------------------------------------
# Rollback-isolated tier — move (rejected)
# ---------------------------------------------------------------------------


async def test_move_self_reference_rejected(auth_schema: AsyncSession) -> None:
    a = await create_category(auth_schema, name="A", parent_id=None)

    with pytest.raises(CategoryCycleError):
        await move_category(auth_schema, category_id=a.id, new_parent_id=a.id)


async def test_move_direct_cycle_rejected(auth_schema: AsyncSession) -> None:
    # ⚠️ Delta corrigé + livrable observable: A→B (B child of A); moving A
    # under B would close A→B→A → CategoryCycleError.
    a = await create_category(auth_schema, name="A", parent_id=None)
    b = await create_category(auth_schema, name="B", parent_id=a.id)

    with pytest.raises(CategoryCycleError):
        await move_category(auth_schema, category_id=a.id, new_parent_id=b.id)


async def test_move_transitive_cycle_rejected(auth_schema: AsyncSession) -> None:
    # A→B→C; move A under C: the CTE walks C→B→A (≥ 3 levels) → cycle.
    a = await create_category(auth_schema, name="A", parent_id=None)
    b = await create_category(auth_schema, name="B", parent_id=a.id)
    c = await create_category(auth_schema, name="C", parent_id=b.id)

    with pytest.raises(CategoryCycleError):
        await move_category(auth_schema, category_id=a.id, new_parent_id=c.id)


async def test_cycle_rejected_before_any_write(auth_schema: AsyncSession) -> None:
    # Order guard (Tests-F6): after the raise, A's parent_id is unchanged. At
    # this mono-session tier this proves the detector raises BEFORE the
    # attribute assignment (code order), not a committed-DB absence — the
    # strong proof is `test_cycle_rejected_persists_nothing` (committed tier).
    a = await create_category(auth_schema, name="A", parent_id=None)
    b = await create_category(auth_schema, name="B", parent_id=a.id)
    a_id, b_id = a.id, b.id  # capture before expire_all (avoid async lazy-load)

    with pytest.raises(CategoryCycleError):
        await move_category(auth_schema, category_id=a_id, new_parent_id=b_id)

    auth_schema.expire_all()
    reloaded = (
        await auth_schema.execute(select(Category.parent_id).where(Category.id == a_id))
    ).scalar_one()
    assert reloaded is None


async def test_move_unknown_category_raises_not_found(auth_schema: AsyncSession) -> None:
    with pytest.raises(CategoryNotFoundError):
        await move_category(auth_schema, category_id=uuid4(), new_parent_id=None)


async def test_move_to_unknown_parent_raises_integrity_error(
    auth_schema: AsyncSession,
) -> None:
    # Symmetric of the create FK case: detector OK (empty chain) → flush →
    # IntegrityError on the self-FK RESTRICT. Covers the move's FK branch.
    a = await create_category(auth_schema, name="A", parent_id=None)

    savepoint = await auth_schema.begin_nested()
    with pytest.raises(IntegrityError):
        await move_category(auth_schema, category_id=a.id, new_parent_id=uuid4())
    await savepoint.rollback()


async def test_load_ancestor_chain_terminates_on_corrupted_tree(
    auth_schema: AsyncSession,
) -> None:
    # Validate the UNION/corruption claim (Tests-F3): seed A→B, then FORCE a
    # cycle B→A via raw SQL (UPDATE bypasses RESTRICT, which only guards
    # DELETE). _load_ancestor_chain must terminate and return both rows.
    a = await create_category(auth_schema, name="A", parent_id=None)
    b = await create_category(auth_schema, name="B", parent_id=a.id)
    # a.parent_id := b → closes the cycle A→B→A in storage.
    await auth_schema.execute(
        text("UPDATE categories SET parent_id = :b WHERE id = :a").bindparams(b=b.id, a=a.id)
    )
    await auth_schema.flush()

    chain = await _load_ancestor_chain(auth_schema, b.id)

    assert set(chain) == {a.id, b.id}


# ---------------------------------------------------------------------------
# Rollback-isolated tier — archive (soft-delete, S06.3 P06.3.1)
# ---------------------------------------------------------------------------


async def test_archive_sets_archived_at(auth_schema: AsyncSession) -> None:
    category = await create_category(auth_schema, name="Logement", parent_id=None)
    category_id = category.id  # capture before expire_all (avoid async lazy-load)

    assert await archive_category(auth_schema, category_id=category_id) is True
    auth_schema.expire_all()
    archived_at = (
        await auth_schema.execute(select(Category.archived_at).where(Category.id == category_id))
    ).scalar_one()
    assert archived_at is not None


async def test_archive_does_not_touch_children(auth_schema: AsyncSession) -> None:
    # Critère #6: archiving a parent leaves its children active (no cascade).
    parent = await create_category(auth_schema, name="Parent", parent_id=None)
    child = await create_category(auth_schema, name="Child", parent_id=parent.id)
    parent_id, child_id = parent.id, child.id  # capture before expire_all

    assert await archive_category(auth_schema, category_id=parent_id) is True
    auth_schema.expire_all()

    child_archived_at = (
        await auth_schema.execute(select(Category.archived_at).where(Category.id == child_id))
    ).scalar_one()
    assert child_archived_at is None


async def test_archive_already_archived_returns_false(auth_schema: AsyncSession) -> None:
    category = await create_category(auth_schema, name="Logement", parent_id=None)
    assert await archive_category(auth_schema, category_id=category.id) is True

    # Re-archive → False (→ 404), idempotent in the "no corruption" sense.
    assert await archive_category(auth_schema, category_id=category.id) is False


async def test_archive_unknown_returns_false(auth_schema: AsyncSession) -> None:
    assert await archive_category(auth_schema, category_id=uuid4()) is False


# ---------------------------------------------------------------------------
# Rollback-isolated tier — delete (hard, not routed, S06.3 P06.3.1)
# ---------------------------------------------------------------------------


async def test_delete_leaf_ok(auth_schema: AsyncSession) -> None:
    category = await create_category(auth_schema, name="Leaf", parent_id=None)

    assert await delete_category(auth_schema, category_id=category.id) is True
    assert await _count(auth_schema) == 0


async def test_delete_with_active_subcategory_raises_in_use(auth_schema: AsyncSession) -> None:
    parent = await create_category(auth_schema, name="Parent", parent_id=None)
    await create_category(auth_schema, name="Child", parent_id=parent.id)

    with pytest.raises(CategoryInUseError):
        await delete_category(auth_schema, category_id=parent.id)
    # Nothing deleted: both rows survive.
    assert await _count(auth_schema) == 2


async def test_delete_archived_only_children_raises_in_use(auth_schema: AsyncSession) -> None:
    # D8 residue: the service count sees 0 *active* children (the only child
    # is archived), so it proceeds to delete — but the self-FK RESTRICT trips
    # on the archived child (23503), which the service re-maps to
    # CategoryInUseError. The IntegrityError is caught *inside* the service,
    # but we still wrap the call in a SAVEPOINT (gabarit `:89`) so the failed
    # flush rolls back only the inner work, keeping the test transaction
    # healthy for teardown.
    parent = await create_category(auth_schema, name="Parent", parent_id=None)
    child = await create_category(auth_schema, name="Child", parent_id=parent.id)
    assert await archive_category(auth_schema, category_id=child.id) is True

    savepoint = await auth_schema.begin_nested()
    with pytest.raises(CategoryInUseError):
        await delete_category(auth_schema, category_id=parent.id)
    await savepoint.rollback()


async def test_delete_unknown_returns_false(auth_schema: AsyncSession) -> None:
    assert await delete_category(auth_schema, category_id=uuid4()) is False


# ---------------------------------------------------------------------------
# Real-commit tier (independent sessions on committed_engine)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_clean_committed_db")
async def test_create_does_not_commit(committed_engine: AsyncEngine) -> None:
    # Flush-only (ADR 0015): closing the session without commit rolls back,
    # so an independent session sees no row.
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    async with sm() as session:
        category = await create_category(session, name="Perso", parent_id=None)
        assert category.id is not None
        # Deliberately no commit — closing the session rolls back.

    async with sm() as session:
        assert await _count(session) == 0


@pytest.mark.usefixtures("_clean_committed_db")
async def test_create_rollback_discards(committed_engine: AsyncEngine) -> None:
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    async with sm() as session:
        await create_category(session, name="Rollback", parent_id=None)
        await session.rollback()

    async with sm() as session:
        assert await _count(session) == 0


@pytest.mark.usefixtures("_clean_committed_db")
async def test_move_does_not_commit(committed_engine: AsyncEngine) -> None:
    # Seed A→B committed; move B to root WITHOUT commit; an independent
    # session must still see B under A (the service did not commit).
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    async with sm() as session:
        a = Category(name="A", parent_id=None)
        session.add(a)
        await session.flush()
        b = Category(name="B", parent_id=a.id)
        session.add(b)
        await session.commit()
        a_id, b_id = a.id, b.id

    async with sm() as session:
        await move_category(session, category_id=b_id, new_parent_id=None)
        # no commit

    assert await _parent_id_of(sm, b_id) == a_id


@pytest.mark.usefixtures("_clean_committed_db")
async def test_move_rollback_discards(committed_engine: AsyncEngine) -> None:
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    async with sm() as session:
        a = Category(name="A", parent_id=None)
        session.add(a)
        await session.flush()
        b = Category(name="B", parent_id=a.id)
        session.add(b)
        await session.commit()
        a_id, b_id = a.id, b.id

    async with sm() as session:
        await move_category(session, category_id=b_id, new_parent_id=None)
        await session.rollback()

    assert await _parent_id_of(sm, b_id) == a_id


@pytest.mark.usefixtures("_clean_committed_db")
async def test_cycle_rejected_persists_nothing(committed_engine: AsyncEngine) -> None:
    # Strong "no cycle persisted" proof (Tests-F6): seed A→B committed; a new
    # session's move(A, parent=B) raises; an independent session re-reads
    # A.parent_id ⇒ still None (unchanged). Closes the gap the mono-session
    # order-guard test leaves open.
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    async with sm() as session:
        a = Category(name="A", parent_id=None)
        session.add(a)
        await session.flush()
        b = Category(name="B", parent_id=a.id)
        session.add(b)
        await session.commit()
        a_id, b_id = a.id, b.id

    async with sm() as session:
        with pytest.raises(CategoryCycleError):
            await move_category(session, category_id=a_id, new_parent_id=b_id)

    assert await _parent_id_of(sm, a_id) is None


@pytest.mark.usefixtures("_clean_committed_db")
async def test_archive_flush_only_no_commit(committed_engine: AsyncEngine) -> None:
    # Flush-only (ADR 0015): archive without commit; an independent session
    # opened after the request session is discarded still sees `archived_at`
    # NULL (the service did not commit).
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    async with sm() as session:
        category = Category(name="Logement", parent_id=None)
        session.add(category)
        await session.commit()
        category_id = category.id

    async with sm() as session:
        await archive_category(session, category_id=category_id)
        # no commit — closing the session rolls back.

    async with sm() as session:
        archived_at = (
            await session.execute(select(Category.archived_at).where(Category.id == category_id))
        ).scalar_one()
        assert archived_at is None


@pytest.mark.usefixtures("_clean_committed_db")
async def test_delete_flush_only_no_commit(committed_engine: AsyncEngine) -> None:
    # Flush-only: a hard-delete without commit must leave the row in place for
    # an independent session.
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    async with sm() as session:
        category = Category(name="Leaf", parent_id=None)
        session.add(category)
        await session.commit()
        category_id = category.id

    async with sm() as session:
        await delete_category(session, category_id=category_id)
        # no commit

    async with sm() as session:
        assert await _count(session) == 1
        assert category_id is not None
