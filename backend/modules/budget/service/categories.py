"""Category service (S06.2): create + re-parent with cycle prevention.

Both ops run the pure `CycleDetector` **before any write** (CONTEXT.md
§Catégorie), then flush — **never commit** (ADR 0015: `get_db` owns the
transaction boundary; this is an ordinary business service, not a
security-critical side effect). The parent lookup the detector needs is
materialised by one `WITH RECURSIVE` query (`_load_ancestor_chain`),
inverting the dependency so `domain.py` stays SQLAlchemy-free.

Internal to budget — no `public.py` re-export yet (no cross-module consumer
until E07/E08); the S06.3 routes live in `budget.transports` (intra-module).

Concurrency caveat (D12): the cycle check is read-then-write with no lock,
so two concurrent `move_category` calls can each validate yet jointly close
a cycle (TOCTOU). Acceptable here — no route exists in S06.2 — and the
serialising guard (household-global advisory lock / `FOR UPDATE` / retry on
`SERIALIZABLE`) lands with the routes in S06.3.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.budget.domain import (
    CategoryInUseError,
    CategoryNotFoundError,
    CycleDetector,
)
from backend.modules.budget.models import Category


async def _load_ancestor_chain(session: AsyncSession, start_id: UUID) -> dict[UUID, UUID | None]:
    """`{id: parent_id}` for `start_id` and all its ancestors, in one query.

    Recursive CTE walking `parent_id` upward. `UNION` (not `UNION ALL`)
    dedups, so the *read* terminates even if the stored tree were corrupted
    (defense doubling `CycleDetector`'s visited-set — note this guards read
    termination, NOT concurrent cycle creation, cf. D12). Bounded by tree
    depth.
    """
    cat = Category.__table__
    anchor = (
        select(cat.c.id, cat.c.parent_id)
        .where(cat.c.id == start_id)
        .cte("ancestors", recursive=True)
    )
    parent = cat.alias("p")
    chain = anchor.union(
        select(parent.c.id, parent.c.parent_id).join(anchor, parent.c.id == anchor.c.parent_id)
    )
    rows = (await session.execute(select(chain.c.id, chain.c.parent_id))).all()
    return {row.id: row.parent_id for row in rows}


async def _assert_no_cycle(
    session: AsyncSession, *, node_id: UUID, new_parent_id: UUID | None
) -> None:
    """Run the pure detector against a freshly-loaded ancestor chain.

    The root case (`new_parent_id is None`) short-circuits here, so the
    domain's None branch is exercised from the service, not the DB — no
    query is issued for a move to root.
    """
    if new_parent_id is None:
        CycleDetector.detect_cycle(node_id=node_id, new_parent_id=None, get_parent=lambda _: None)
        return
    chain = await _load_ancestor_chain(session, new_parent_id)
    CycleDetector.detect_cycle(node_id=node_id, new_parent_id=new_parent_id, get_parent=chain.get)


async def create_category(
    session: AsyncSession,
    *,
    name: str,
    color: str | None = None,
    icon: str | None = None,
    parent_id: UUID | None = None,
) -> Category:
    """Create a category, cycle-checked before write (D6).

    The id is generated server-side and the node has no children yet, so a
    cycle is impossible by construction — the detector call is kept for
    symmetry with `move_category` (they share `_assert_no_cycle`) and as a
    guard against a future client-supplied id. Parent existence is enforced
    by the self-FK constraint at flush — an unknown `parent_id` raises
    `IntegrityError` (clean 404/422 mapping is S06.3). Flush-only (ADR 0015).
    """
    new_id = uuid4()
    await _assert_no_cycle(session, node_id=new_id, new_parent_id=parent_id)
    category = Category(id=new_id, name=name, color=color, icon=icon, parent_id=parent_id)
    session.add(category)
    await session.flush()  # surface PK; no commit (get_db owns it, ADR 0015)
    return category


async def move_category(
    session: AsyncSession, *, category_id: UUID, new_parent_id: UUID | None
) -> Category:
    """Re-parent a category, rejecting any cycle **before** the write (D3/D11).

    Raises `CategoryNotFoundError` if the node is unknown, `CategoryCycleError`
    if the move would close a cycle. No audit log here (S06.3). Flush-only.
    """
    category = await session.get(Category, category_id)
    if category is None:
        raise CategoryNotFoundError(f"category {category_id} not found")
    await _assert_no_cycle(session, node_id=category_id, new_parent_id=new_parent_id)
    category.parent_id = new_parent_id
    await session.flush()
    return category


async def archive_category(session: AsyncSession, *, category_id: UUID) -> bool:
    """Soft-delete a category: set `archived_at = now()`, **no cascade** (D9).

    Returns `False` if the category is unknown OR already archived (→ 404,
    gabarit `accounts.archive`): a re-DELETE of an archived row finds it
    already tombstoned and is idempotent in the "no corruption / row
    preserved" sense, not a 204-replay. Children are deliberately untouched
    (CONTEXT.md "pas de cascade") — a child of an archived parent stays
    active. Household-global: no user filter (D3). Flush-only (ADR 0015).
    """
    category = await session.get(Category, category_id)
    if category is None or category.archived_at is not None:
        return False
    category.archived_at = datetime.now(UTC)
    await session.flush()
    return True


async def delete_category(session: AsyncSession, *, category_id: UUID) -> bool:
    """Hard-delete a category — **not routed** (admin tooling, D8).

    Returns `False` if unknown. Raises `CategoryInUseError` if the node has
    ≥ 1 **non-archived** sub-category (in E07 the counter extends to
    `splits.category_id`). Otherwise deletes the row and flushes.

    The self-FK `RESTRICT` is the DB-level twin of this rule and is STRICTER
    (it counts *any* child, archived included): a node whose only children
    are archived passes the service count (0 active) yet trips 23503 at
    flush. We catch that and re-raise `CategoryInUseError`, so the helper's
    contract stays uniform ("refuses while in use") whichever rampart fires
    — the residue is never an opaque `IntegrityError` (D8). Flush-only.
    """
    category = await session.get(Category, category_id)
    if category is None:
        return False
    active_children = (
        await session.execute(
            select(func.count())
            .select_from(Category)
            .where(Category.parent_id == category_id, Category.archived_at.is_(None))
        )
    ).scalar_one()
    if active_children > 0:
        raise CategoryInUseError(
            f"category {category_id} has {active_children} active sub-categories"
        )
    await session.delete(category)
    try:
        await session.flush()
    except IntegrityError as exc:  # archived-only children → self-FK RESTRICT (23503)
        if getattr(exc.orig, "sqlstate", None) == "23503":
            raise CategoryInUseError(
                f"category {category_id} still has archived sub-categories (FK RESTRICT)"
            ) from exc
        raise
    return True
