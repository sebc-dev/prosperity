"""Budget write service (S08.4): create / update / archive a budget.

The mutation half of the budget CRUD, split from the read model (`budgets.py`,
which holds `list_active_budgets_for_user` + `get_visible_budget`) the way
`transactions` splits `lifecycle` from `queries`. Every writer is **flush-only**
— `get_db` owns the transaction boundary (ADR 0015); this is an ordinary
business service, not a security-critical side effect, so the commit stays with
the request.

Two-stage contributor validation (CONTEXT.md §Budget):

* the pure count/shape invariant (`domain.validate_contributor_count`):
  `personal ⇒ {owner}`, `shared ⇒ ≥ 2` distinct;
* a DB-backed eligibility check for `shared`: every contributor must be a member
  of *some* common account (`accounts.public.shared_account_member_ids`,
  predicate "member-of-any" — Note implémenteur #128). This is deliberately
  laxer than the consumption filter's "subset-of-members" predicate (D4): a
  `{A,B}` budget validated against a `{A,B,C}` common account simply consumes 0,
  a divergence pinned by a cross-invariant test.

`currency` is never client-supplied: `create_budget` derives it from the
household base currency (D6, mono-currency V1) so it always matches the splits
the consumption filter sums. `scope`/`category_id`/`period_*` are frozen after
creation (D7) — `update_budget` only touches `amount_cents`,
`carry_over_remainder` and the contributor set.

Internal to the budget module (no cross-module consumer → nothing in
`budget.public`). Imports `accounts.public` (below budget in the graph,
contract 1) for the household currency and the member set — both arcs are
already whitelisted second-hops in `2-budget` (D11).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.public import get_household, shared_account_member_ids
from backend.modules.budget.domain import BudgetContributorError, validate_contributor_count
from backend.modules.budget.events import BudgetCreatedEvent, BudgetUpdatedEvent
from backend.modules.budget.models import Budget, BudgetContributor
from backend.modules.budget.service.budgets import get_visible_budget
from backend.shared.events import dispatch


async def _assert_contributors_eligible(
    session: AsyncSession,
    *,
    scope: str,
    contributor_ids: Sequence[UUID],
    created_by: UUID,
) -> None:
    """Two-stage contributor validation; raises `BudgetContributorError` on failure.

    First the pure count/shape invariant, then — for `shared` only — the
    DB-backed "every contributor is a member of a common account" check
    (member-of-any, D4). The pure check runs first so a malformed `personal`
    list never hits the DB.
    """
    validate_contributor_count(scope=scope, contributor_ids=contributor_ids, created_by=created_by)
    if scope == "shared":
        members = await shared_account_member_ids(session)
        if not set(contributor_ids) <= members:
            raise BudgetContributorError("a contributor is not a member of any common account")


async def create_budget(  # noqa: PLR0913 — flat keyword surface mirroring the schema
    session: AsyncSession,
    *,
    category_id: UUID,
    period_kind: str,
    period_start: date,
    amount_cents: int,
    scope: str,
    carry_over_remainder: bool,
    contributor_ids: Sequence[UUID],
    created_by: UUID,
) -> Budget:
    """Crée le budget + ses `BudgetContributor`. `currency` dérivée du foyer (D6).

    Valide les contributeurs **avant** tout write. Une `category_id` inconnue
    déclenche une FK 23503 au flush → 422 mappé à la route (gabarit
    `create_category`). Flush-only (ADR 0015 : `get_db` commit).
    """
    await _assert_contributors_eligible(
        session, scope=scope, contributor_ids=contributor_ids, created_by=created_by
    )
    household = await get_household(session)
    budget = Budget(
        category_id=category_id,
        period_kind=period_kind,
        period_start=period_start,
        amount_cents=amount_cents,
        currency=household.base_currency,
        scope=scope,
        created_by=created_by,
        carry_over_remainder=carry_over_remainder,
    )
    session.add(budget)
    await session.flush()  # surface l'id ; FK 23503 si category_id inconnu
    session.add_all(BudgetContributor(budget_id=budget.id, user_id=uid) for uid in contributor_ids)
    await session.flush()
    # S11.4 : un budget qui apparaît re-matérialise l'overflow des tx passées qu'il
    # couvre (abonné `debts` async ⇒ `dispatch`, jamais `publish`). Après le 2e flush
    # (id + contributeurs visibles). Flush-only conservé (ADR 0015 : `dispatch` ne
    # commit pas ; le handler tourne dans la transaction du request).
    await dispatch(
        session,
        BudgetCreatedEvent(
            budget_id=budget.id, category_id=budget.category_id, currency=budget.currency
        ),
    )
    return budget


async def update_budget(
    session: AsyncSession,
    *,
    budget_id: UUID,
    user_id: UUID,
    fields: dict[str, object],
    contributor_ids: list[UUID] | None,
) -> Budget | None:
    """Édite amount/carry_over (+ remplace les contributeurs si fournis). `None`
    si non visible (→ 404). Re-valide l'invariant contributeurs (D8). Flush-only.

    ORDRE security-relevant : la visibilité (`get_visible_budget`) est vérifiée
    **en premier** — un non-contributeur reçoit 404 AVANT toute validation des
    contributeurs (sinon un body invalide fuiterait un 422 révélant l'existence
    du budget, D3). Le remplacement des contributeurs est un `DELETE all +
    INSERT` dans la même transaction : l'invariant re-validé garantit qu'un
    `shared` ne tombe pas sous 2 et qu'un `personal` reste `{owner}`. L'audit du
    changement de contributeurs est hors scope S08.4 (§7).
    """
    budget = await get_visible_budget(session, budget_id=budget_id, user_id=user_id)
    if budget is None:
        return None
    if contributor_ids is not None:
        await _assert_contributors_eligible(
            session,
            scope=budget.scope,
            contributor_ids=contributor_ids,
            created_by=budget.created_by,
        )
        await session.execute(
            delete(BudgetContributor).where(BudgetContributor.budget_id == budget.id)
        )
        session.add_all(
            BudgetContributor(budget_id=budget.id, user_id=uid) for uid in contributor_ids
        )
    for key, value in fields.items():
        setattr(budget, key, value)
    await session.flush()
    # S11.4 : le restant (montant) ou l'éligibilité (contributeurs) a pu bouger ⇒
    # recalcul overflow des tx couvertes (abonné `debts` async ⇒ `dispatch`). Idempotent
    # côté handler ⇒ coût nul si rien de matériel n'a changé.
    await dispatch(
        session,
        BudgetUpdatedEvent(
            budget_id=budget.id, category_id=budget.category_id, currency=budget.currency
        ),
    )
    return budget


async def archive_budget(session: AsyncSession, *, budget_id: UUID, user_id: UUID) -> bool:
    """Soft-delete (set `archived_at`), jamais hard-delete. `False` si non visible
    ou déjà archivé → 404 (gabarit `archive_category`/`accounts.archive`).

    `get_visible_budget` exclut déjà les budgets archivés, donc un second archive
    ne trouve rien → `False` → 404 (idempotent au sens « pas de corruption / ligne
    préservée », pas un 204-replay). Les contributeurs survivent (aucune ligne
    supprimée). Flush-only (ADR 0015).
    """
    budget = await get_visible_budget(session, budget_id=budget_id, user_id=user_id)
    if budget is None:
        return False
    budget.archived_at = datetime.now(UTC)
    await session.flush()
    # S11.4 (D3) : archiver retire la couverture ⇒ les tx couvertes re-résolvent
    # « sans budget » (base = M, dette plus élevée) — symétrique à la création. La
    # projection `Debt` (ADR 0002) doit refléter l'état courant ⇒ on émet aussi. Le
    # handler lit le budget PAR id (`session.get`), donc fonctionne même archivé.
    await dispatch(
        session,
        BudgetUpdatedEvent(
            budget_id=budget.id, category_id=budget.category_id, currency=budget.currency
        ),
    )
    return True
