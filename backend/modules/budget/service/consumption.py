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

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import ColumnElement, column, func, select, table, tuple_
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

logger = logging.getLogger(__name__)

# Lightweight Core handles on a PEER module's tables (`transactions ⊥ budget`,
# contract 1). NO import of `transactions.models` — read-only access only
# (CONTEXT.md §Split sanctions budget aggregation reads). Only the columns the
# SUM query touches are declared.
_splits = table(
    "splits",
    column("id"),
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
    # Scope inattendu → fail-closed (aucun compte → consommation 0). On trace
    # l'anomalie : un budget mal formé afficherait 0 au lieu d'alerter, ce qui
    # doit rester visible côté exploitation (pas de PII : id + scope bruts).
    logger.warning(
        "budget %s has unexpected scope %r; fail-closed to an empty account set",
        budget.id,
        budget.scope,
    )
    return set()


def _consumption_filters(
    *,
    subtree: Sequence[UUID],
    accounts: Sequence[UUID],
    currency: str,
    start: date,
    end: date,
) -> list[ColumnElement[bool]]:
    """Bloc `.where(...)` commun à `compute_consumption` ET `list_contributing_splits`
    (D13 — **source unique**).

    Les sept prédicats qui définissent « un split compté » : leg catégorie ∈
    sous-arbre, compte éligible, devise du budget, transaction `confirmed`, hors
    `force_full_debt` (CONTEXT.md §debt_generation_override), fenêtre `[start,
    end)`. Une seule définition ⇒ `splits_count` (agrégat) et le drill-down
    (liste paginée) ne peuvent pas diverger silencieusement si un prédicat évolue
    (affinage forme canonique E15, nouvel état). Seul le `select(...)` (SUM/COUNT
    vs colonnes + keyset) diffère entre les deux consommateurs.
    """
    return [
        _splits.c.category_id.in_(subtree),
        _splits.c.account_id.in_(accounts),
        _splits.c.currency == currency,
        _transactions.c.state == "confirmed",
        _transactions.c.debt_generation_override != "force_full_debt",
        _transactions.c.date >= start,
        _transactions.c.date < end,
    ]


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
            *_consumption_filters(
                subtree=list(subtree),
                accounts=list(accounts),
                currency=budget.currency,
                start=start,
                end=end,
            )
        )
    )
    consumed_cents, splits_count = (await session.execute(stmt)).one()
    return consumption_from_totals(
        consumed_cents=int(consumed_cents),
        amount_cents=budget.amount_cents,
        splits_count=int(splits_count),
    )


# --- Drill-down: contributing splits, paginated (S08.4 P08.4.3) -------------


@dataclass(frozen=True, slots=True)
class ContributingSplit:
    """One split that contributes to a budget's consumption (drill-down UI).

    `category_id` is **always non-NULL**: the `category_id ∈ subtree` filter
    excludes the canonical account leg (E15, whose `category_id` is NULL). The
    pure read shape — no ORM leak (the splits are read via Core, `transactions ⊥
    budget`).
    """

    id: UUID
    transaction_id: UUID
    account_id: UUID
    category_id: UUID
    amount_cents: int
    currency: str
    date: date


async def list_contributing_splits(
    session: AsyncSession,
    *,
    budget_id: UUID,
    as_of: date,
    after: tuple[date, UUID] | None,
    limit: int,
) -> tuple[list[ContributingSplit], tuple[date, UUID] | None]:
    """Page des splits contribuant à la consommation de `budget_id` + cursor suivant.

    Réutilise le **même** prédicat que `compute_consumption` via
    `_consumption_filters` (D13 — sous-arbre, comptes éligibles, fenêtre
    `[start,end)`, devise, `confirmed`, hors `force_full_debt`) en mode liste.
    Ordre `(transactions.date, splits.id)` DESC (ordre total : `splits.id` UUID
    unique). `LIMIT limit+1` détecte la page suivante ; keyset
    `tuple_(date, id) < after` (strict — ancré sur le **dernier** de la page).
    Lecture seule (ADR 0015), splits via Core (pas d'import `transactions`).

    RBAC : **RBAC-aveugle** — présuppose la visibilité vérifiée par l'appelant
    (`get_visible_budget` au boundary), comme `compute_consumption`. À ne JAMAIS
    exposer sans garde de visibilité en amont (la route S08.4 garde avant
    d'appeler). Le cursor ne déplace que l'offset keyset ; la requête reste bornée
    au `budget_id` de la route → un cursor d'un autre budget n'élargit pas le
    périmètre.
    """
    budget = await session.get(Budget, budget_id)
    if budget is None:
        return [], None
    start, end = compute_period_window(budget.period_kind, budget.period_start, as_of)  # type: ignore[arg-type]
    subtree = await _load_descendant_ids(session, budget.category_id)
    accounts = await _eligible_account_ids(session, budget)
    if not subtree or not accounts:
        return [], None

    stmt = (
        select(
            _splits.c.id,
            _splits.c.transaction_id,
            _splits.c.account_id,
            _splits.c.category_id,
            _splits.c.amount_cents,
            _splits.c.currency,
            _transactions.c.date,
        )
        .select_from(_splits.join(_transactions, _splits.c.transaction_id == _transactions.c.id))
        .where(
            *_consumption_filters(
                subtree=list(subtree),
                accounts=list(accounts),
                currency=budget.currency,
                start=start,
                end=end,
            )
        )
    )
    if after is not None:
        stmt = stmt.where(tuple_(_transactions.c.date, _splits.c.id) < after)
    stmt = stmt.order_by(_transactions.c.date.desc(), _splits.c.id.desc()).limit(limit + 1)
    rows = (await session.execute(stmt)).all()

    page = [
        ContributingSplit(
            id=r.id,
            transaction_id=r.transaction_id,
            account_id=r.account_id,
            category_id=r.category_id,
            amount_cents=int(r.amount_cents),
            currency=r.currency,
            date=r.date,
        )
        for r in rows[:limit]
    ]
    # The cursor is the LAST row of THIS page (the keyset filter `< after` is
    # strict, so anchoring on the first next-page row would skip it).
    next_cursor = (page[-1].date, page[-1].id) if len(rows) > limit else None
    return page, next_cursor
