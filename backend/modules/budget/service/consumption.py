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

from sqlalchemy import ColumnElement, column, func, literal, select, table, tuple_
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


def _consumption_filters(  # noqa: PLR0913 — flat keyword-only filter knobs (single source, D13)
    *,
    subtree: Sequence[UUID],
    accounts: Sequence[UUID],
    currency: str,
    start: date | None = None,
    end: date | None = None,
    before: tuple[date, UUID] | None = None,
) -> list[ColumnElement[bool]]:
    """Bloc `.where(...)` commun à `compute_consumption`, `list_contributing_splits`
    ET `list_overflow_recompute_tx_ids` (D13 — **source unique**).

    Les prédicats qui définissent « un split compté » : leg catégorie ∈
    sous-arbre, compte éligible, devise du budget, transaction `confirmed`, hors
    `force_full_debt` (CONTEXT.md §debt_generation_override), fenêtre `[start,
    end)`. Une seule définition ⇒ `splits_count` (agrégat), le drill-down (liste
    paginée) et l'énumération du reclassement (S11.4) ne peuvent pas diverger
    silencieusement si un prédicat évolue (affinage forme canonique E15, nouvel
    état). Seul le `select(...)` (SUM/COUNT vs colonnes + keyset vs DISTINCT id)
    diffère entre les consommateurs.

    `start`/`end` sont **optionnels** (défaut `None`) : la re-matérialisation F10
    (S11.4) balaye **toute** l'histoire d'un budget récurrent sans borne de fenêtre
    (D4 — la fenêtre par tx est rétablie par le materializer via `before`). Les
    appelants S08 passent toujours les deux ⇒ inchangés.

    `before` (overflow F10, S11.3) borne en plus la fenêtre aux transactions
    **strictement antérieures** dans l'ordre total `(date, id)` : c'est le
    « restant *avant* la transaction » d'une dépense datée, qui rend l'excédent
    conservatif `Σ E = max(0, ΣM − budget)` (CONTEXT.md §Excédent). `None` par
    défaut ⇒ les appelants S08 (consommation pleine période) sont inchangés.
    """
    filters = [
        _splits.c.category_id.in_(subtree),
        _splits.c.account_id.in_(accounts),
        _splits.c.currency == currency,
        _transactions.c.state == "confirmed",
        _transactions.c.debt_generation_override != "force_full_debt",
    ]
    if start is not None:
        filters.append(_transactions.c.date >= start)
    if end is not None:
        filters.append(_transactions.c.date < end)
    if before is not None:
        filters.append(tuple_(_transactions.c.date, _transactions.c.id) < before)
    return filters


async def compute_consumption(
    session: AsyncSession,
    *,
    budget_id: UUID,
    as_of: date,
    before: tuple[date, UUID] | None = None,
) -> BudgetConsumption | None:
    """Consommation de `budget_id` à `as_of`. `None` si le budget est inconnu.

    Lecture seule (ADR 0015 : aucun flush/commit). Agrège les legs « catégorie »
    (forme canonique E15 : seul le leg de dépense porte `category_id`, D4) des
    splits `confirmed`, hors `force_full_debt` (D6), de catégorie ∈ sous-arbre
    de `budget.category_id` (D3), dont la transaction tombe dans la fenêtre
    `[start, end)` (D5), sur les comptes éligibles (D7), en devise du budget
    (D8, mono-devise V1). `percent`/`remaining` dérivés par
    `consumption_from_totals` (garde-fou `amount <= 0`).

    `before` (overflow F10, S11.3) borne en plus aux transactions strictement
    antérieures `(date, id) < before` (fenêtre ordonnée) ⇒ le « restant avant la
    tx ». `None` (défaut) ⇒ consommation pleine période (appelants S08 inchangés).
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
                before=before,
            )
        )
    )
    consumed_cents, splits_count = (await session.execute(stmt)).one()
    return consumption_from_totals(
        consumed_cents=int(consumed_cents),
        amount_cents=budget.amount_cents,
        splits_count=int(splits_count),
    )


# --- Overflow budget resolution (E11 / S11.3 P11.3.2) -----------------------
#
# `resolve_overflow_context` answers, for a shared-account expense: "which active
# budget covers this category, and how much of it remained BEFORE this tx?". It
# is the single place that picks the *most specific* covering budget (CONTEXT.md
# §Excédent) and derives the ordered-window remaining — `debts` only ever
# receives the scalars, never a `Budget` row (graphe ADR 0005, contrat `2-debts`).

# Bounds the ancestor walk so a corrupted (cyclic) category tree cannot loop the
# recursive CTE forever (a real tree is far shallower; the dedup `UNION` used by
# the S08 walks cannot dedup once a `depth` column is carried, hence this cap).
_MAX_CATEGORY_DEPTH = 64


@dataclass(frozen=True, slots=True)
class OverflowBudgetContext:
    """Scalars the overflow materializer needs from `budget` (S11.3).

    `remaining_before_cents` is **clamped to ≥ 0**: the ordered window can leave a
    negative raw remaining when strictly-prior txs already exceeded the budget,
    but `DebtCalculator.compute_for_overflow` contracts `budget_remaining_before
    ≥ 0` — clamping keeps the excess additive/conservative (`Σ E = max(0, ΣM −
    budget)`) instead of charging a later tx MORE than its own amount. `currency`
    is the budget currency (V1 mono-devise, ADR 0008).
    """

    budget_id: UUID
    remaining_before_cents: int
    currency: str


async def resolve_overflow_context(
    session: AsyncSession,
    *,
    category_ids: set[UUID],
    account_id: UUID,
    as_of: date,
    before: tuple[date, UUID],
) -> OverflowBudgetContext | None:
    """The most specific active budget covering `category_ids` AND eligible for
    `account_id`, with its remaining BEFORE `before` (ordered window). `None` if
    none (→ overflow base = full expense, S11.3 D9).

    « Most specific » = the candidate whose category is the closest ancestor-or-self
    of a tx category (smallest walk-up depth), tie-break `(created_at, id)` — the
    rule frozen in CONTEXT.md §Excédent. The `account_id ∈ _eligible_account_ids`
    filter excludes `personal` budgets (a shared account is never among an owner's
    personal accounts), so a personal budget never applies to a shared-account
    expense. V1 mono-catégorie ⇒ unambiguous.
    """
    if not category_ids:
        return None

    cat = Category.__table__
    anchor = (
        select(cat.c.id, cat.c.parent_id, literal(0).label("depth"))
        .where(cat.c.id.in_(category_ids))
        .cte("overflow_walkup", recursive=True)
    )
    parent = cat.alias("p")
    walkup = anchor.union_all(
        select(parent.c.id, parent.c.parent_id, anchor.c.depth + 1)
        .join(anchor, parent.c.id == anchor.c.parent_id)
        .where(anchor.c.depth < _MAX_CATEGORY_DEPTH)  # terminate even on a cycle
    )
    depth_per_cat = (
        select(walkup.c.id, func.min(walkup.c.depth).label("depth"))
        .group_by(walkup.c.id)
        .cte("overflow_depth")
    )
    # Candidates ordered most-specific-first (depth ASC, then deterministic
    # `(created_at, id)`); SELECT the full entity so `_eligible_account_ids`
    # reuses the identity-map.
    candidates = (
        (
            await session.execute(
                select(Budget)
                .join(depth_per_cat, Budget.category_id == depth_per_cat.c.id)
                .where(Budget.archived_at.is_(None))
                .order_by(depth_per_cat.c.depth, Budget.created_at, Budget.id)
            )
        )
        .scalars()
        .all()
    )

    for budget in candidates:
        eligible = await _eligible_account_ids(session, budget)
        if account_id not in eligible:
            continue  # e.g. a personal budget never covers a shared-account expense
        consumption = await compute_consumption(
            session, budget_id=budget.id, as_of=as_of, before=before
        )
        if consumption is None:  # defensive: budget purged concurrently
            continue
        return OverflowBudgetContext(
            budget_id=budget.id,
            # `consumption.remaining_cents` is already `amount_cents − consumed_cents`
            # (`budget.amount_cents` is what `compute_consumption` summed against) —
            # reuse the derived scalar; clamp ≥ 0 (ordered window can go negative once
            # strictly-prior txs exceeded the budget, see `OverflowBudgetContext`).
            remaining_before_cents=max(0, consumption.remaining_cents),
            currency=budget.currency,
        )
    return None


async def list_overflow_recompute_tx_ids(session: AsyncSession, *, budget_id: UUID) -> list[UUID]:
    """Distinct `transaction_id`s whose a classification split counts for `budget_id`
    (S11.4 reclassement F10), over the WHOLE history — NO window bound (D4).

    Reuses `_consumption_filters` (single source, D13) without `start`/`end`:
    subtree + eligible accounts + currency + `confirmed`, excluding
    `force_full_debt`. The per-tx window is restored downstream by the materializer
    (`before=(tx.date, tx.id)`), so this enumeration must NOT know it — a recurring
    budget covers all its past/future windows, and reclassement targets « les
    transactions passées ». `[]` if the budget is unknown or its subtree / eligible
    accounts are empty. Read-only (ADR 0015).
    """
    budget = await session.get(Budget, budget_id)
    if budget is None:
        return []
    subtree = await _load_descendant_ids(session, budget.category_id)
    accounts = await _eligible_account_ids(session, budget)
    if not subtree or not accounts:
        return []
    stmt = (
        select(_splits.c.transaction_id)
        .select_from(_splits.join(_transactions, _splits.c.transaction_id == _transactions.c.id))
        .where(
            *_consumption_filters(
                subtree=list(subtree), accounts=list(accounts), currency=budget.currency
            )
        )
        .distinct()
    )
    return list((await session.execute(stmt)).scalars().all())


async def list_overflow_budget_ids_for_categories(
    session: AsyncSession, *, category_ids: set[UUID], account_id: UUID
) -> list[UUID]:
    """Active budgets CONCERNED by a category of `category_ids` (the budget's category
    is an ancestor-or-self) AND eligible for `account_id` (S11.4 P11.4.4).

    Over-resolution is safe (gabarit `_concerned_budgets`): this only WIDENS the set
    to recompute — each tx re-resolves its own most-specific budget via the
    materializer. Covers the ancestor-budget case (a tx in a sub-category also
    consumes the parent budget ⇒ the parent's neighbours must be recomputed). `[]`
    if `category_ids` is empty. REUSES the ancestor walk-up of `_concerned_budgets`
    (no second CTE), adding only the `_eligible_account_ids` filter. Read-only.

    The `_concerned_budgets` import is intra-`budget` (not constrained by
    import-linter, whose contracts are cross-module) and done lazily here to avoid
    the `consumption ↔ threshold_detector` import cycle (`threshold_detector`
    imports `compute_consumption` at module load).
    """
    if not category_ids:
        return []
    # Lazy + intra-module: top-level would cycle (`threshold_detector` imports
    # `compute_consumption` at load). Private reuse is deliberate (single source of
    # the ancestor walk-up, no second CTE — gabarit `_consumption_filters`).
    from backend.modules.budget.service.threshold_detector import (  # noqa: PLC0415
        _concerned_budgets,  # pyright: ignore[reportPrivateUsage]
    )

    budgets = await _concerned_budgets(session, category_ids)
    out: list[UUID] = []
    for budget in budgets:
        if account_id in await _eligible_account_ids(session, budget):
            out.append(budget.id)
    return out


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
