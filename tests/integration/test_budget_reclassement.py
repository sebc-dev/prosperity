"""Integration tests for the budget reclassement F10 (E11 / S11.4).

Reclassement = creating, updating or archiving a budget **after the fact** must
re-materialise the overflow of the past transactions it covers, REUSING the
idempotent S11.3 path (`_materialize_for_tx`), never a second voie. Covers:

* P11.4.1 — `BudgetCreatedEvent` / `BudgetUpdatedEvent` emitted by `budget_crud`,
  the `recompute_overflow_on_budget_event` handler, the `_consumption_filters`-based
  enumeration (whole history, no window bound), idempotence, `share_request`
  isolation, `force_full_debt` exclusion.
* P11.4.2 — the server-only audit trace `debts_recomputed_on_budget_event`
  (timestamp via logging, `budget_id`, count) WITHOUT PII.

Wiring (gabarit `test_overflow_materializer`): the `subscribe_async` câblage lives
in `main.py`'s `lifespan`; this tier calls the services directly (no lifespan), so
the autouse `_wire_reclass` fixture `clear_subscribers()` then re-subscribes the
overflow materializer on confirm AND the reclassement handler on the budget events.

Seeds use the **canonical expense form B** (ADR 0017): a funding leg
(`category_id=NULL`, `-M`) + a classification leg (`category_id=C`, `+M`) on the
same shared account. Overflow debts orient *other members → payer* (`tx.created_by`).
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import backend.modules.debts.service.overflow_materializer as _materializer_module
from backend.config import get_settings
from backend.main import (  # composition-root wiring under test
    _register_event_subscribers,  # pyright: ignore[reportPrivateUsage]
)
from backend.modules.accounts.models import HOUSEHOLD_SINGLETON_UUID, AccountMember, Household
from backend.modules.accounts.service.household import invalidate_household_cache
from backend.modules.auth.service.jwt import issue_access_token
from backend.modules.budget.events import BudgetCreatedEvent, BudgetUpdatedEvent
from backend.modules.budget.models import Budget, BudgetContributor, Category
from backend.modules.budget.service.budget_crud import (
    archive_budget,
    create_budget,
    update_budget,
)
from backend.modules.budget.service.consumption import compute_consumption
from backend.modules.debts.models import Debt
from backend.modules.debts.service.overflow_materializer import (
    materialize_overflow,
    recompute_overflow_for_budget,
    recompute_overflow_on_budget_event,
    rematerialize_overflow_on_edit,
)
from backend.modules.transactions.events import (
    TransactionConfirmedEvent,
    TransactionEditableFieldsChangedEvent,
)
from backend.modules.transactions.models import Split, Transaction
from backend.modules.transactions.service.lifecycle import (
    transition_to_confirmed,
    update_editable_fields,
)
from backend.shared.events import clear_subscribers, subscribe, subscribe_async

FactoryBundle = Callable[[], Awaitable[tuple[type, type, type]]]

_OVERFLOW = "shared_account_overflow"
_TODAY = dt.date(2026, 6, 15)
_PERIOD_START = dt.date(2026, 6, 1)
_settings = get_settings()


def _bearer(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


@pytest.fixture(autouse=True)
def _wire_reclass() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Re-wire the overflow materializer (confirm) AND the reclassement handler
    (budget created/updated) on the bus — the lifespan câblage does not run in this
    tier. Cleared on teardown (process-global state)."""
    clear_subscribers()
    subscribe_async(TransactionConfirmedEvent, materialize_overflow)
    subscribe_async(BudgetCreatedEvent, recompute_overflow_on_budget_event)
    subscribe_async(BudgetUpdatedEvent, recompute_overflow_on_budget_event)
    subscribe_async(TransactionEditableFieldsChangedEvent, rematerialize_overflow_on_edit)
    yield
    clear_subscribers()


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _initialised_household(  # pyright: ignore[reportUnusedFunction]
    household_singleton: AsyncSession,
) -> AsyncIterator[None]:
    """Mark the singleton household `initialized_at` so `create_budget` resolves
    `get_household` (it raises until `/setup` has run, S03.2), and keep the
    process-local household cache cold around each test."""
    invalidate_household_cache()

    def _init(s: Session) -> None:
        household = s.get(Household, HOUSEHOLD_SINGLETON_UUID)
        assert household is not None
        household.initialized_at = dt.datetime.now(tz=dt.UTC)

    await household_singleton.run_sync(_init)
    yield
    invalidate_household_cache()


# ---------------------------------------------------------------------------
# Seed helpers (run inside `run_sync` on the test's sync Session)
# ---------------------------------------------------------------------------


@dataclass
class Scenario:
    payer: UUID  # Alice — tx.created_by → creditor
    members: dict[str, UUID]
    account: UUID
    category: UUID
    tx: UUID


def _add_expense(  # noqa: PLR0913 — keyword-only seed knobs
    s: Session,
    *,
    account_id: UUID,
    category_id: UUID,
    amount: int,
    created_by: UUID,
    state: str = "planned",
    override: str = "default",
    on: dt.date = _TODAY,
) -> UUID:
    """Persist a canonical form-B expense (funding NULL leg + classification leg)."""
    tx = Transaction(
        account_id=account_id,
        date=on,
        state=state,
        created_by=created_by,
        debt_generation_override=override,
    )
    s.add(tx)
    s.flush()
    s.add_all(
        [
            Split(
                transaction_id=tx.id,
                account_id=account_id,
                category_id=None,
                amount_cents=-amount,
                currency="EUR",
            ),
            Split(
                transaction_id=tx.id,
                account_id=account_id,
                category_id=category_id,
                amount_cents=amount,
                currency="EUR",
            ),
        ]
    )
    s.flush()
    return tx.id


def _make_budget_row(  # noqa: PLR0913 — keyword-only seed knobs
    s: Session,
    *,
    category_id: UUID,
    created_by: UUID,
    amount_cents: int,
    scope: str = "shared",
    contributor_ids: tuple[UUID, ...] = (),
) -> UUID:
    """Directly persist a budget row (bypasses the dispatch — used to seed an
    EXISTING budget before exercising `update`/`archive`)."""
    budget = Budget(
        category_id=category_id,
        period_kind="monthly",
        period_start=_PERIOD_START,
        amount_cents=amount_cents,
        currency="EUR",
        scope=scope,
        created_by=created_by,
    )
    s.add(budget)
    s.flush()
    for uid in contributor_ids:
        s.add(BudgetContributor(budget_id=budget.id, user_id=uid))
    s.flush()
    return budget.id


async def _seed(  # noqa: PLR0913 — keyword-only scenario knobs
    session: AsyncSession,
    factories: FactoryBundle,
    *,
    member_ratios: dict[str, Decimal],
    amount: int,
    override: str = "default",
    on: dt.date = _TODAY,
) -> Scenario:
    """Seed Alice (payer) + other members of a shared account, a category and ONE
    `planned` expense (no budget). Confirm it separately to materialise overflow."""
    user_factory, account_factory, _ = await factories()

    def _do(s: Session) -> Scenario:
        members = {
            name: user_factory(email=f"{name}-{uuid4().hex[:8]}@example.com").id
            for name in member_ratios
        }
        payer = members["alice"]
        account = account_factory(owner_id=None, name="Commun")
        for name, ratio in member_ratios.items():
            s.add(
                AccountMember(
                    account_id=account.id, user_id=members[name], default_share_ratio=ratio
                )
            )
        s.flush()
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        tx_id = _add_expense(
            s,
            account_id=account.id,
            category_id=cat.id,
            amount=amount,
            created_by=payer,
            override=override,
            on=on,
        )
        return Scenario(payer, members, account.id, cat.id, tx_id)

    return await session.run_sync(_do)


async def _overflow_debts(session: AsyncSession, tx_id: UUID) -> list[Debt]:
    rows = await session.execute(
        select(Debt)
        .where(Debt.source_transaction_id == tx_id, Debt.origin == _OVERFLOW)
        .order_by(Debt.from_user_id)
    )
    return list(rows.scalars().all())


async def _overflow_by_debtor(session: AsyncSession, tx_id: UUID) -> dict[UUID, int]:
    return {d.from_user_id: d.amount_cents for d in await _overflow_debts(session, tx_id)}


async def _create_covering_budget(
    session: AsyncSession, sc: Scenario, *, amount_cents: int
) -> UUID:
    """Create a `shared` budget covering `sc.category` via the REAL `create_budget`
    flow (which dispatches `BudgetCreatedEvent` → reclassement handler)."""
    budget = await create_budget(
        session,
        category_id=sc.category,
        period_kind="monthly",
        period_start=_PERIOD_START,
        amount_cents=amount_cents,
        scope="shared",
        carry_over_remainder=False,
        contributor_ids=list(sc.members.values()),
        created_by=sc.payer,
    )
    return budget.id


# ---------------------------------------------------------------------------
# P11.4.1 — create / update / archive a budget recomputes overflow
# ---------------------------------------------------------------------------


async def test_create_covering_budget_removes_debt(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # AC headline: a `default` tx on a shared account WITHOUT a budget → overflow
    # base = M; CREATE a covering budget (remaining ≥ M) → the debt is REMOVED
    # (recalculated to 0, the prune purges it). A recompute, NOT a hard delete.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    assert await _overflow_by_debtor(household_singleton, sc.tx) == {sc.members["bob"]: 5000}

    await _create_covering_budget(household_singleton, sc, amount_cents=50000)
    assert await _overflow_debts(household_singleton, sc.tx) == []


async def test_create_partial_budget_reduces_debt(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # A covering budget with a PARTIAL remaining R=30 against M=100 → overflow
    # recalculated to base = M − R = 70 → Bob (0.5) owes 35€.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    await _create_covering_budget(household_singleton, sc, amount_cents=3000)
    assert await _overflow_by_debtor(household_singleton, sc.tx) == {sc.members["bob"]: 3500}


async def test_update_amount_recomputes(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # An EXISTING budget too small leaves an overflow; raising `amount_cents` via
    # `update_budget` (→ BudgetUpdatedEvent) recomputes it to 0.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
    )
    budget_id = await household_singleton.run_sync(
        lambda s: _make_budget_row(
            s,
            category_id=sc.category,
            created_by=sc.payer,
            amount_cents=2000,
            contributor_ids=tuple(sc.members.values()),
        )
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    # M=100, remaining=20 → base 80 → Bob 40€.
    assert await _overflow_by_debtor(household_singleton, sc.tx) == {sc.members["bob"]: 4000}

    await update_budget(
        household_singleton,
        budget_id=budget_id,
        user_id=sc.payer,
        fields={"amount_cents": 50000},
        contributor_ids=None,
    )
    assert await _overflow_debts(household_singleton, sc.tx) == []


async def test_archive_budget_rematerialises(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # D3: a tx within the budget (no overflow) → ARCHIVE the budget (coverage lost)
    # → overflow re-materialised at base = M (symmetric to creation).
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
    )
    budget_id = await household_singleton.run_sync(
        lambda s: _make_budget_row(
            s,
            category_id=sc.category,
            created_by=sc.payer,
            amount_cents=50000,
            contributor_ids=tuple(sc.members.values()),
        )
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    assert await _overflow_debts(household_singleton, sc.tx) == []  # within budget

    await archive_budget(household_singleton, budget_id=budget_id, user_id=sc.payer)
    assert await _overflow_by_debtor(household_singleton, sc.tx) == {sc.members["bob"]: 5000}


async def test_idempotent_redispatch_budget_event(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # Re-dispatching the SAME BudgetCreatedEvent leaves the overflow debt set
    # identical (upsert + prune). Here both events recompute to the empty set.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    budget_id = await _create_covering_budget(household_singleton, sc, amount_cents=3000)
    first = await _overflow_by_debtor(household_singleton, sc.tx)
    await recompute_overflow_on_budget_event(
        household_singleton,
        BudgetCreatedEvent(budget_id=budget_id, category_id=sc.category, currency="EUR"),
    )
    assert (
        await _overflow_by_debtor(household_singleton, sc.tx) == first == {sc.members["bob"]: 3500}
    )


async def test_force_full_debt_excluded_from_enumeration(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # A `force_full_debt` tx is NOT enumerated (excluded by `_consumption_filters`)
    # AND its overflow (= full total) is unchanged by a budget creation.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
        override="force_full_debt",
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    assert await _overflow_by_debtor(household_singleton, sc.tx) == {sc.members["bob"]: 5000}

    budget_id = await _create_covering_budget(household_singleton, sc, amount_cents=50000)
    # Not enumerated → recompute count 0; overflow unchanged (budget ignored).
    assert await recompute_overflow_for_budget(household_singleton, budget_id=budget_id) == 0
    assert await _overflow_by_debtor(household_singleton, sc.tx) == {sc.members["bob"]: 5000}


async def test_share_request_debt_untouched_by_reclass(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # AC opposable: a personal_share_request debt on the same tx is NEVER touched
    # by the reclassement recompute (origin-exclusive writes).
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
    )
    bob = sc.members["bob"]

    def _add_sr(s: Session) -> UUID:
        d = Debt(
            from_user_id=bob,
            to_user_id=sc.payer,
            amount_cents=777,
            currency="EUR",
            account_id=sc.account,
            source_transaction_id=sc.tx,
            origin="personal_share_request",
        )
        s.add(d)
        s.flush()
        return d.id

    sr_id = await household_singleton.run_sync(_add_sr)
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    await _create_covering_budget(household_singleton, sc, amount_cents=50000)

    sr = (await household_singleton.execute(select(Debt).where(Debt.id == sr_id))).scalar_one()
    assert sr.amount_cents == 777 and sr.origin == "personal_share_request"
    assert await _overflow_debts(household_singleton, sc.tx) == []  # overflow recomputed away


async def test_create_personal_budget_no_overflow_on_shared_expense(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # A `personal` budget never covers a shared-account expense → its creation
    # enumerates zero shared txs (eligible accounts = owner's personal only).
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    before = await _overflow_by_debtor(household_singleton, sc.tx)

    budget = await create_budget(
        household_singleton,
        category_id=sc.category,
        period_kind="monthly",
        period_start=_PERIOD_START,
        amount_cents=50000,
        scope="personal",
        carry_over_remainder=False,
        contributor_ids=[sc.payer],
        created_by=sc.payer,
    )
    assert await recompute_overflow_for_budget(household_singleton, budget_id=budget.id) == 0
    assert (
        await _overflow_by_debtor(household_singleton, sc.tx) == before == {sc.members["bob"]: 5000}
    )


async def test_recompute_unknown_budget_returns_zero(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # A budget id that does not resolve → no enumeration, count 0 (no crash).
    assert await recompute_overflow_for_budget(household_singleton, budget_id=uuid4()) == 0


# ---------------------------------------------------------------------------
# P11.4.2 — audit trace (server-only, no PII)
# ---------------------------------------------------------------------------

_TRACE_LOGGER = "backend.modules.debts.service.overflow_materializer"


async def test_audit_trace_counts_recomputed_txs(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The trace carries the exact count of recomputed transactions (here 1).
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    budget_id = await household_singleton.run_sync(
        lambda s: _make_budget_row(
            s,
            category_id=sc.category,
            created_by=sc.payer,
            amount_cents=50000,
            contributor_ids=tuple(sc.members.values()),
        )
    )
    with caplog.at_level(logging.INFO, logger=_TRACE_LOGGER):
        await recompute_overflow_on_budget_event(
            household_singleton,
            BudgetUpdatedEvent(budget_id=budget_id, category_id=sc.category, currency="EUR"),
        )
    traces = [r for r in caplog.records if r.message.startswith("debts_recomputed_on_budget_event")]
    assert len(traces) == 1
    assert "transactions_recomputed_count=1" in traces[0].getMessage()


async def test_audit_trace_written_even_at_zero(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # A budget with no covered tx still writes the trace (count=0): the sweep is
    # always observable.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
    )
    # A budget on an UNRELATED category covers nothing.
    other_cat = await household_singleton.run_sync(_add_unrelated_category)
    budget_id = await household_singleton.run_sync(
        lambda s: _make_budget_row(
            s,
            category_id=other_cat,
            created_by=sc.payer,
            amount_cents=50000,
            contributor_ids=tuple(sc.members.values()),
        )
    )
    with caplog.at_level(logging.INFO, logger=_TRACE_LOGGER):
        await recompute_overflow_on_budget_event(
            household_singleton,
            BudgetUpdatedEvent(budget_id=budget_id, category_id=other_cat, currency="EUR"),
        )
    traces = [r for r in caplog.records if r.message.startswith("debts_recomputed_on_budget_event")]
    assert len(traces) == 1
    assert "transactions_recomputed_count=0" in traces[0].getMessage()


async def test_audit_trace_has_no_pii(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The trace contains only budget_id + count — no email, label, or amount.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    with caplog.at_level(logging.INFO, logger=_TRACE_LOGGER):
        budget_id = await _create_covering_budget(household_singleton, sc, amount_cents=50000)
    traces = [
        r.getMessage()
        for r in caplog.records
        if r.message.startswith("debts_recomputed_on_budget_event")
    ]
    assert traces, "the trace must be emitted via the real create_budget flow"
    msg = traces[0]
    assert str(budget_id) in msg
    assert "@example.com" not in msg and "Courses" not in msg and "10000" not in msg


def _add_unrelated_category(s: Session) -> UUID:
    cat = Category(name="Loisirs")
    s.add(cat)
    s.flush()
    return cat.id


# ---------------------------------------------------------------------------
# P11.4.3 — reclassement propagates to the classification leg
# ---------------------------------------------------------------------------


@dataclass
class ReclassBase:
    payer: UUID
    bob: UUID
    account: UUID
    cat_a: UUID
    cat_b: UUID


async def _seed_two_categories(
    session: AsyncSession, factories: FactoryBundle, *, ratio: Decimal = Decimal("0.5")
) -> ReclassBase:
    """Shared account (Alice payer + Bob) and two sibling categories A / B, no budget,
    no transaction. Tests add budgets and expenses via `run_sync`."""
    user_factory, account_factory, _ = await factories()

    def _do(s: Session) -> ReclassBase:
        alice = user_factory(email=f"a-{uuid4().hex[:8]}@example.com").id
        bob = user_factory(email=f"b-{uuid4().hex[:8]}@example.com").id
        account = account_factory(owner_id=None, name="Commun")
        s.add_all(
            [
                AccountMember(account_id=account.id, user_id=alice, default_share_ratio=ratio),
                AccountMember(account_id=account.id, user_id=bob, default_share_ratio=ratio),
            ]
        )
        s.flush()
        cat_a = Category(name="A")
        cat_b = Category(name="B")
        s.add_all([cat_a, cat_b])
        s.flush()
        return ReclassBase(alice, bob, account.id, cat_a.id, cat_b.id)

    return await session.run_sync(_do)


async def _classification_category(session: AsyncSession, tx_id: UUID) -> UUID | None:
    """Category of the classification leg (non-NULL category split) of `tx_id`."""
    row = await session.execute(
        select(Split.category_id).where(
            Split.transaction_id == tx_id, Split.category_id.is_not(None)
        )
    )
    return row.scalar_one_or_none()


async def test_category_edit_propagates_to_classification_leg(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # Editing `category_id` of a confirmed tx writes the new category onto the
    # classification leg; the funding leg stays NULL; the split structure/amounts
    # are unchanged (still 2 legs, zero-sum).
    base = await _seed_two_categories(household_singleton, bound_account_factories)
    tx = await household_singleton.run_sync(
        lambda s: _add_expense(
            s,
            account_id=base.account,
            category_id=base.cat_a,
            amount=10000,
            created_by=base.payer,
        )
    )
    await transition_to_confirmed(household_singleton, tx_id=tx)
    assert await _classification_category(household_singleton, tx) == base.cat_a

    await update_editable_fields(household_singleton, tx_id=tx, category_id=base.cat_b)
    assert await _classification_category(household_singleton, tx) == base.cat_b
    # Still exactly one funding (NULL) + one classification leg.
    legs = (
        (await household_singleton.execute(select(Split).where(Split.transaction_id == tx)))
        .scalars()
        .all()
    )
    assert len(legs) == 2
    assert sum(s.amount_cents for s in legs) == 0
    assert {s.category_id for s in legs} == {None, base.cat_b}


async def test_consumption_follows_reclassement(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # The budget consumption reads the classification leg: after a reclassement the
    # OLD budget consumption drops by M and the NEW budget consumption rises by M.
    base = await _seed_two_categories(household_singleton, bound_account_factories)
    budget_a, budget_b = await household_singleton.run_sync(
        lambda s: (
            _make_budget_row(
                s,
                category_id=base.cat_a,
                created_by=base.payer,
                amount_cents=50000,
                contributor_ids=(base.payer, base.bob),
            ),
            _make_budget_row(
                s,
                category_id=base.cat_b,
                created_by=base.payer,
                amount_cents=50000,
                contributor_ids=(base.payer, base.bob),
            ),
        )
    )
    tx = await household_singleton.run_sync(
        lambda s: _add_expense(
            s,
            account_id=base.account,
            category_id=base.cat_a,
            amount=10000,
            created_by=base.payer,
        )
    )
    await transition_to_confirmed(household_singleton, tx_id=tx)
    cons_a = await compute_consumption(household_singleton, budget_id=budget_a, as_of=_TODAY)
    cons_b = await compute_consumption(household_singleton, budget_id=budget_b, as_of=_TODAY)
    assert cons_a is not None and cons_a.consumed_cents == 10000
    assert cons_b is not None and cons_b.consumed_cents == 0

    await update_editable_fields(household_singleton, tx_id=tx, category_id=base.cat_b)
    cons_a2 = await compute_consumption(household_singleton, budget_id=budget_a, as_of=_TODAY)
    cons_b2 = await compute_consumption(household_singleton, budget_id=budget_b, as_of=_TODAY)
    assert cons_a2 is not None and cons_a2.consumed_cents == 0
    assert cons_b2 is not None and cons_b2.consumed_cents == 10000


async def test_category_edit_no_immutable_violation(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # The leg write does not trip `check_mutation_allowed` (splits are not in
    # `fields`) — the edit succeeds and reports `category_id` changed.
    received: list[TransactionEditableFieldsChangedEvent] = []
    subscribe(TransactionEditableFieldsChangedEvent, received.append)
    base = await _seed_two_categories(household_singleton, bound_account_factories)
    tx = await household_singleton.run_sync(
        lambda s: _add_expense(
            s,
            account_id=base.account,
            category_id=base.cat_a,
            amount=10000,
            created_by=base.payer,
        )
    )
    await transition_to_confirmed(household_singleton, tx_id=tx)

    after = await update_editable_fields(household_singleton, tx_id=tx, category_id=base.cat_b)
    assert after.category_id == base.cat_b
    assert any("category_id" in e.changed_fields for e in received)


async def test_previous_category_ids_populated_only_on_category_change(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # `previous_category_ids` carries the OLD classification category ONLY when
    # `category_id` changes; a description-only edit leaves it empty.
    received: list[TransactionEditableFieldsChangedEvent] = []
    subscribe(TransactionEditableFieldsChangedEvent, received.append)
    base = await _seed_two_categories(household_singleton, bound_account_factories)
    tx = await household_singleton.run_sync(
        lambda s: _add_expense(
            s,
            account_id=base.account,
            category_id=base.cat_a,
            amount=10000,
            created_by=base.payer,
        )
    )
    await transition_to_confirmed(household_singleton, tx_id=tx)

    await update_editable_fields(household_singleton, tx_id=tx, description="note libre")
    desc_events = [e for e in received if e.changed_fields == frozenset({"description"})]
    assert desc_events and desc_events[0].previous_category_ids == frozenset()

    await update_editable_fields(household_singleton, tx_id=tx, category_id=base.cat_b)
    cat_events = [e for e in received if "category_id" in e.changed_fields]
    assert cat_events and cat_events[0].previous_category_ids == frozenset({base.cat_a})


# ---------------------------------------------------------------------------
# P11.4.4 — reclassement re-materialises overflow on the tx + period neighbours
# ---------------------------------------------------------------------------


async def test_reclass_moves_overflow_to_new_budget(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # tx overflows on budget A (small) → reclass to a category covered by budget B
    # (large) → overflow REMOVED from A's resolution and recomputed against B (none).
    base = await _seed_two_categories(household_singleton, bound_account_factories)
    await household_singleton.run_sync(
        lambda s: (
            _make_budget_row(
                s,
                category_id=base.cat_a,
                created_by=base.payer,
                amount_cents=2000,
                contributor_ids=(base.payer, base.bob),
            ),
            _make_budget_row(
                s,
                category_id=base.cat_b,
                created_by=base.payer,
                amount_cents=50000,
                contributor_ids=(base.payer, base.bob),
            ),
        )
    )
    tx = await household_singleton.run_sync(
        lambda s: _add_expense(
            s,
            account_id=base.account,
            category_id=base.cat_a,
            amount=10000,
            created_by=base.payer,
        )
    )
    await transition_to_confirmed(household_singleton, tx_id=tx)
    # remaining 20 against M=100 → base 80 → Bob 40€.
    assert await _overflow_by_debtor(household_singleton, tx) == {base.bob: 4000}

    await update_editable_fields(household_singleton, tx_id=tx, category_id=base.cat_b)
    assert await _overflow_debts(household_singleton, tx) == []  # within budget B


async def test_reclass_to_unbudgeted_category_full_debt(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # tx within budget A (no overflow) → reclass to an UNBUDGETED category B →
    # overflow re-resolved « sans budget » → base = M (full debt).
    base = await _seed_two_categories(household_singleton, bound_account_factories)
    await household_singleton.run_sync(
        lambda s: _make_budget_row(
            s,
            category_id=base.cat_a,
            created_by=base.payer,
            amount_cents=50000,
            contributor_ids=(base.payer, base.bob),
        )
    )
    tx = await household_singleton.run_sync(
        lambda s: _add_expense(
            s,
            account_id=base.account,
            category_id=base.cat_a,
            amount=10000,
            created_by=base.payer,
        )
    )
    await transition_to_confirmed(household_singleton, tx_id=tx)
    assert await _overflow_debts(household_singleton, tx) == []

    await update_editable_fields(household_singleton, tx_id=tx, category_id=base.cat_b)
    assert await _overflow_by_debtor(household_singleton, tx) == {base.bob: 5000}


async def test_reclass_recomputes_old_budget_neighbours(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # KEY (previous_category_ids): budget A=100, tx X (earlier, M=100) consumes the
    # whole remaining so tx Y (later, M=100) bears the full overflow. Reclass X OUT
    # of A → Y's remaining is freed → Y's overflow drops to 0. Proves the OLD
    # budget's neighbours are recomputed from `previous_category_ids`.
    base = await _seed_two_categories(
        household_singleton, bound_account_factories, ratio=Decimal("1")
    )
    await household_singleton.run_sync(
        lambda s: _make_budget_row(
            s,
            category_id=base.cat_a,
            created_by=base.payer,
            amount_cents=10000,
            contributor_ids=(base.payer, base.bob),
        )
    )
    earlier = dt.date(2026, 6, 10)
    tx_x = await household_singleton.run_sync(
        lambda s: _add_expense(
            s,
            account_id=base.account,
            category_id=base.cat_a,
            amount=10000,
            created_by=base.payer,
            on=earlier,
        )
    )
    tx_y = await household_singleton.run_sync(
        lambda s: _add_expense(
            s,
            account_id=base.account,
            category_id=base.cat_a,
            amount=10000,
            created_by=base.payer,
            on=_TODAY,
        )
    )
    for tx in (tx_x, tx_y):
        await transition_to_confirmed(household_singleton, tx_id=tx)
    # X (earlier) sees full budget → 0; Y (later) bears the whole 100 excess.
    assert await _overflow_by_debtor(household_singleton, tx_x) == {}
    assert await _overflow_by_debtor(household_singleton, tx_y) == {base.bob: 10000}

    # Reclass X to the unbudgeted cat_b: X leaves A → Y now sees the full budget.
    await update_editable_fields(household_singleton, tx_id=tx_x, category_id=base.cat_b)
    assert await _overflow_by_debtor(household_singleton, tx_y) == {}  # neighbour recomputed
    # X itself, now unbudgeted, carries the full debt.
    assert await _overflow_by_debtor(household_singleton, tx_x) == {base.bob: 10000}


async def test_reclass_idempotent(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # Re-dispatching the same edit event leaves the overflow set identical.
    base = await _seed_two_categories(household_singleton, bound_account_factories)
    await household_singleton.run_sync(
        lambda s: _make_budget_row(
            s,
            category_id=base.cat_b,
            created_by=base.payer,
            amount_cents=2000,
            contributor_ids=(base.payer, base.bob),
        )
    )
    tx = await household_singleton.run_sync(
        lambda s: _add_expense(
            s,
            account_id=base.account,
            category_id=base.cat_a,
            amount=10000,
            created_by=base.payer,
        )
    )
    await transition_to_confirmed(household_singleton, tx_id=tx)
    await update_editable_fields(household_singleton, tx_id=tx, category_id=base.cat_b)
    first = await _overflow_by_debtor(household_singleton, tx)
    await rematerialize_overflow_on_edit(
        household_singleton,
        TransactionEditableFieldsChangedEvent(
            transaction_id=tx,
            changed_fields=frozenset({"category_id"}),
            previous_category_ids=frozenset({base.cat_a}),
        ),
    )
    assert await _overflow_by_debtor(household_singleton, tx) == first


async def test_override_only_edit_short_circuits_neighbours(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression S11.3: an override-only edit (no category_id) must NOT enumerate
    # neighbours — the budget resolver `list_overflow_budget_ids_for_categories` is
    # never called.
    mod = _materializer_module

    base = await _seed_two_categories(household_singleton, bound_account_factories)
    tx = await household_singleton.run_sync(
        lambda s: _add_expense(
            s,
            account_id=base.account,
            category_id=base.cat_a,
            amount=10000,
            created_by=base.payer,
        )
    )
    await transition_to_confirmed(household_singleton, tx_id=tx)

    calls = 0
    real = mod.list_overflow_budget_ids_for_categories

    async def _spy(*args: object, **kwargs: object) -> list[UUID]:
        nonlocal calls
        calls += 1
        return await real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(mod, "list_overflow_budget_ids_for_categories", _spy)
    await update_editable_fields(
        household_singleton, tx_id=tx, debt_generation_override="force_full_debt"
    )
    assert calls == 0  # neighbour enumeration skipped for a non-category edit


async def test_reclass_does_not_touch_share_request(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # AC opposable: a personal_share_request debt on the tx survives a reclassement.
    base = await _seed_two_categories(household_singleton, bound_account_factories)
    tx = await household_singleton.run_sync(
        lambda s: _add_expense(
            s,
            account_id=base.account,
            category_id=base.cat_a,
            amount=10000,
            created_by=base.payer,
        )
    )
    await transition_to_confirmed(household_singleton, tx_id=tx)

    def _add_sr(s: Session) -> UUID:
        d = Debt(
            from_user_id=base.bob,
            to_user_id=base.payer,
            amount_cents=321,
            currency="EUR",
            account_id=base.account,
            source_transaction_id=tx,
            origin="personal_share_request",
        )
        s.add(d)
        s.flush()
        return d.id

    sr_id = await household_singleton.run_sync(_add_sr)
    await update_editable_fields(household_singleton, tx_id=tx, category_id=base.cat_b)
    sr = (await household_singleton.execute(select(Debt).where(Debt.id == sr_id))).scalar_one()
    assert sr.origin == "personal_share_request" and sr.amount_cents == 321


async def test_reclass_recomputes_new_budget_neighbours(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # Symmetric to the OLD-budget neighbours case: budget B=100 on cat_b already has a
    # tx Z (within budget → 0). Reclass an EARLIER unbudgeted tx X INTO cat_b → X
    # consumes B's remaining first → Z's ordered remaining shifts → Z now overflows.
    # Proves the NEW-budget branch (`new_category_ids`) recomputes neighbours, not just
    # the reclassed tx itself.
    base = await _seed_two_categories(
        household_singleton, bound_account_factories, ratio=Decimal("1")
    )
    await household_singleton.run_sync(
        lambda s: _make_budget_row(
            s,
            category_id=base.cat_b,
            created_by=base.payer,
            amount_cents=10000,
            contributor_ids=(base.payer, base.bob),
        )
    )
    earlier = dt.date(2026, 6, 10)
    tx_x = await household_singleton.run_sync(
        lambda s: _add_expense(
            s,
            account_id=base.account,
            category_id=base.cat_a,
            amount=10000,
            created_by=base.payer,
            on=earlier,
        )
    )
    tx_z = await household_singleton.run_sync(
        lambda s: _add_expense(
            s,
            account_id=base.account,
            category_id=base.cat_b,
            amount=10000,
            created_by=base.payer,
            on=_TODAY,
        )
    )
    for tx in (tx_x, tx_z):
        await transition_to_confirmed(household_singleton, tx_id=tx)
    # X unbudgeted (cat_a) → full debt; Z alone within budget B → 0.
    assert await _overflow_by_debtor(household_singleton, tx_x) == {base.bob: 10000}
    assert await _overflow_by_debtor(household_singleton, tx_z) == {}

    await update_editable_fields(household_singleton, tx_id=tx_x, category_id=base.cat_b)
    assert await _overflow_by_debtor(household_singleton, tx_x) == {}  # X now first in B
    # Z, the LATER neighbour of the NEW budget, is recomputed: B is now exhausted by X.
    assert await _overflow_by_debtor(household_singleton, tx_z) == {base.bob: 10000}


# ---------------------------------------------------------------------------
# P11.4.4 — D6 walk-up: an ANCESTOR budget's neighbours are recomputed
# ---------------------------------------------------------------------------


@dataclass
class HierBase:
    payer: UUID
    bob: UUID
    account: UUID
    parent: UUID  # budgeted
    child: UUID  # sub-category of `parent`, where the expenses live
    sibling: UUID  # unbudgeted root, outside the parent subtree


async def _seed_hierarchy(session: AsyncSession, factories: FactoryBundle) -> HierBase:
    """Shared account (Alice payer + Bob, ratio 1 ⇒ Bob bears the full base) with a
    `parent → child` category tree and an unrelated unbudgeted `sibling` root."""
    user_factory, account_factory, _ = await factories()

    def _do(s: Session) -> HierBase:
        alice = user_factory(email=f"a-{uuid4().hex[:8]}@example.com").id
        bob = user_factory(email=f"b-{uuid4().hex[:8]}@example.com").id
        account = account_factory(owner_id=None, name="Commun")
        s.add_all(
            [
                AccountMember(
                    account_id=account.id, user_id=alice, default_share_ratio=Decimal("1")
                ),
                AccountMember(account_id=account.id, user_id=bob, default_share_ratio=Decimal("1")),
            ]
        )
        s.flush()
        parent = Category(name="Parent")
        sibling = Category(name="Sibling")
        s.add_all([parent, sibling])
        s.flush()
        child = Category(name="Child", parent_id=parent.id)
        s.add(child)
        s.flush()
        return HierBase(alice, bob, account.id, parent.id, child.id, sibling.id)

    return await session.run_sync(_do)


async def test_reclass_walk_up_recomputes_ancestor_budget_neighbours(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # D6 (walk-up): the budget sits on the PARENT category; both txs live in the CHILD
    # sub-category and consume the parent budget via its descendant subtree. Reclass X
    # OUT of the hierarchy (to an unbudgeted sibling root) → the PARENT budget's
    # neighbour Y is recomputed — found by walking UP from the child category in
    # `list_overflow_budget_ids_for_categories`. Exercises the ancestor path, which the
    # sibling-only `test_reclass_recomputes_old_budget_neighbours` never reaches.
    base = await _seed_hierarchy(household_singleton, bound_account_factories)
    await household_singleton.run_sync(
        lambda s: _make_budget_row(
            s,
            category_id=base.parent,
            created_by=base.payer,
            amount_cents=10000,
            contributor_ids=(base.payer, base.bob),
        )
    )
    earlier = dt.date(2026, 6, 10)
    tx_x = await household_singleton.run_sync(
        lambda s: _add_expense(
            s,
            account_id=base.account,
            category_id=base.child,
            amount=10000,
            created_by=base.payer,
            on=earlier,
        )
    )
    tx_y = await household_singleton.run_sync(
        lambda s: _add_expense(
            s,
            account_id=base.account,
            category_id=base.child,
            amount=10000,
            created_by=base.payer,
            on=_TODAY,
        )
    )
    for tx in (tx_x, tx_y):
        await transition_to_confirmed(household_singleton, tx_id=tx)
    # X (earlier, in child) fills the parent budget → 0; Y (later) bears the 100 excess.
    assert await _overflow_by_debtor(household_singleton, tx_x) == {}
    assert await _overflow_by_debtor(household_singleton, tx_y) == {base.bob: 10000}

    # Reclass X to the unbudgeted sibling (out of the parent subtree) → the parent
    # budget's neighbour Y is freed (walk-up from `previous_category_ids={child}`).
    await update_editable_fields(household_singleton, tx_id=tx_x, category_id=base.sibling)
    assert (
        await _overflow_by_debtor(household_singleton, tx_y) == {}
    )  # ancestor neighbour recomputed
    assert await _overflow_by_debtor(household_singleton, tx_x) == {
        base.bob: 10000
    }  # now unbudgeted


async def test_category_edit_on_transfer_is_graceful_noop(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # A transfer (NO classification leg — both legs `category_id NULL` ⇒ funding)
    # edited on `category_id` propagates to no leg and recomputes nothing: no crash,
    # no overflow debt, legs untouched. Proves the « transfer is a no-op » claim.
    base = await _seed_two_categories(household_singleton, bound_account_factories)

    def _add_transfer(s: Session) -> UUID:
        tx = Transaction(
            account_id=base.account,
            date=_TODAY,
            state="confirmed",
            created_by=base.payer,
            debt_generation_override="default",
        )
        s.add(tx)
        s.flush()
        s.add_all(
            [
                Split(
                    transaction_id=tx.id,
                    account_id=base.account,
                    category_id=None,
                    amount_cents=-10000,
                    currency="EUR",
                ),
                Split(
                    transaction_id=tx.id,
                    account_id=base.account,
                    category_id=None,
                    amount_cents=10000,
                    currency="EUR",
                ),
            ]
        )
        s.flush()
        return tx.id

    tx = await household_singleton.run_sync(_add_transfer)
    # The category edit must not raise and must leave no overflow behind.
    await update_editable_fields(household_singleton, tx_id=tx, category_id=base.cat_a)
    assert await _overflow_debts(household_singleton, tx) == []
    # No classification leg was created/touched — both legs stay funding (NULL).
    legs = (
        (await household_singleton.execute(select(Split).where(Split.transaction_id == tx)))
        .scalars()
        .all()
    )
    assert {s.category_id for s in legs} == {None}


# ---------------------------------------------------------------------------
# Composition-root wiring — the REAL POST /budgets route materialises overflow
# ---------------------------------------------------------------------------


async def test_post_budgets_route_recomputes_overflow_end_to_end(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # Drive the REAL `POST /budgets` route (not a manual `dispatch`) and rely on
    # `backend.main._register_event_subscribers` — the production composition root — to
    # wire `BudgetCreatedEvent` to the reclassement handler. If that wiring line ever
    # disappears from `main.py`, the overflow survives and this test fails: the silent
    # regression the manual `_wire_reclass` fixture structurally cannot catch.
    clear_subscribers()
    _register_event_subscribers()  # the actual production wiring under test

    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    assert await _overflow_by_debtor(household_singleton, sc.tx) == {sc.members["bob"]: 5000}

    resp = await async_client.post(
        "/budgets",
        json={
            "category_id": str(sc.category),
            "period_kind": "monthly",
            "period_start": _PERIOD_START.isoformat(),
            "amount_cents": 50000,
            "scope": "shared",
            "contributor_ids": [str(uid) for uid in sc.members.values()],
        },
        headers=_bearer(sc.payer),
    )
    assert resp.status_code == 201, resp.text
    assert await _overflow_debts(household_singleton, sc.tx) == []  # recomputed end-to-end
