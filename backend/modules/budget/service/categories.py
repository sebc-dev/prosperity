"""Category service (S06.2/S06.3): full category lifecycle.

Every cycle-checking op runs the pure `CycleDetector` **before any write**
(CONTEXT.md §Catégorie), then flushes — **never commits** (ADR 0015: `get_db`
owns the transaction boundary; an ordinary business service, not a
security-critical side effect). The detector is pure, so the service injects
the parent lookup it needs.

The two cycle-checking paths read that lookup **differently**, by design:

* `create_category` keeps the S06.2 `_load_ancestor_chain` (a single
  `WITH RECURSIVE` snapshot): the id is freshly minted server-side and the
  node has no descendants, so no concurrent op can race it into a cycle — the
  guard is a defensive symmetry, not a contended path.
* `move_category` (S06.3) is the **only** mutation that can race two callers
  into a persistent cycle (no DB acyclicity constraint can catch it), so it is
  hardened (D7): it takes a household-global `pg_advisory_xact_lock` as its
  first statement (serialising movers, ordering row locks → no deadlock), then
  walks ancestors row-by-row with `_load_ancestor_chain_locked`
  (`SELECT … FOR SHARE`, `populate_existing=True`). Under the engine's
  REPEATABLE READ isolation (`shared.db`), `FOR SHARE` is the only primitive
  that, inside an already-open RR transaction, reads a predecessor's
  **committed** state or aborts with `40001` — closing the snapshot-freeze
  TOCTOU window the advisory lock alone cannot (the lock orders writes, not
  read freshness). The route maps `40001`/`40P01` to a 409 retry.

Internal to budget — no `public.py` re-export yet (no cross-module consumer
until E07/E08); the S06.3 routes live in `budget.transports` (intra-module).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.budget.domain import (
    CategoryInUseError,
    CategoryNotFoundError,
    CycleDetector,
)
from backend.modules.budget.models import Category

# Household-global advisory lock key for `move_category` (D7). A stable
# constant: V1 is mono-household, and this is the only advisory lock in the
# system. E13 (multi-household) switches to the two-arg form
# `pg_advisory_xact_lock(key, household_id)` so movers in different households
# do not serialise against each other.
_CATEGORY_MOVE_LOCK_KEY = 0xCA7E_0603

# Reads `{id: parent_id}` for a node and its ancestors. `_assert_no_cycle` is
# parametrised by which loader to use: `create_category` takes the CTE snapshot
# (`_load_ancestor_chain`), `move_category` the hardened `FOR SHARE` walk
# (`_load_ancestor_chain_locked`, D7).
_ChainLoader = Callable[[AsyncSession, UUID], Awaitable[dict[UUID, UUID | None]]]


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
    session: AsyncSession,
    *,
    node_id: UUID,
    new_parent_id: UUID | None,
    load_chain: _ChainLoader = _load_ancestor_chain,
) -> None:
    """Run the pure detector against a freshly-loaded ancestor chain.

    The root case (`new_parent_id is None`) short-circuits here, so the
    domain's None branch is exercised from the service, not the DB — no
    query is issued for a move to root. `load_chain` selects how the chain is
    read: the default CTE snapshot for `create_category`, or the hardened
    `FOR SHARE` walk (`_load_ancestor_chain_locked`) injected by `move_category`
    (D7) — both paths share this single guard.
    """
    if new_parent_id is None:
        CycleDetector.detect_cycle(node_id=node_id, new_parent_id=None, get_parent=lambda _: None)
        return
    chain = await load_chain(session, new_parent_id)
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


async def _load_ancestor_chain_locked(
    session: AsyncSession, start_id: UUID
) -> dict[UUID, UUID | None]:
    """`{id: parent_id}` for `start_id` and its ancestors, read **FOR SHARE**.

    The hardened twin of `_load_ancestor_chain` for `move_category` (D7):
    instead of one CTE snapshot, it walks the chain row-by-row with
    `SELECT … FOR SHARE`, so under REPEATABLE READ it reads each predecessor's
    committed state — or aborts with `40001` if a concurrent mover committed a
    change after this transaction's snapshot froze. `populate_existing=True` is
    mandatory: without it `session.get` may return a row already in the
    identity-map **without re-emitting the locking SELECT**, silently skipping
    the lock. The `current not in chain` guard bounds the walk even on an
    already-corrupted tree (read-termination, mirroring `CycleDetector`).
    """
    chain: dict[UUID, UUID | None] = {}
    current: UUID | None = start_id
    while current is not None and current not in chain:
        row = await session.get(
            Category, current, with_for_update={"read": True}, populate_existing=True
        )
        if row is None:  # unknown new_parent: stop; the FK 23503 maps to 422 at flush
            break
        chain[current] = row.parent_id
        current = row.parent_id
    return chain


async def move_category(
    session: AsyncSession, *, category_id: UUID, new_parent_id: UUID | None
) -> tuple[Category, UUID | None]:
    """Re-parent a category, rejecting any cycle **before** the write, serialised (D7).

    Returns `(category, previous_parent_id)` so the route can audit
    `from_parent_id` without a second read. Raises `CategoryNotFoundError` if
    the node is unknown **or archived** (an archived category is invisible —
    you cannot move what you cannot edit, symmetric with `update_category`,
    D10), `CategoryCycleError` if the move would close a cycle.

    Hardening (D7): a `pg_advisory_xact_lock` taken as the first statement
    serialises concurrent movers; the ancestor walk then uses `FOR SHARE`
    (`_load_ancestor_chain_locked`) to read committed state under REPEATABLE
    READ. The cycle is validated **before** the write, so a rejected move
    raises before any mutation (and, at the route, before any audit row).
    Flush-only (ADR 0015).
    """
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _CATEGORY_MOVE_LOCK_KEY})
    category = await session.get(Category, category_id, populate_existing=True)
    if category is None or category.archived_at is not None:
        raise CategoryNotFoundError(f"category {category_id} not found")
    previous_parent_id = category.parent_id
    await _assert_no_cycle(
        session,
        node_id=category_id,
        new_parent_id=new_parent_id,
        load_chain=_load_ancestor_chain_locked,
    )
    category.parent_id = new_parent_id
    await session.flush()
    return category, previous_parent_id


async def list_categories(session: AsyncSession, *, include_archived: bool) -> Sequence[Category]:
    """Flat, household-global category list (D3/D11).

    By default excludes archived rows (`archived_at IS NULL`, served by the
    partial index `ix_categories_active`); `include_archived=True` returns
    every row. Ordered by `(created_at, id)` — the `id` tie-breaker makes the
    order deterministic for two rows sharing a `created_at` (stable shape
    tests). No user filter: a category is visible to any household member.
    """
    stmt = select(Category)
    if not include_archived:
        stmt = stmt.where(Category.archived_at.is_(None))
    stmt = stmt.order_by(Category.created_at, Category.id)
    return (await session.execute(stmt)).scalars().all()


async def update_category(
    session: AsyncSession, *, category_id: UUID, fields: dict[str, object]
) -> Category | None:
    """Edit `name`/`color`/`icon` (partial). Returns `None` if unknown or archived.

    An archived category is treated as absent (→ 404, D10): it is invisible in
    the pickers, so it cannot be edited — symmetric with `move_category`, which
    also 404s an archived node. `fields` carries only the keys the client sent
    (`exclude_unset`). Flush-only (ADR 0015).
    """
    category = await session.get(Category, category_id)
    if category is None or category.archived_at is not None:
        return None
    for key, value in fields.items():
        setattr(category, key, value)
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
