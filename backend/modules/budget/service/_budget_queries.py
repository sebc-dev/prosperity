"""Primitives Core SQLAlchemy partagées entre `consumption.py` et `threshold_detector.py`.

Fichier privé (`_`-préfixé) — strictement intra-`budget/service/`, jamais
ré-exporté via `budget/public.py`. Élimine le cycle d'import
`consumption ↔ threshold_detector` en centralisant les deux primitives communes :
handles Core peer-module (`_splits`, `_transactions`) et walk-up ancêtre
(`_concerned_budgets`).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import column, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.budget.models import Budget, Category

# Lightweight Core handles on a PEER module's tables (`transactions ⊥ budget`,
# contract 1). NO import of `transactions.models` — read-only access only
# (CONTEXT.md §Split sanctions budget aggregation reads). Columns: union des
# colonnes requises par `consumption.py` (6) et `threshold_detector.py` (2).
# Sans préfixe `_` : le fichier `_budget_queries.py` est déjà le marqueur de
# confidentialité ; les symboles ici sont l'API interne du fichier privé.
splits = table(
    "splits",
    column("id"),
    column("account_id"),
    column("category_id"),
    column("amount_cents"),
    column("currency"),
    column("transaction_id"),
)
transactions = table(
    "transactions",
    column("id"),
    column("date"),
    column("state"),
    column("debt_generation_override"),
)


async def concerned_budgets(session: AsyncSession, category_ids: set[UUID]) -> list[Budget]:
    """Active budgets whose category is an ancestor-or-self of a split category.

    A budget is concerned iff `split.category ∈ subtree(budget.category)` ⟺
    `budget.category` is an ancestor-or-self of a split category — so we walk
    UPWARD (recursive CTE, gabarit `categories._load_ancestor_chain`), then join
    active budgets. SELECTs the full `Budget` ENTITIES (populates the identity-map
    → no re-SELECT per `session.get` in the handler loop). Ordered `(created_at,
    id)` for determinism.

    Over-resolution is safe: the `publish` decision depends EXCLUSIVELY on
    `crossed_thresholds(consumed, amount)`, where `consumed` is recomputed by
    `compute_consumption` (re-filtered strictly by subtree, eligible accounts,
    window, currency, state) — never on membership of this candidate set. A
    falsely-candidate budget computes its true consumption (often 0 on the
    eligible accounts) → `crossed_thresholds` returns `[]` → no INSERT, no publish.
    This only WIDENS the candidate set, never triggers an effect by itself.
    """
    cat = Category.__table__
    anchor = (
        select(cat.c.id, cat.c.parent_id)
        .where(cat.c.id.in_(category_ids))
        .cte("concerned", recursive=True)
    )
    parent = cat.alias("p")
    chain = anchor.union(  # UNION (dedup) → terminates even on a corrupted tree
        select(parent.c.id, parent.c.parent_id).join(anchor, parent.c.id == anchor.c.parent_id)
    )
    stmt = (
        select(Budget)
        .where(Budget.category_id.in_(select(chain.c.id)), Budget.archived_at.is_(None))
        .order_by(Budget.created_at, Budget.id)
    )
    return list((await session.execute(stmt)).scalars().all())
