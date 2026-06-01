"""Concurrency proofs for the hardened `move_category` (S06.3, P06.3.3, D7).

These tests run on `committed_sessionmaker` (real commits, REPEATABLE READ —
production isolation), NOT `async_client`: the savepoint harness shares one
connection, so it cannot exercise true cross-session concurrency or the
`SELECT … FOR SHARE` → 40001 abort. Two proofs:

1. The primitive in isolation: under a frozen REPEATABLE READ snapshot, a
   `FOR SHARE` read of a row another session has committed-modified aborts with
   SQLSTATE 40001. If a PG/driver upgrade ever broke this, the whole D7
   hardening would silently become a no-op — this test pins it.
2. The TOCTOU scenario end-to-end: two opposite moves whose snapshots both
   freeze before either writes. The first commits; the second's `FOR SHARE`
   ancestor walk reads the freshly-committed predecessor → 40001 (NOT a
   trivial cycle error), and the tree stays acyclic.

Both are deterministic — statements are driven step-by-step, no sleeps/timing.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.modules.budget.models import Category
from backend.modules.budget.service.categories import move_category

pytestmark = [pytest.mark.usefixtures("_clean_committed_db")]

# Type alias for readability.
_Sessionmaker = async_sessionmaker[_AsyncSession]


async def _seed_root(sm: _Sessionmaker, name: str) -> Category:
    async with sm() as session:
        category = Category(name=name, parent_id=None)
        session.add(category)
        await session.commit()
        # `expire_on_commit=False` on the maker keeps `.id` readable after commit.
        return category


async def test_for_share_raises_40001_on_stale_predecessor(
    committed_sessionmaker: _Sessionmaker,
) -> None:
    # Pin the primitive D7 relies on (independently of move_category).
    target = await _seed_root(committed_sessionmaker, "X")
    other = await _seed_root(committed_sessionmaker, "Y")
    target_id, other_id = target.id, other.id

    async with committed_sessionmaker() as sa, committed_sessionmaker() as sb:
        # A: initial read freezes A's REPEATABLE READ snapshot.
        await sa.execute(text("SELECT id FROM categories WHERE id = :x"), {"x": target_id})

        # B: modify X and COMMIT (in its own transaction).
        await sb.execute(
            text("UPDATE categories SET parent_id = :p WHERE id = :x"),
            {"p": other_id, "x": target_id},
        )
        await sb.commit()

        # A: FOR SHARE read of X — modified-and-committed after A's snapshot ⇒
        # serialization_failure (40001), the only RR-safe "read committed or
        # abort" primitive.
        with pytest.raises(DBAPIError) as excinfo:
            await sa.execute(
                text("SELECT id FROM categories WHERE id = :x FOR SHARE"), {"x": target_id}
            )
        assert getattr(excinfo.value.orig, "sqlstate", None) == "40001"


async def test_concurrent_opposite_moves_no_cycle(
    committed_sessionmaker: _Sessionmaker,
) -> None:
    # Two siblings A, B. Txn1: move A under B. Txn2 (concurrent): move B under A.
    # Both snapshots freeze BEFORE either write (the TOCTOU core). Txn1 commits;
    # Txn2's FOR SHARE walk reads the freshly-committed A ⇒ 40001. The advisory
    # lock serialises the writers; the FOR SHARE walk closes the read window.
    a = await _seed_root(committed_sessionmaker, "A")
    b = await _seed_root(committed_sessionmaker, "B")
    a_id, b_id = a.id, b.id

    async with committed_sessionmaker() as s1, committed_sessionmaker() as s2:
        # Freeze BOTH snapshots before any write (force the ordering explicitly).
        await s1.execute(text("SELECT id FROM categories"))
        await s2.execute(text("SELECT id FROM categories"))

        # Txn1: move A under B, then commit (releases the advisory lock).
        moved, previous = await move_category(s1, category_id=a_id, new_parent_id=b_id)
        assert moved.parent_id == b_id
        assert previous is None
        await s1.commit()

        # Txn2: move B under A. The advisory lock is now free, but s2's snapshot
        # froze before s1's commit ⇒ the FOR SHARE walk of A (the new parent,
        # just committed-modified) aborts with 40001 — proving the D7 read path,
        # NOT a trivial CategoryCycleError on stale data.
        with pytest.raises(DBAPIError) as excinfo:
            await move_category(s2, category_id=b_id, new_parent_id=a_id)
        assert getattr(excinfo.value.orig, "sqlstate", None) == "40001"

    # From a THIRD session opened after both transactions ended: the tree has at
    # most one edge (A→B) and is acyclic.
    async with committed_sessionmaker() as s3:
        a_parent = (
            await s3.execute(select(Category.parent_id).where(Category.id == a_id))
        ).scalar_one()
        b_parent = (
            await s3.execute(select(Category.parent_id).where(Category.id == b_id))
        ).scalar_one()
        assert a_parent == b_id
        assert b_parent is None
