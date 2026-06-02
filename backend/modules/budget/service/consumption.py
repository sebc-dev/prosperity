"""Budget consumption service (S08.2): the aggregation core of E08.

`compute_consumption` answers "how much of this budget has been spent over the
period window containing `as_of`". It aggregates **at read time** (CONTEXT.md
§Budget « les budgets agrègent à la lecture, pas à l'écriture ») the confirmed
splits of the budget's category **and its whole subtree**, filtered by the
period window, by the eligible accounts (contributor semantics, D7) and
excluding `force_full_debt` transactions (CONTEXT.md §debt_generation_override
« hors budget »).

Layering (ADR 0005, contract 1): `transactions ⊥ budget` (same layer), so the
`splits`/`transactions` tables are read via **SQLAlchemy Core** lightweight
`table()`/`column()` declarations — never importing `transactions.models`
(which would break the directional graph). CONTEXT.md §Split sanctions the
*read* cross-module for budget aggregation; only *mutation* is forbidden. The
light `table()` form (vs `Table(..., Base.metadata, autoload)`) also avoids any
dependency on model-registration order on `Base.metadata`.

`accounts` sits *below* budget in the graph → `accounts.public` is imported
directly for the contributor filter (D2/D7). `categories` is intra-module →
read via the ORM (recursive CTE).

Read-only (ADR 0015): `compute_consumption` never flushes nor commits. `as_of`
is a **required** keyword (no hidden `date.today()`): the calling route (S08.4)
supplies the default, keeping the service deterministic and testable.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import column, func, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.public import (
    owned_personal_account_ids,
    shared_account_ids_with_members_subset,
)
from backend.modules.budget.domain import (
    BudgetConsumption,
    compute_period_window,
    consumption_from_totals,
)
from backend.modules.budget.models import Budget, BudgetContributor, Category

# Lightweight Core handles on a PEER module's tables (`transactions ⊥ budget`,
# contract 1). NO import of `transactions.models` — read-only access only
# (CONTEXT.md §Split sanctions budget aggregation reads). Only the columns the
# SUM query touches are declared.
_splits = table(
    "splits",
    column("account_id"),
    column("category_id"),
    column("amount_cents"),
    column("currency"),
    column("transaction_id"),
)
_transactions = table(
    "transactions",
    column("id"),
    column("date"),
    column("state"),
    column("debt_generation_override"),
)


async def _load_descendant_ids(session: AsyncSession, root_id: UUID) -> set[UUID]:
    """Ids du sous-arbre de `root_id` (racine incluse), 1 CTE récursive descendante.

    Miroir descendant de `categories._load_ancestor_chain` (sens inverse :
    enfants au lieu d'ancêtres). `UNION` (dédup) → terminaison même sur un arbre
    corrompu. `Category` est intra-module → ORM direct, pas de contrainte de
    layer. Bornée par la taille du sous-arbre.
    """
    cat = Category.__table__
    anchor = select(cat.c.id).where(cat.c.id == root_id).cte("descendants", recursive=True)
    child = cat.alias("c")
    tree = anchor.union(select(child.c.id).join(anchor, child.c.parent_id == anchor.c.id))
    return set((await session.execute(select(tree.c.id))).scalars().all())


async def _eligible_account_ids(session: AsyncSession, budget: Budget) -> set[UUID]:
    """Comptes dont les splits comptent pour `budget` (D7). Fail-closed sur scope inconnu.

    `personal` → comptes personnels de l'owner (`budget.created_by`). `shared` →
    comptes communs dont tous les members sont contributeurs du budget
    (sous-ensemble). Tout autre `scope` → ensemble vide (consommation 0), jamais
    une fuite cross-scope.
    """
    if budget.scope == "personal":
        return await owned_personal_account_ids(session, owner_id=budget.created_by)
    if budget.scope == "shared":
        contributor_ids = set(
            (
                await session.execute(
                    select(BudgetContributor.user_id).where(
                        BudgetContributor.budget_id == budget.id
                    )
                )
            )
            .scalars()
            .all()
        )
        return await shared_account_ids_with_members_subset(session, member_ids=contributor_ids)
    return set()  # scope inattendu → fail-closed (aucun compte → consommation 0)


async def compute_consumption(
    session: AsyncSession, *, budget_id: UUID, as_of: date
) -> BudgetConsumption | None:
    """Consommation de `budget_id` à `as_of`. `None` si le budget est inconnu.

    Lecture seule (ADR 0015 : aucun flush/commit). Agrège les legs « catégorie »
    (forme canonique E15 : seul le leg de dépense porte `category_id`, D4) des
    splits `confirmed`, hors `force_full_debt` (D6), de catégorie ∈ sous-arbre
    de `budget.category_id` (D3), dont la transaction tombe dans la fenêtre
    `[start, end)` (D5), sur les comptes éligibles (D7), en devise du budget
    (D8, mono-devise V1). `percent`/`remaining` dérivés par
    `consumption_from_totals` (garde-fou `amount <= 0`).
    """
    budget = await session.get(Budget, budget_id)
    if budget is None:
        return None

    start, end = compute_period_window(budget.period_kind, budget.period_start, as_of)  # type: ignore[arg-type]
    subtree = await _load_descendant_ids(session, budget.category_id)
    accounts = await _eligible_account_ids(session, budget)

    if not subtree or not accounts:
        # Aucune catégorie ou aucun compte éligible → rien à sommer (court-circuit
        # qui évite un `IN ()` dégénéré).
        return consumption_from_totals(
            consumed_cents=0, amount_cents=budget.amount_cents, splits_count=0
        )

    stmt = (
        select(func.coalesce(func.sum(_splits.c.amount_cents), 0), func.count())
        .select_from(_splits.join(_transactions, _splits.c.transaction_id == _transactions.c.id))
        .where(
            _splits.c.category_id.in_(subtree),
            _splits.c.account_id.in_(accounts),
            _splits.c.currency == budget.currency,
            _transactions.c.state == "confirmed",
            _transactions.c.debt_generation_override != "force_full_debt",
            _transactions.c.date >= start,
            _transactions.c.date < end,
        )
    )
    consumed_cents, splits_count = (await session.execute(stmt)).one()
    return consumption_from_totals(
        consumed_cents=int(consumed_cents),
        amount_cents=budget.amount_cents,
        splits_count=int(splits_count),
    )
