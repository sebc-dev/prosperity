"""Integration tests for the budget threshold detector (S08.3, repiloted S08.5.3).

Drives the **real** confirm flow end to end: `transition_to_confirmed` →
`dispatch` → `on_transaction_confirmed`, with a SYNC spy subscribed to
`BudgetThresholdEvent` proving the livrable observable. The idempotence table
`budget_threshold_alerts` is inspected alongside the spy.

Reconciled consumption model (ADR 0017, S08.5.3 — D1/D2). Since #137 a dépense
in **forme canonique B** (jambe `funding` compte `category_id=NULL` + jambe
`classification` catégorisée, même compte, zero-sum) is **confirmable by the
service** AND consumed by the budget: `_consumption_filters` sums the
`classification` leg (the `funding` NULL leg is excluded by `category_id ∈
subtree`). So there are no longer **two** objects (a directly-seeded `confirmed`
expense driving consumption + a net-0 `planned` trigger firing detection) but a
**single** one — the consuming expense IS the trigger. Every scenario below seeds
a `planned` form-B expense via `_add_planned_expense` and confirms it through the
real service; the flip to `CONFIRMED` happens **before** `dispatch`, and
`compute_consumption` filters `state == "confirmed"`, so the just-confirmed
expense is in the total the detector observes. No more DB-direct seed of the
consuming form (AC #138).

Wiring (corrects review Bloquant B1). The `subscribe_async` câblage lives in
`main.py`'s `lifespan`; these tests call `transition_to_confirmed` directly
(no lifespan) and the autouse fixture `clear_subscribers()` wipes BOTH registries.
The fixture below therefore re-subscribes the detector after the clear, before
any confirm — and `test_wiring_is_load_bearing` pins that this wiring is
load-bearing (an unwired detector makes a "1 event" case fail, not silently pass).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from backend.modules.accounts.domain import AccountType
from backend.modules.accounts.models import Account, Household
from backend.modules.auth.models import User, UserRole
from backend.modules.budget.models import Budget, BudgetContributor, BudgetThresholdAlert, Category
from backend.modules.budget.public import BudgetThresholdEvent, on_transaction_confirmed
from backend.modules.transactions.events import TransactionConfirmedEvent
from backend.modules.transactions.models import Split, Transaction
from backend.modules.transactions.service.lifecycle import transition_to_confirmed
from backend.shared.events import clear_subscribers, subscribe, subscribe_async

FactoryBundle = Callable[[], Awaitable[tuple[type, type, type]]]

# Anchor the monthly budget on the 1st of the *current* month and date the
# transactions today, so the detector's `as_of = now().date()` always lands in
# the budget's window [1st-of-month, 1st-of-next-month).
_TODAY = datetime.now(UTC).date()
_PERIOD_START = _TODAY.replace(day=1)


@pytest.fixture(autouse=True)
def _wire_threshold_detector() -> Iterator[list[BudgetThresholdEvent]]:  # pyright: ignore[reportUnusedFunction]
    """Re-wire the detector on the bus and spy on `BudgetThresholdEvent`.

    `clear_subscribers()` first (cold bus), then `subscribe_async` the real
    detector (the lifespan câblage does not run in this tier) and a SYNC spy.
    Yields the captured-events list. Cleared again on teardown (process-global).
    """
    clear_subscribers()
    subscribe_async(TransactionConfirmedEvent, on_transaction_confirmed)
    captured: list[BudgetThresholdEvent] = []
    subscribe(BudgetThresholdEvent, captured.append)
    yield captured
    clear_subscribers()


# ---------------------------------------------------------------------------
# Seed helpers (run inside `run_sync` on the test's sync Session)
# ---------------------------------------------------------------------------


def _add_planned_expense(  # noqa: PLR0913 — keyword-only seed helper
    s: Session,
    *,
    account_id: UUID,
    category_id: UUID,
    amount: int,
    created_by: UUID,
    override: str = "default",
    currency: str = "EUR",
) -> UUID:
    """Persist a `planned` expense in **canonical form B** (ADR 0017) and return
    its id, ready to be confirmed by the service.

    `funding` leg (account movement): `category_id=NULL`, `-amount` (leg_role
    derived `funding` by the ORM default). `classification` leg: `category_id`,
    `+amount` (leg_role `classification`). Same account, zero-sum.

    Once confirmed via `transition_to_confirmed`, this expense:
      * **raises** the consumption by `amount` (the NULL leg is excluded by the
        `category_id ∈ subtree` filter), AND
      * **triggers** the threshold detector (state `CONFIRMED` before `dispatch`).
    It is the single object: no more seeded consumption + net-0 trigger.
    """
    tx = Transaction(
        account_id=account_id,
        date=_TODAY,
        state="planned",
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
                currency=currency,
            ),
            Split(
                transaction_id=tx.id,
                account_id=account_id,
                category_id=category_id,
                amount_cents=amount,
                currency=currency,
            ),
        ]
    )
    s.flush()
    return tx.id


def _make_budget(  # noqa: PLR0913 — keyword-only seed helper
    s: Session,
    *,
    category_id: UUID,
    created_by: UUID,
    amount_cents: int,
    scope: str = "personal",
    contributor_ids: tuple[UUID, ...] = (),
) -> UUID:
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


def _seed_alert(s: Session, *, budget_id: UUID, threshold_pct: int) -> None:
    """Pre-seed a `budget_threshold_alerts` row (a previously-notified crossing)."""
    s.add(
        BudgetThresholdAlert(
            budget_id=budget_id, period_start=_PERIOD_START, threshold_pct=threshold_pct
        )
    )
    s.flush()


async def _alert_count(session: AsyncSession, budget_id: UUID) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(BudgetThresholdAlert)
            .where(BudgetThresholdAlert.budget_id == budget_id)
        )
    ).scalar_one()


async def _tx_state(session: AsyncSession, tx_id: UUID) -> str:
    return (
        await session.execute(select(Transaction.state).where(Transaction.id == tx_id))
    ).scalar_one()


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


async def test_below_threshold_emits_no_event(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
    _wire_threshold_detector: list[BudgetThresholdEvent],
) -> None:
    # Consumption pushed to 79 % (7900 / 10000) → nothing crosses → 0 event.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="below@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        budget_id = _make_budget(s, category_id=cat.id, created_by=owner.id, amount_cents=10000)
        return _add_planned_expense(
            s, account_id=acc.id, category_id=cat.id, amount=7900, created_by=owner.id
        ), budget_id

    tx_id, budget_id = await household_singleton.run_sync(_seed)
    await transition_to_confirmed(household_singleton, tx_id=tx_id)

    assert _wire_threshold_detector == []
    assert await _alert_count(household_singleton, budget_id) == 0


async def test_crossing_80_emits_once(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
    _wire_threshold_detector: list[BudgetThresholdEvent],
) -> None:
    # 81 % (8100 / 10000) → exactly one event `80`, with the exact payload. The
    # consumed amount now comes from the **confirmed** expense, not a seed.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="cross80@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        budget_id = _make_budget(s, category_id=cat.id, created_by=owner.id, amount_cents=10000)
        return _add_planned_expense(
            s, account_id=acc.id, category_id=cat.id, amount=8100, created_by=owner.id
        ), budget_id

    tx_id, budget_id = await household_singleton.run_sync(_seed)
    await transition_to_confirmed(household_singleton, tx_id=tx_id)

    assert len(_wire_threshold_detector) == 1
    evt = _wire_threshold_detector[0]
    assert evt.budget_id == budget_id
    assert evt.threshold_pct == 80
    # Positive consumed (expense sign convention of `compute_consumption`).
    assert evt.consumed_cents == 8100
    assert evt.period_start == _PERIOD_START
    assert await _alert_count(household_singleton, budget_id) == 1


async def test_crossing_exactly_80_emits_once(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
    _wire_threshold_detector: list[BudgetThresholdEvent],
) -> None:
    # Boundary (S08.5.3 §I): consumption EXACTLY at 80.00 % (8000 / 10000). The
    # detector counts equality as reached (`consumed*100 >= pct*amount`), so the
    # `80` event fires once — pins the frontier the other scenarios straddle.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="exact80@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        budget_id = _make_budget(s, category_id=cat.id, created_by=owner.id, amount_cents=10000)
        return _add_planned_expense(
            s, account_id=acc.id, category_id=cat.id, amount=8000, created_by=owner.id
        ), budget_id

    tx_id, budget_id = await household_singleton.run_sync(_seed)
    await transition_to_confirmed(household_singleton, tx_id=tx_id)

    assert [e.threshold_pct for e in _wire_threshold_detector] == [80]
    assert _wire_threshold_detector[0].consumed_cents == 8000
    assert await _alert_count(household_singleton, budget_id) == 1


async def test_only_new_threshold_published_when_80_pre_seeded(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
    _wire_threshold_detector: list[BudgetThresholdEvent],
) -> None:
    # 105 % with `80` already notified (pre-seeded row) → only `100` is published.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="cross100@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        budget_id = _make_budget(s, category_id=cat.id, created_by=owner.id, amount_cents=10000)
        _seed_alert(s, budget_id=budget_id, threshold_pct=80)
        return _add_planned_expense(
            s, account_id=acc.id, category_id=cat.id, amount=10500, created_by=owner.id
        ), budget_id

    tx_id, budget_id = await household_singleton.run_sync(_seed)
    await transition_to_confirmed(household_singleton, tx_id=tx_id)

    assert [e.threshold_pct for e in _wire_threshold_detector] == [100]
    # Rows: pre-seeded 80 + newly-inserted 100.
    assert await _alert_count(household_singleton, budget_id) == 2


async def test_crossing_120_from_100_pre_seeded(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
    _wire_threshold_detector: list[BudgetThresholdEvent],
) -> None:
    # 125 % with `80` and `100` already notified → only `120` is published.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="cross120@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        budget_id = _make_budget(s, category_id=cat.id, created_by=owner.id, amount_cents=10000)
        _seed_alert(s, budget_id=budget_id, threshold_pct=80)
        _seed_alert(s, budget_id=budget_id, threshold_pct=100)
        return _add_planned_expense(
            s, account_id=acc.id, category_id=cat.id, amount=12500, created_by=owner.id
        ), budget_id

    tx_id, budget_id = await household_singleton.run_sync(_seed)
    await transition_to_confirmed(household_singleton, tx_id=tx_id)

    assert [e.threshold_pct for e in _wire_threshold_detector] == [120]
    assert await _alert_count(household_singleton, budget_id) == 3


async def test_multi_threshold_single_write(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
    _wire_threshold_detector: list[BudgetThresholdEvent],
) -> None:
    # 130 % with no prior alert → one event per crossed threshold: 80, 100, 120.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="multi@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        budget_id = _make_budget(s, category_id=cat.id, created_by=owner.id, amount_cents=10000)
        return _add_planned_expense(
            s, account_id=acc.id, category_id=cat.id, amount=13000, created_by=owner.id
        ), budget_id

    tx_id, budget_id = await household_singleton.run_sync(_seed)
    await transition_to_confirmed(household_singleton, tx_id=tx_id)

    assert sorted(e.threshold_pct for e in _wire_threshold_detector) == [80, 100, 120]
    assert await _alert_count(household_singleton, budget_id) == 3


async def test_idempotent_on_second_confirmation(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
    _wire_threshold_detector: list[BudgetThresholdEvent],
) -> None:
    # Two confirmations that BOTH leave consumption in the same band [80 %, 100 %)
    # → the `80` event fires ONCE (the second confirm re-evaluates, recomputes the
    # SAME `[80]` set, and the INSERT hits ON CONFLICT DO NOTHING → no re-publish).
    # The 8100-then-+50 amounts (81 % → 81.5 %) cross no NEW threshold (S08.5.3 D4).
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID, UUID]:
        owner = user_factory(email="idem@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        budget_id = _make_budget(s, category_id=cat.id, created_by=owner.id, amount_cents=10000)
        tx1 = _add_planned_expense(
            s, account_id=acc.id, category_id=cat.id, amount=8100, created_by=owner.id
        )
        tx2 = _add_planned_expense(
            s, account_id=acc.id, category_id=cat.id, amount=50, created_by=owner.id
        )
        return tx1, tx2, budget_id

    tx1, tx2, budget_id = await household_singleton.run_sync(_seed)
    await transition_to_confirmed(household_singleton, tx_id=tx1)
    await transition_to_confirmed(household_singleton, tx_id=tx2)

    assert [e.threshold_pct for e in _wire_threshold_detector] == [80]
    # The single event is the FIRST confirm's (consumed 8100): the second confirm
    # re-evaluated and republished nothing (ON CONFLICT), it did not emit 8150.
    assert _wire_threshold_detector[0].consumed_cents == 8100
    assert await _alert_count(household_singleton, budget_id) == 1


async def test_cumulative_crossing_across_two_confirms(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
    _wire_threshold_detector: list[BudgetThresholdEvent],
) -> None:
    # Recovers the "(re)trigger is orthogonal to the tx amount" coverage the old
    # net-0 trigger gave (S08.5.3 §E): a FIRST expense at 50 % (5000) crosses
    # nothing, a SECOND at +31 % (3100) brings the CUMULATIVE to 81 % → the `80`
    # event fires on the SECOND confirm. This discriminates a CUMULATIVE recompute
    # (sums 8100) from a per-tx one (3100 = 31 % alone would cross nothing).
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID, UUID]:
        owner = user_factory(email="cumulative@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        budget_id = _make_budget(s, category_id=cat.id, created_by=owner.id, amount_cents=10000)
        tx1 = _add_planned_expense(
            s, account_id=acc.id, category_id=cat.id, amount=5000, created_by=owner.id
        )
        tx2 = _add_planned_expense(
            s, account_id=acc.id, category_id=cat.id, amount=3100, created_by=owner.id
        )
        return tx1, tx2, budget_id

    tx1, tx2, budget_id = await household_singleton.run_sync(_seed)
    await transition_to_confirmed(household_singleton, tx_id=tx1)
    assert _wire_threshold_detector == []  # 50 % crosses nothing

    await transition_to_confirmed(household_singleton, tx_id=tx2)
    assert [e.threshold_pct for e in _wire_threshold_detector] == [80]
    assert _wire_threshold_detector[0].consumed_cents == 8100  # cumulative, not 3100
    assert await _alert_count(household_singleton, budget_id) == 1


async def test_force_full_debt_not_counted(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
    _wire_threshold_detector: list[BudgetThresholdEvent],
) -> None:
    # A `force_full_debt` expense that would reach 90 % is "hors budget" → 0 event.
    # It IS confirmed via the service (the override does not block confirmation,
    # S08.5.3 §J); the `[]` comes from the consumption filter excluding it.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="ffd@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        budget_id = _make_budget(s, category_id=cat.id, created_by=owner.id, amount_cents=10000)
        return _add_planned_expense(
            s,
            account_id=acc.id,
            category_id=cat.id,
            amount=9000,
            created_by=owner.id,
            override="force_full_debt",
        ), budget_id

    tx_id, budget_id = await household_singleton.run_sync(_seed)
    await transition_to_confirmed(household_singleton, tx_id=tx_id)

    # The `[]` is the consumption FILTER (override), not a silent confirm failure.
    assert await _tx_state(household_singleton, tx_id) == "confirmed"
    assert _wire_threshold_detector == []
    assert await _alert_count(household_singleton, budget_id) == 0


async def test_hierarchical_parent_budget_alerts(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
    _wire_threshold_detector: list[BudgetThresholdEvent],
) -> None:
    # Expense on a CHILD category, budget posted on the PARENT → the upward
    # resolution (D8) makes the parent budget alert.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="hier@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        parent = Category(name="Maison")
        s.add(parent)
        s.flush()
        child = Category(name="Énergie", parent_id=parent.id)
        s.add(child)
        s.flush()
        budget_id = _make_budget(s, category_id=parent.id, created_by=owner.id, amount_cents=10000)
        return _add_planned_expense(
            s, account_id=acc.id, category_id=child.id, amount=8100, created_by=owner.id
        ), budget_id

    tx_id, budget_id = await household_singleton.run_sync(_seed)
    await transition_to_confirmed(household_singleton, tx_id=tx_id)

    assert [e.threshold_pct for e in _wire_threshold_detector] == [80]
    assert await _alert_count(household_singleton, budget_id) == 1


async def test_transfer_without_category_emits_nothing(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
    _wire_threshold_detector: list[BudgetThresholdEvent],
) -> None:
    # A confirmed transfer (2 accounts, uncategorised legs) short-circuits the
    # detector (`_split_category_ids` empty) → no event, even against a HOT budget.
    # The budget is warmed by a REAL consuming confirm (9000 → 90 %, emits `80`);
    # a snapshot of the spy then isolates the transfer's (null) effect (D5).
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID, UUID]:
        owner = user_factory(email="transfer@example.com")
        acc_a = account_factory(owner_id=owner.id, name="A")
        acc_b = account_factory(owner_id=owner.id, name="B")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        budget_id = _make_budget(s, category_id=cat.id, created_by=owner.id, amount_cents=10000)
        hot = _add_planned_expense(
            s, account_id=acc_a.id, category_id=cat.id, amount=9000, created_by=owner.id
        )
        # Transfer built inline (D6): 2 distinct accounts, uncategorised funding
        # legs — structurally different from the mono-account form B helper. Both
        # legs are `funding`, allowed here because a transfer (≥ 2 accounts) is
        # exempt from `assert_at_most_one_funding_leg` AND from categorisation.
        transfer = Transaction(
            account_id=acc_a.id, date=_TODAY, state="planned", created_by=owner.id
        )
        s.add(transfer)
        s.flush()
        s.add_all(
            [
                Split(
                    transaction_id=transfer.id,
                    account_id=acc_a.id,
                    category_id=None,
                    amount_cents=-1000,
                    currency="EUR",
                ),
                Split(
                    transaction_id=transfer.id,
                    account_id=acc_b.id,
                    category_id=None,
                    amount_cents=1000,
                    currency="EUR",
                ),
            ]
        )
        s.flush()
        return hot, transfer.id, budget_id

    hot_id, transfer_id, budget_id = await household_singleton.run_sync(_seed)

    # Warm the budget with a real consuming confirm → it legitimately emits `80`.
    await transition_to_confirmed(household_singleton, tx_id=hot_id)
    before = list(_wire_threshold_detector)
    assert [e.threshold_pct for e in before] == [80]  # the budget IS hot now
    count_before = await _alert_count(household_singleton, budget_id)

    # Confirming the transfer against the hot budget adds NOTHING.
    await transition_to_confirmed(household_singleton, tx_id=transfer_id)
    assert list(_wire_threshold_detector) == before
    assert await _alert_count(household_singleton, budget_id) == count_before


async def test_shared_scope_non_contributor_account_no_leak(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
    _wire_threshold_detector: list[BudgetThresholdEvent],
) -> None:
    # The ONLY cross-scope non-leak guard (fully delegated to compute_consumption,
    # D8): a `shared` budget whose eligible accounts don't include the expense's
    # account → consumption 0 → no event, despite a high raw spend.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        a = user_factory(email="leak-a@example.com")
        b = user_factory(email="leak-b@example.com")
        perso = account_factory(owner_id=a.id, name="A perso")  # personal, NOT a shared account
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        budget_id = _make_budget(
            s,
            category_id=cat.id,
            created_by=a.id,
            amount_cents=10000,
            scope="shared",
            contributor_ids=(a.id, b.id),
        )
        # High spend on a PERSONAL account; the shared budget's eligible set is
        # shared accounts whose members ⊆ {a,b} — a personal account is not one.
        return _add_planned_expense(
            s, account_id=perso.id, category_id=cat.id, amount=9000, created_by=a.id
        ), budget_id

    tx_id, budget_id = await household_singleton.run_sync(_seed)
    await transition_to_confirmed(household_singleton, tx_id=tx_id)

    assert _wire_threshold_detector == []
    assert await _alert_count(household_singleton, budget_id) == 0


async def test_shared_scope_account_with_foreign_member_no_leak(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
    _wire_threshold_detector: list[BudgetThresholdEvent],
) -> None:
    # Defensive sibling of the personal-account guard above, exercising the OTHER
    # exclusion branch: a COMMON account (owner_id=None) is eligible for a `shared`
    # budget only if its members ⊆ the contributor set. A common account with a
    # FOREIGN member (c ∉ {a,b}) is excluded (the members-subset branch of
    # compute_consumption's eligible set) → consumption 0 → no event, despite a
    # high raw spend.
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(s: Session) -> tuple[UUID, UUID]:
        a = user_factory(email="fm-a@example.com")
        b = user_factory(email="fm-b@example.com")
        c = user_factory(email="fm-c@example.com")  # foreign member, NOT a contributor
        abc = account_factory(owner_id=None, name="ABC commun")
        member_factory(account_id=abc.id, user_id=a.id, default_share_ratio="0.3333")
        member_factory(account_id=abc.id, user_id=b.id, default_share_ratio="0.3333")
        member_factory(account_id=abc.id, user_id=c.id, default_share_ratio="0.3334")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        budget_id = _make_budget(
            s,
            category_id=cat.id,
            created_by=a.id,
            amount_cents=10000,
            scope="shared",
            contributor_ids=(a.id, b.id),
        )
        return _add_planned_expense(
            s, account_id=abc.id, category_id=cat.id, amount=9000, created_by=a.id
        ), budget_id

    tx_id, budget_id = await household_singleton.run_sync(_seed)
    await transition_to_confirmed(household_singleton, tx_id=tx_id)

    assert _wire_threshold_detector == []
    assert await _alert_count(household_singleton, budget_id) == 0


async def test_wiring_is_load_bearing(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # Guard (review B1): DELIBERATELY unwire the detector, keep only the spy, then
    # confirm a crossing. With no async subscriber the crossing yields NO event —
    # so a future mis-ordered `clear` that drops the detector fails THIS test
    # instead of silently passing a "1 event" scenario for the wrong reason.
    clear_subscribers()
    captured: list[BudgetThresholdEvent] = []
    subscribe(BudgetThresholdEvent, captured.append)
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(s: Session) -> UUID:
        owner = user_factory(email="guard@example.com")
        acc = account_factory(owner_id=owner.id, name="Perso")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        _make_budget(s, category_id=cat.id, created_by=owner.id, amount_cents=10000)
        return _add_planned_expense(
            s, account_id=acc.id, category_id=cat.id, amount=8100, created_by=owner.id
        )

    tx_id = await household_singleton.run_sync(_seed)
    await transition_to_confirmed(household_singleton, tx_id=tx_id)

    assert captured == []  # detector unwired → no event (proves the wiring matters)


# ---------------------------------------------------------------------------
# Real-commit tier — detector failure rolls the confirmation back (D13)
# ---------------------------------------------------------------------------


async def _seed_committed_budget_scenario(sm: async_sessionmaker[AsyncSession]) -> UUID:
    """Seed a committed budget + a `planned` form-B 81 %-expense; return its id.

    The consuming expense IS the trigger now (S08.5.3): the test confirms it and
    asserts the detector failure rolls the confirm back — no DB-direct seed.
    """
    async with sm() as session:
        session.add(Household(name="Committed-S083", base_currency="EUR"))
        await session.commit()
    async with sm() as session:
        owner = User(
            email="d13@example.com",
            password_hash="x" * 60,
            display_name="owner",
            role=UserRole.MEMBER,
        )
        session.add(owner)
        await session.flush()
        acc = Account(name="Perso", type=AccountType.COURANT, currency="EUR", owner_id=owner.id)
        session.add(acc)
        await session.flush()
        cat = Category(name="Courses")
        session.add(cat)
        await session.flush()

        def _seed(s: Session) -> UUID:
            _make_budget(s, category_id=cat.id, created_by=owner.id, amount_cents=10000)
            return _add_planned_expense(
                s, account_id=acc.id, category_id=cat.id, amount=8100, created_by=owner.id
            )

        tx_id = await session.run_sync(_seed)
        await session.commit()
    return tx_id


@pytest.mark.usefixtures("_clean_committed_db")
async def test_detector_failure_rolls_back_confirmation(
    committed_sessionmaker: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    # D13 arbitrage: the detector is on the critical path. If it raises (here we
    # force `compute_consumption` to blow up), the WHOLE confirmation rolls back —
    # the transaction stays `planned` and no alert row is committed.
    sm = committed_sessionmaker
    tx_id = await _seed_committed_budget_scenario(sm)

    async def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("detector recompute failed")

    monkeypatch.setattr(
        "backend.modules.budget.service.threshold_detector.compute_consumption", _boom
    )

    async with sm() as session:
        with pytest.raises(RuntimeError, match="recompute failed"):
            await transition_to_confirmed(session, tx_id=tx_id)
        await session.rollback()

    async with sm() as session:
        state = (
            await session.execute(select(Transaction.state).where(Transaction.id == tx_id))
        ).scalar_one()
        assert state == "planned"  # confirmation rolled back
        alerts = (
            await session.execute(select(func.count()).select_from(BudgetThresholdAlert))
        ).scalar_one()
        assert alerts == 0  # nothing committed out-of-transaction
