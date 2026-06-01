"""Pure domain for the budget module (no SQLAlchemy / session / FastAPI).

`CycleDetector` decides whether re-parenting a category would close a cycle
in the unbounded tree (CONTEXT.md §Catégorie « Cycle prevention : validation
au service »). It is **pure**: the service injects `get_parent`, a callable
mapping a node to its parent — in production a closure over a parent chain
pre-loaded by one `WITH RECURSIVE` query; in tests a plain `dict.get`. The
domain never touches the DB (gabarit `accounts.domain.AccountValidator`,
which receives `household_base_currency` instead of importing the ORM).

Internal to `modules.budget`: cross-module callers reach domain values
through `backend.modules.budget.public` (empty in S06.2 — no consumer yet).
Import-linter contract `2-budget` forbids reaching into this module from
peer modules; it imports only the stdlib, so it creates no cross-module arc.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID


class CategoryError(Exception):
    """Base of every pure category-rule violation (S06.2).

    Stays in `domain.py` (stdlib-only) so the service can map the whole
    family with one `except CategoryError` at the S06.3 boundary while
    `domain.py` imports nothing but the stdlib.
    """


class CategoryCycleError(CategoryError):
    """Re-parenting would close a cycle (direct self-ref or descendant loop)."""


class CategoryNotFoundError(CategoryError):
    """Target category does not exist (used by `move_category`, S06.2).

    Co-located with the family even though it reports a *DB-absence* state
    (not a pure rule violation) — acceptable for a single S06.3 route
    mapping; the class itself imports nothing, keeping `domain.py` stdlib-only.
    """


class CategoryInUseError(CategoryError):
    """Hard-delete refused: the category is still referenced (S06.3, D8).

    Raised by `delete_category` when the node has ≥ 1 non-archived
    sub-category, or when the self-FK `RESTRICT` trips on an archived child
    at flush (the DB-level twin is stricter than the service count, so the
    service catches the 23503 and re-raises it here for a uniform contract).
    In E07 the counter extends to `splits.category_id`.

    Co-located with the family — like `CategoryNotFoundError`, it reports a
    DB-state condition (not a pure rule violation), so the S06.3 boundary
    maps the whole family with one `except CategoryError` while `domain.py`
    stays stdlib-only.
    """


class CycleDetector:
    """Pure acyclicity guard for category re-parenting (CONTEXT.md §Catégorie).

    `detect_cycle` raises `CategoryCycleError` iff setting `node_id`'s parent
    to `new_parent_id` would create a cycle:
      - `new_parent_id is None` (root) → always OK;
      - `new_parent_id == node_id`   → direct self-reference → cycle;
      - walking ancestors of `new_parent_id` reaches `node_id` → `node_id` is
        an ancestor of the new parent, i.e. we'd hang the new parent's subtree
        (which contains `node_id`) under `node_id` → cycle.

    Termination is unconditional: the `visited` set bounds the walk to at
    most N distinct steps even on an already-corrupted tree (acceptance
    criterion #5). No integer bound constant — it would be a dead branch
    behind `visited` and sink branch coverage.
    """

    @staticmethod
    def detect_cycle(
        *,
        node_id: UUID,
        new_parent_id: UUID | None,
        get_parent: Callable[[UUID], UUID | None],
    ) -> None:
        if new_parent_id is None:
            return  # re-parent to root: never a cycle
        if new_parent_id == node_id:
            raise CategoryCycleError(f"category {node_id} cannot be its own parent")

        # Order matters: test `== node_id` *before* the visited-guard, so a
        # legitimate cycle whose node sits inside a corrupted loop is still
        # reported instead of silently broken out of.
        visited: set[UUID] = set()
        current: UUID | None = new_parent_id
        while current is not None:
            if current == node_id:
                raise CategoryCycleError(
                    f"category {node_id} is an ancestor of {new_parent_id}: "
                    "moving it under its own descendant would create a cycle"
                )
            if current in visited:
                break  # corrupted-tree guard: terminate, never loop
            visited.add(current)
            current = get_parent(current)
