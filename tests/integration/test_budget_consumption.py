"""Integration tests for `budget.service.consumption.compute_consumption` (S08.2, P08.2.2).

The aggregation core of E08, driven against a real Postgres so every filter
fires end to end: the recursive-CTE category subtree, the period window, the
`confirmed`-only state filter, the `force_full_debt` exclusion, the contributor
(account-eligibility) filter and the currency match.

Seeds follow the **canonical expense form** (E15 §P15.5.2, D4): a transaction is
an account leg (`category_id = NULL`, `−M`) plus a category leg
(`category_id = C`, `+M`). Only the category leg carries `category_id`, so the
`category_id ∈ subtree` filter captures exactly the spent amount — no double
counting. The `transactions`/`splits` ORM models are imported **only in the
test** (tests are outside the import-linter root package); the service itself
reads them via SQLAlchemy Core (`transactions ⊥ budget`, contract 1).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.modules.accounts.models import AccountMember
from backend.modules.budget.models import Budget, BudgetContributor, Category
from backend.modules.budget.service.consumption import compute_consumption, resolve_overflow_context
from backend.modules.transactions.models import Split, Transaction

FactoryBundle = Callable[[], Awaitable[tuple[type, type, type]]]

# A monthly budget anchored on the 1st; `as_of` lands mid-window unless a test
# overrides it. Window = [2026-06-01, 2026-07-01).
_PERIOD_START = date(2026, 6, 1)
_AS_OF = date(2026, 6, 15)
_IN_WINDOW = date(2026, 6, 10)


def _add_expense(  # noqa: PLR0913 — helper paramétrable de seed (scénarios variés)
    session: Session,
    *,
    account_id: UUID,
    category_id: UUID | None,
    amount: int,
    created_by: UUID,
    on: date = _IN_WINDOW,
    state: str = "confirmed",
    override: str = "default",
    currency: str = "EUR",
) -> UUID:
    """Persist a canonical expense (account leg + category leg). Returns the tx id.

    The account leg always carries `category_id = NULL` (never counted); only
    the category leg is tagged with `category_id` and counted. `currency`
    applies to the **category** leg (the one the budget sums); the account leg
    stays EUR so a currency-mismatch test isolates the category leg.
    """
    tx = Transaction(
        account_id=account_id,
        date=on,
        state=state,
        created_by=created_by,
        debt_generation_override=override,
    )
    session.add(tx)
    session.flush()
    session.add(
        Split(
            transaction_id=tx.id,
            account_id=account_id,
            category_id=None,
            amount_cents=-amount,
            currency="EUR",
        )
    )
    session.add(
        Split(
            transaction_id=tx.id,
            account_id=account_id,
            category_id=category_id,
            amount_cents=amount,
            currency=currency,
        )
    )
    session.flush()
    return tx.id


def _make_budget(  # noqa: PLR0913 — helper paramétrable de seed (scope/contrib/montant)
    session: Session,
    *,
    category_id: UUID,
    created_by: UUID,
    scope: str = "personal",
    amount_cents: int = 40000,
    contributor_ids: tuple[UUID, ...] = (),
) -> UUID:
    """Persist a `Budget` (+ its contributors). Returns the budget id."""
    budget = Budget(
        category_id=category_id,
        period_kind="monthly",
        period_start=_PERIOD_START,
        amount_cents=amount_cents,
        currency="EUR",
        scope=scope,
        created_by=created_by,
    )
    session.add(budget)
    session.flush()
    for uid in contributor_ids:
        session.add(BudgetContributor(budget_id=budget.id, user_id=uid))
    session.flush()
    return budget.id


# ---------------------------------------------------------------------------
# Subtree aggregation
# ---------------------------------------------------------------------------


async def test_category_without_children(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> UUID:
        owner = user_factory(email="leaf@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        _add_expense(s, account_id=acc.id, category_id=cat.id, amount=5000, created_by=owner.id)
        return _make_budget(s, category_id=cat.id, created_by=owner.id)

    budget_id = await household_singleton.run_sync(_seed)

    c = await compute_consumption(household_singleton, budget_id=budget_id, as_of=_AS_OF)
    assert c is not None
    assert c.consumed_cents == 5000
    assert c.splits_count == 1
    assert c.remaining_cents == 35000


async def test_aggregates_full_subtree(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # Budget sur parent P ; dépenses sur P, enfant C1, petit-enfant C2 (≥2 niveaux).
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> UUID:
        owner = user_factory(email="tree@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        p = Category(name="Maison")
        s.add(p)
        s.flush()
        c1 = Category(name="Énergie", parent_id=p.id)
        s.add(c1)
        s.flush()
        c2 = Category(name="Électricité", parent_id=c1.id)
        s.add(c2)
        s.flush()
        _add_expense(s, account_id=acc.id, category_id=p.id, amount=1000, created_by=owner.id)
        _add_expense(s, account_id=acc.id, category_id=c1.id, amount=2000, created_by=owner.id)
        _add_expense(s, account_id=acc.id, category_id=c2.id, amount=3000, created_by=owner.id)
        return _make_budget(s, category_id=p.id, created_by=owner.id)

    budget_id = await household_singleton.run_sync(_seed)

    c = await compute_consumption(household_singleton, budget_id=budget_id, as_of=_AS_OF)
    assert c is not None
    assert c.consumed_cents == 6000
    assert c.splits_count == 3


async def test_sibling_subtree_not_counted(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # Une dépense sur une catégorie sœur (hors sous-arbre) n'est pas comptée.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> UUID:
        owner = user_factory(email="sib@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        budget_cat = Category(name="Budgétée")
        sibling = Category(name="Autre")
        s.add_all([budget_cat, sibling])
        s.flush()
        _add_expense(
            s, account_id=acc.id, category_id=budget_cat.id, amount=1000, created_by=owner.id
        )
        _add_expense(s, account_id=acc.id, category_id=sibling.id, amount=9999, created_by=owner.id)
        return _make_budget(s, category_id=budget_cat.id, created_by=owner.id)

    budget_id = await household_singleton.run_sync(_seed)

    c = await compute_consumption(household_singleton, budget_id=budget_id, as_of=_AS_OF)
    assert c is not None
    assert c.consumed_cents == 1000
    assert c.splits_count == 1


async def test_multi_split_only_matching_counted(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # Transaction à plusieurs legs catégorie dont UN SEUL ∈ sous-arbre.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> UUID:
        owner = user_factory(email="multi@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        budget_cat = Category(name="Budgétée")
        other = Category(name="Hors budget")
        s.add_all([budget_cat, other])
        s.flush()
        # Une transaction, deux legs catégorie (+ un leg compte) : seul le leg
        # `budget_cat` doit compter.
        tx = Transaction(account_id=acc.id, date=_IN_WINDOW, state="confirmed", created_by=owner.id)
        s.add(tx)
        s.flush()
        s.add_all(
            [
                Split(
                    transaction_id=tx.id,
                    account_id=acc.id,
                    category_id=None,
                    amount_cents=-5000,
                    currency="EUR",
                ),
                Split(
                    transaction_id=tx.id,
                    account_id=acc.id,
                    category_id=budget_cat.id,
                    amount_cents=2000,
                    currency="EUR",
                ),
                Split(
                    transaction_id=tx.id,
                    account_id=acc.id,
                    category_id=other.id,
                    amount_cents=3000,
                    currency="EUR",
                ),
            ]
        )
        s.flush()
        return _make_budget(s, category_id=budget_cat.id, created_by=owner.id)

    budget_id = await household_singleton.run_sync(_seed)

    c = await compute_consumption(household_singleton, budget_id=budget_id, as_of=_AS_OF)
    assert c is not None
    assert c.consumed_cents == 2000
    assert c.splits_count == 1


async def test_account_leg_not_double_counted(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # Le leg compte (category_id=NULL) n'est pas compté → consumed == +M, pas 0 ni 2M.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> UUID:
        owner = user_factory(email="legs@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        _add_expense(s, account_id=acc.id, category_id=cat.id, amount=7000, created_by=owner.id)
        return _make_budget(s, category_id=cat.id, created_by=owner.id)

    budget_id = await household_singleton.run_sync(_seed)

    c = await compute_consumption(household_singleton, budget_id=budget_id, as_of=_AS_OF)
    assert c is not None
    assert c.consumed_cents == 7000


# ---------------------------------------------------------------------------
# Period window
# ---------------------------------------------------------------------------


async def test_split_outside_window_ignored(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> UUID:
        owner = user_factory(email="window@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        # In window (juin), counted.
        _add_expense(
            s,
            account_id=acc.id,
            category_id=cat.id,
            amount=1000,
            created_by=owner.id,
            on=date(2026, 6, 10),
        )
        # Previous month + next month, ignored.
        _add_expense(
            s,
            account_id=acc.id,
            category_id=cat.id,
            amount=5000,
            created_by=owner.id,
            on=date(2026, 5, 31),
        )
        _add_expense(
            s,
            account_id=acc.id,
            category_id=cat.id,
            amount=8000,
            created_by=owner.id,
            on=date(2026, 7, 1),
        )
        return _make_budget(s, category_id=cat.id, created_by=owner.id)

    budget_id = await household_singleton.run_sync(_seed)

    c = await compute_consumption(household_singleton, budget_id=budget_id, as_of=_AS_OF)
    assert c is not None
    assert c.consumed_cents == 1000
    assert c.splits_count == 1


async def test_window_boundaries_half_open(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # date == start comptée ; date == end NON comptée (demi-ouvert [start, end)).
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> UUID:
        owner = user_factory(email="bounds@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        _add_expense(
            s,
            account_id=acc.id,
            category_id=cat.id,
            amount=1000,
            created_by=owner.id,
            on=date(2026, 6, 1),
        )  # == start
        _add_expense(
            s,
            account_id=acc.id,
            category_id=cat.id,
            amount=5000,
            created_by=owner.id,
            on=date(2026, 7, 1),
        )  # == end (exclusive)
        return _make_budget(s, category_id=cat.id, created_by=owner.id)

    budget_id = await household_singleton.run_sync(_seed)

    c = await compute_consumption(household_singleton, budget_id=budget_id, as_of=_AS_OF)
    assert c is not None
    assert c.consumed_cents == 1000
    assert c.splits_count == 1


# ---------------------------------------------------------------------------
# State + override filters
# ---------------------------------------------------------------------------


async def test_non_confirmed_ignored(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> UUID:
        owner = user_factory(email="state@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        _add_expense(
            s,
            account_id=acc.id,
            category_id=cat.id,
            amount=1000,
            created_by=owner.id,
            state="confirmed",
        )
        for bad in ("draft", "planned", "void"):
            _add_expense(
                s,
                account_id=acc.id,
                category_id=cat.id,
                amount=9000,
                created_by=owner.id,
                state=bad,
            )
        return _make_budget(s, category_id=cat.id, created_by=owner.id)

    budget_id = await household_singleton.run_sync(_seed)

    c = await compute_consumption(household_singleton, budget_id=budget_id, as_of=_AS_OF)
    assert c is not None
    assert c.consumed_cents == 1000
    assert c.splits_count == 1


async def test_force_full_debt_excluded(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # force_full_debt exclu ; force_no_debt et default comptés.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> UUID:
        owner = user_factory(email="override@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        _add_expense(
            s,
            account_id=acc.id,
            category_id=cat.id,
            amount=1000,
            created_by=owner.id,
            override="default",
        )
        _add_expense(
            s,
            account_id=acc.id,
            category_id=cat.id,
            amount=2000,
            created_by=owner.id,
            override="force_no_debt",
        )
        _add_expense(
            s,
            account_id=acc.id,
            category_id=cat.id,
            amount=9999,
            created_by=owner.id,
            override="force_full_debt",
        )
        return _make_budget(s, category_id=cat.id, created_by=owner.id)

    budget_id = await household_singleton.run_sync(_seed)

    c = await compute_consumption(household_singleton, budget_id=budget_id, as_of=_AS_OF)
    assert c is not None
    assert c.consumed_cents == 3000
    assert c.splits_count == 2


# ---------------------------------------------------------------------------
# Contributor (account-eligibility) filter
# ---------------------------------------------------------------------------


async def test_personal_scope_owner_accounts_only(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # personal : dépense sur compte perso de l'owner comptée ; sur compte commun non.
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(s: Session) -> UUID:
        owner = user_factory(email="pers-owner@example.com")
        other = user_factory(email="pers-other@example.com")
        perso = account_factory(owner_id=owner.id, name="Perso")
        shared = account_factory(owner_id=None, name="Commun")
        member_factory(account_id=shared.id, user_id=owner.id)
        member_factory(account_id=shared.id, user_id=other.id)
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        _add_expense(s, account_id=perso.id, category_id=cat.id, amount=1000, created_by=owner.id)
        _add_expense(s, account_id=shared.id, category_id=cat.id, amount=9000, created_by=owner.id)
        return _make_budget(
            s,
            category_id=cat.id,
            created_by=owner.id,
            scope="personal",
            contributor_ids=(owner.id,),
        )

    budget_id = await household_singleton.run_sync(_seed)

    c = await compute_consumption(household_singleton, budget_id=budget_id, as_of=_AS_OF)
    assert c is not None
    assert c.consumed_cents == 1000
    assert c.splits_count == 1


async def test_shared_scope_contributor_accounts(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # shared {A,B} : commun {A,B} compté ; commun {A,B,C} non (D7) ; perso non.
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(s: Session) -> UUID:
        a = user_factory(email="sh-a@example.com")
        b = user_factory(email="sh-b@example.com")
        c = user_factory(email="sh-c@example.com")
        ab = account_factory(owner_id=None, name="AB")
        member_factory(account_id=ab.id, user_id=a.id)
        member_factory(account_id=ab.id, user_id=b.id)
        abc = account_factory(owner_id=None, name="ABC")
        member_factory(account_id=abc.id, user_id=a.id, default_share_ratio="0.3333")
        member_factory(account_id=abc.id, user_id=b.id, default_share_ratio="0.3333")
        member_factory(account_id=abc.id, user_id=c.id, default_share_ratio="0.3334")
        perso = account_factory(owner_id=a.id, name="A perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        _add_expense(s, account_id=ab.id, category_id=cat.id, amount=1000, created_by=a.id)
        _add_expense(s, account_id=abc.id, category_id=cat.id, amount=8000, created_by=a.id)
        _add_expense(s, account_id=perso.id, category_id=cat.id, amount=9000, created_by=a.id)
        return _make_budget(
            s, category_id=cat.id, created_by=a.id, scope="shared", contributor_ids=(a.id, b.id)
        )

    budget_id = await household_singleton.run_sync(_seed)

    c = await compute_consumption(household_singleton, budget_id=budget_id, as_of=_AS_OF)
    assert c is not None
    assert c.consumed_cents == 1000
    assert c.splits_count == 1


# ---------------------------------------------------------------------------
# Sign, currency, edge cases
# ---------------------------------------------------------------------------


async def test_refund_reduces_consumption(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # Un leg catégorie négatif (remboursement) réduit naturellement la consommation.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> UUID:
        owner = user_factory(email="refund@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        _add_expense(s, account_id=acc.id, category_id=cat.id, amount=5000, created_by=owner.id)
        _add_expense(s, account_id=acc.id, category_id=cat.id, amount=-2000, created_by=owner.id)
        return _make_budget(s, category_id=cat.id, created_by=owner.id)

    budget_id = await household_singleton.run_sync(_seed)

    c = await compute_consumption(household_singleton, budget_id=budget_id, as_of=_AS_OF)
    assert c is not None
    assert c.consumed_cents == 3000
    assert c.splits_count == 2


async def test_currency_mismatch_split_ignored(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> UUID:
        owner = user_factory(email="ccy@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        _add_expense(s, account_id=acc.id, category_id=cat.id, amount=1000, created_by=owner.id)
        _add_expense(
            s,
            account_id=acc.id,
            category_id=cat.id,
            amount=9000,
            created_by=owner.id,
            currency="USD",
        )
        return _make_budget(s, category_id=cat.id, created_by=owner.id)

    budget_id = await household_singleton.run_sync(_seed)

    c = await compute_consumption(household_singleton, budget_id=budget_id, as_of=_AS_OF)
    assert c is not None
    assert c.consumed_cents == 1000
    assert c.splits_count == 1


async def test_unknown_budget_returns_none(household_singleton: AsyncSession) -> None:
    assert await compute_consumption(household_singleton, budget_id=uuid4(), as_of=_AS_OF) is None


async def test_unexpected_scope_fail_closed(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # Scope inattendu (ni personal ni shared) → fail-closed : aucun compte
    # éligible → consommation 0, jamais une fuite cross-scope (D7).
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="scope@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        _add_expense(s, account_id=acc.id, category_id=cat.id, amount=5000, created_by=owner.id)
        budget_id = _make_budget(s, category_id=cat.id, created_by=owner.id, scope="weird")
        return budget_id, cat.id

    budget_id, cat_id = await household_singleton.run_sync(_seed)

    # La dépense existe bien en base : le 0 vient du fail-closed (scope inconnu →
    # aucun compte éligible), pas d'une base vide.
    category_leg_count = await household_singleton.scalar(
        select(func.count()).select_from(Split).where(Split.category_id == cat_id)
    )
    assert category_leg_count == 1

    c = await compute_consumption(household_singleton, budget_id=budget_id, as_of=_AS_OF)
    assert c is not None
    assert c.consumed_cents == 0
    assert c.splits_count == 0


async def test_empty_subtree_or_no_expense_zero(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> UUID:
        owner = user_factory(email="zero@example.com")
        account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Vide")
        s.add(cat)
        s.flush()
        return _make_budget(s, category_id=cat.id, created_by=owner.id)

    budget_id = await household_singleton.run_sync(_seed)

    c = await compute_consumption(household_singleton, budget_id=budget_id, as_of=_AS_OF)
    assert c is not None
    assert c.consumed_cents == 0
    assert c.splits_count == 0
    assert c.remaining_cents == 40000


async def test_read_only_no_mutation(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # compute_consumption ne crée/supprime aucune ligne (lecture seule, ADR 0015).
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> UUID:
        owner = user_factory(email="ro@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        _add_expense(s, account_id=acc.id, category_id=cat.id, amount=1000, created_by=owner.id)
        return _make_budget(s, category_id=cat.id, created_by=owner.id)

    budget_id = await household_singleton.run_sync(_seed)

    async def _count(model: type) -> int:
        return (
            await household_singleton.execute(select(func.count()).select_from(model))
        ).scalar_one()

    async def _counts() -> tuple[int, int, int]:
        return await _count(Transaction), await _count(Split), await _count(Budget)

    before = await _counts()
    await compute_consumption(household_singleton, budget_id=budget_id, as_of=_AS_OF)
    after = await _counts()
    assert before == after


# ---------------------------------------------------------------------------
# Ordered window `before` (overflow F10, S11.3 D7) + most-specific tie-break (D8)
# ---------------------------------------------------------------------------


async def test_before_excludes_boundary_and_orders_by_id(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # D7: `before=(date, id)` bounds consumption to txs STRICTLY before in the total
    # order `(date, id)`. Pins three things the materializer's conservation relies on:
    # (a) a tx exactly AT the bound is EXCLUDED (strict `<`, NOT `<=`); (b) two txs
    # sharing a date are split by `id`; (c) `before=None` (default) counts the full
    # period (S08 callers non-regression). A flip to `<=` would break (a) silently.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID, UUID]:
        owner = user_factory(email=f"win-{uuid4().hex[:8]}@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        _add_expense(  # earlier date — always before the same-date pair
            s,
            account_id=acc.id,
            category_id=cat.id,
            amount=1000,
            created_by=owner.id,
            on=date(2026, 6, 5),
        )
        same1 = _add_expense(
            s,
            account_id=acc.id,
            category_id=cat.id,
            amount=2000,
            created_by=owner.id,
            on=_IN_WINDOW,
        )
        same2 = _add_expense(
            s,
            account_id=acc.id,
            category_id=cat.id,
            amount=4000,
            created_by=owner.id,
            on=_IN_WINDOW,
        )
        budget_id = _make_budget(s, category_id=cat.id, created_by=owner.id, amount_cents=40000)
        return budget_id, same1, same2

    budget_id, same1, same2 = await household_singleton.run_sync(_seed)
    # Order the two same-date ids so assertions are deterministic regardless of UUIDs.
    lo, hi = sorted((same1, same2))
    amount_of = {same1: 2000, same2: 4000}

    # (c) Full period (no bound): 1000 + 2000 + 4000.
    full = await compute_consumption(household_singleton, budget_id=budget_id, as_of=_AS_OF)
    assert full is not None and full.consumed_cents == 7000

    # (a) + (b) bound on `hi`: excludes `hi` itself (strict), keeps earlier + `lo`.
    bounded = await compute_consumption(
        household_singleton, budget_id=budget_id, as_of=_AS_OF, before=(_IN_WINDOW, hi)
    )
    assert bounded is not None and bounded.consumed_cents == 1000 + amount_of[lo]

    # (b) bound on `lo`: excludes both same-date txs (lo at bound, hi after), keeps earlier.
    only_earlier = await compute_consumption(
        household_singleton, budget_id=budget_id, as_of=_AS_OF, before=(_IN_WINDOW, lo)
    )
    assert only_earlier is not None and only_earlier.consumed_cents == 1000


async def test_resolve_overflow_context_tie_break_created_at(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # D8: two active budgets on the SAME category (same walk-up depth = most specific)
    # are ordered by `(created_at, id)` → the earlier-created one is chosen
    # deterministically. Guards the tie-break that V1 mono-catégorie makes rare.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID, UUID]:
        alice = user_factory(email=f"tb-{uuid4().hex[:8]}@example.com")
        acc = account_factory(owner_id=None, name="Commun")
        s.add(AccountMember(account_id=acc.id, user_id=alice.id, default_share_ratio=Decimal("1")))
        s.flush()
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        b_old = Budget(
            category_id=cat.id,
            period_kind="monthly",
            period_start=_PERIOD_START,
            amount_cents=5000,
            currency="EUR",
            scope="shared",
            created_by=alice.id,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        b_new = Budget(
            category_id=cat.id,
            period_kind="monthly",
            period_start=_PERIOD_START,
            amount_cents=9999,
            currency="EUR",
            scope="shared",
            created_by=alice.id,
            created_at=datetime(2026, 5, 1, tzinfo=UTC),
        )
        s.add_all([b_old, b_new])
        s.flush()
        for b in (b_old, b_new):
            s.add(BudgetContributor(budget_id=b.id, user_id=alice.id))
        s.flush()
        return acc.id, cat.id, b_old.id

    account_id, cat_id, b_old_id = await household_singleton.run_sync(_seed)
    ctx = await resolve_overflow_context(
        household_singleton,
        category_ids={cat_id},
        account_id=account_id,
        as_of=_AS_OF,
        before=(_AS_OF, uuid4()),
    )
    assert ctx is not None
    assert ctx.budget_id == b_old_id  # earlier created_at wins the tie-break
    assert ctx.remaining_before_cents == 5000  # b_old's amount, no prior consumption
