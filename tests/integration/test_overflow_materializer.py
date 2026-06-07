"""Integration tests for the overflow debt materializer (E11 / S11.3).

Drive the F10 overflow projection against a real Postgres so every step fires:
the ordered-window budget resolution (`resolve_overflow_context`), the
member/quote-part read (`shared_account_members_with_ratios`), the pure
`compute_for_overflow`, and the idempotent upsert + prune
(`uq_debts_overflow_active` partial unique). Covers the three handlers:

* `materialize_overflow` (P11.3.2) — confirm path + idempotence + conservation,
* `remove_overflow_on_void` (P11.3.3) — void deletes overflow, spares share-requests,
* `rematerialize_overflow_on_edit` (P11.3.4) — override edit re-materialises.

Wiring (gabarit `test_budget_threshold_alerts`): the `subscribe_async` câblage
lives in `main.py`'s `lifespan`; this tier calls `transition_to_confirmed`/`void`/
`update_editable_fields` directly (no lifespan), so the autouse `_wire_overflow`
fixture `clear_subscribers()` then re-subscribes the three handlers. Tests that
need only the effectful core call the handlers directly (idempotence, rollback).

Seeds use the **canonical expense form B** (ADR 0017): a funding leg
(`category_id=NULL`, `-M`) + a classification leg (`category_id=C`, `+M`), same
shared account, zero-sum — so the classification leg both *consumes* the budget
and *carries* the overflow expense total. Overflow debts orient *other members →
payer* (`tx.created_by`); the payer (Alice) never owes themselves.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from backend.modules.accounts.models import Account, AccountMember, Household
from backend.modules.auth.models import User
from backend.modules.budget.models import Budget, BudgetContributor, Category
from backend.modules.debts.models import Debt
from backend.modules.debts.service import overflow_materializer as _materializer_module
from backend.modules.debts.service.overflow_materializer import (
    materialize_overflow,
    rematerialize_overflow_on_edit,
    remove_overflow_on_void,
)
from backend.modules.transactions.events import (
    TransactionConfirmedEvent,
    TransactionEditableFieldsChangedEvent,
    TransactionVoidedEvent,
)
from backend.modules.transactions.models import Split, Transaction
from backend.modules.transactions.service.lifecycle import (
    transition_to_confirmed,
    update_editable_fields,
    void,
)
from backend.shared.events import clear_subscribers, subscribe_async
from backend.shared.models import Base
from backend.shared.money import Money

FactoryBundle = Callable[
    [], Awaitable[tuple[type, type, type]]
]  # (UserFactory, AccountFactory, AccountMemberFactory)

_OVERFLOW = "shared_account_overflow"
_TODAY = dt.date(2026, 6, 15)
_PERIOD_START = dt.date(2026, 6, 1)


@pytest.fixture(autouse=True)
def _wire_overflow() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Re-wire the three overflow handlers on the bus (the lifespan câblage does
    not run in this tier). `clear_subscribers()` first (cold bus); cleared again
    on teardown (process-global state)."""
    clear_subscribers()
    subscribe_async(TransactionConfirmedEvent, materialize_overflow)
    subscribe_async(TransactionVoidedEvent, remove_overflow_on_void)
    subscribe_async(TransactionEditableFieldsChangedEvent, rematerialize_overflow_on_edit)
    yield
    clear_subscribers()


# ---------------------------------------------------------------------------
# Seed helpers (run inside `run_sync` on the test's sync Session)
# ---------------------------------------------------------------------------


@dataclass
class Scenario:
    payer: UUID  # Alice — tx.created_by → creditor
    members: dict[str, UUID]  # name → user_id (incl. payer)
    account: UUID
    category: UUID
    budget: UUID | None
    tx: UUID


def _add_expense(  # noqa: PLR0913 — keyword-only seed knobs
    s: Session,
    *,
    account_id: UUID,
    category_id: UUID | None,
    amount: int,
    created_by: UUID,
    state: str = "confirmed",
    override: str = "default",
    on: dt.date = _TODAY,
    transfer_account_id: UUID | None = None,
) -> UUID:
    """Persist a canonical form-B expense (funding NULL leg + classification leg).

    `transfer_account_id` (≠ None) makes a TRANSFER instead: the second leg moves
    money to another account (no classification leg, ≥ 2 accounts) → no overflow.
    """
    tx = Transaction(
        account_id=account_id,
        date=on,
        state=state,
        created_by=created_by,
        debt_generation_override=override,
    )
    s.add(tx)
    s.flush()
    if transfer_account_id is not None:
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
                    account_id=transfer_account_id,
                    category_id=None,
                    amount_cents=amount,
                    currency="EUR",
                ),
            ]
        )
    else:
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


def _make_budget(  # noqa: PLR0913 — keyword-only seed knobs
    s: Session,
    *,
    category_id: UUID,
    created_by: UUID,
    amount_cents: int,
    scope: str = "shared",
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


async def _seed(  # noqa: PLR0913 — keyword-only scenario knobs
    session: AsyncSession,
    factories: FactoryBundle,
    *,
    member_ratios: dict[str, Decimal],
    amount: int,
    budget_amount: int | None,
    override: str = "default",
    state: str = "planned",
    personal_account: bool = False,
    personal_budget: bool = False,
    archived_account: bool = False,
) -> Scenario:
    """Seed Alice (payer/creator) + the other members of a shared account, a
    category, an optional budget, and one expense. `member_ratios` maps name →
    `default_share_ratio` (must include "alice"). `budget_amount=None` → no budget.
    """
    user_factory, account_factory, _ = await factories()

    def _do(s: Session) -> Scenario:
        members: dict[str, UUID] = {}
        for name in member_ratios:
            members[name] = user_factory(email=f"{name}-{uuid4().hex[:8]}@example.com").id
        payer = members["alice"]

        if personal_account:
            account = account_factory(owner_id=payer, name="Alice perso")
        else:
            account = account_factory(owner_id=None, name="Commun")
            for name, ratio in member_ratios.items():
                s.add(
                    AccountMember(
                        account_id=account.id, user_id=members[name], default_share_ratio=ratio
                    )
                )
            s.flush()
        if archived_account:
            account.archived_at = dt.datetime(2026, 5, 1, tzinfo=dt.UTC)
            s.flush()

        cat = Category(name="Courses")
        s.add(cat)
        s.flush()

        budget_id: UUID | None = None
        if budget_amount is not None:
            budget_id = _make_budget(
                s,
                category_id=cat.id,
                created_by=payer,
                amount_cents=budget_amount,
                scope="personal" if personal_budget else "shared",
                contributor_ids=() if personal_budget else tuple(members.values()),
            )

        tx_id = _add_expense(
            s,
            account_id=account.id,
            category_id=cat.id,
            amount=amount,
            created_by=payer,
            state=state,
            override=override,
        )
        return Scenario(payer, members, account.id, cat.id, budget_id, tx_id)

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


# ---------------------------------------------------------------------------
# P11.3.2 — confirm path (AC + D9)
# ---------------------------------------------------------------------------


async def test_default_within_budget_no_debt(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # AC: default, budget not exceeded (M=100 ≤ budget=500) → no overflow debt.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
        budget_amount=50000,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    assert await _overflow_debts(household_singleton, sc.tx) == []


async def test_default_overflow_proportional(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # AC: Alice 100€, remaining-before 50€ (budget=50, single tx), 50-50 → base 50
    # → Bob owes 25€ to Alice; Alice (payer) owes nothing.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
        budget_amount=5000,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    by_debtor = await _overflow_by_debtor(household_singleton, sc.tx)
    assert by_debtor == {sc.members["bob"]: 2500}
    assert all(d.to_user_id == sc.payer for d in await _overflow_debts(household_singleton, sc.tx))


async def test_default_no_budget_full_amount(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # D9: no covering budget → base = full amount (≡ force_full_debt).
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
        budget_amount=None,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    assert await _overflow_by_debtor(household_singleton, sc.tx) == {sc.members["bob"]: 5000}


async def test_force_full_debt_with_budget(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # AC: force_full_debt → base = total (budget ignored). Bob owes 50€ of a 100€.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
        budget_amount=50000,
        override="force_full_debt",
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    assert await _overflow_by_debtor(household_singleton, sc.tx) == {sc.members["bob"]: 5000}


async def test_force_no_debt_never_materialises(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # AC: force_no_debt → no overflow debt even when the budget is exceeded.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
        budget_amount=1000,
        override="force_no_debt",
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    assert await _overflow_debts(household_singleton, sc.tx) == []


async def test_idempotent_redispatch(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # AC idempotence: a second dispatch of the same event → identical debt set
    # (ON CONFLICT DO UPDATE), no duplicate rows.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
        budget_amount=5000,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    first = await _overflow_by_debtor(household_singleton, sc.tx)
    await materialize_overflow(
        household_singleton, TransactionConfirmedEvent(transaction_id=sc.tx, account_id=sc.account)
    )
    assert (
        await _overflow_by_debtor(household_singleton, sc.tx) == first == {sc.members["bob"]: 2500}
    )


async def test_conservation_multi_tx(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # KEY (D7): budget=100, two `default` tx A=100 and B=100 on the same
    # budget/period/category → Σ overflow == max(0, ΣM − budget) (= 100), NOT 200.
    # Bob's ratio is 1.0 so Σ debt == Σ base. The two tx carry DISTINCT dates so
    # the ordered window `(date, id)` is deterministic: the EARLIER tx (A) sees the
    # full budget remaining → 0 overflow; the LATER tx (B) sees the budget already
    # consumed → carries the whole 100 excess. We pin both the total AND the
    # ordered repartition (which line bears the overflow), not just the sum.
    earlier = dt.date(2026, 6, 10)  # strictly before `_TODAY` in the period window
    user_factory, account_factory, _ = await bound_account_factories()

    def _do(s: Session) -> tuple[UUID, UUID, UUID, UUID]:
        alice = user_factory(email=f"a-{uuid4().hex[:8]}@e.com").id
        bob = user_factory(email=f"b-{uuid4().hex[:8]}@e.com").id
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
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        _make_budget(
            s,
            category_id=cat.id,
            created_by=alice,
            amount_cents=10000,
            contributor_ids=(alice, bob),
        )
        tx_a = _add_expense(
            s, account_id=account.id, category_id=cat.id, amount=10000, created_by=alice, on=earlier
        )
        tx_b = _add_expense(
            s, account_id=account.id, category_id=cat.id, amount=10000, created_by=alice, on=_TODAY
        )
        return bob, account.id, tx_a, tx_b

    bob, account_id, tx_a, tx_b = await household_singleton.run_sync(_do)
    # Both already `confirmed` in the seed; materialise each independently.
    for tx in (tx_a, tx_b):
        await materialize_overflow(
            household_singleton,
            TransactionConfirmedEvent(transaction_id=tx, account_id=account_id),
        )

    # Ordered repartition: A (earlier) bears nothing, B (later) bears the full excess.
    assert await _overflow_by_debtor(household_singleton, tx_a) == {}
    assert await _overflow_by_debtor(household_singleton, tx_b) == {bob: 10000}

    total = (
        await household_singleton.execute(
            select(func.coalesce(func.sum(Debt.amount_cents), 0)).where(
                Debt.origin == _OVERFLOW, Debt.from_user_id == bob
            )
        )
    ).scalar_one()
    assert total == 10000  # max(0, (100+100) − 100), NOT 200


async def test_conservation_multi_tx_via_service_flow(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # Conservation (D7) driven through the REAL service flow: two `planned` `default`
    # tx (A earlier, B later) on the same budget=100/period/category are each confirmed
    # via `transition_to_confirmed` (→ dispatch → materialize_overflow), NOT a manual
    # handler call. Σ overflow must still be max(0, ΣM − budget) = 100 with the ordered
    # repartition (A bears 0, B bears the whole excess) — proving the ordered-window
    # conservation holds end-to-end, not only under a direct handler dispatch.
    earlier = dt.date(2026, 6, 10)  # strictly before `_TODAY` in the period window
    user_factory, account_factory, _ = await bound_account_factories()

    def _do(s: Session) -> tuple[UUID, UUID, UUID, UUID]:
        alice = user_factory(email=f"a-{uuid4().hex[:8]}@e.com").id
        bob = user_factory(email=f"b-{uuid4().hex[:8]}@e.com").id
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
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        _make_budget(
            s,
            category_id=cat.id,
            created_by=alice,
            amount_cents=10000,
            contributor_ids=(alice, bob),
        )
        tx_a = _add_expense(
            s,
            account_id=account.id,
            category_id=cat.id,
            amount=10000,
            created_by=alice,
            state="planned",
            on=earlier,
        )
        tx_b = _add_expense(
            s,
            account_id=account.id,
            category_id=cat.id,
            amount=10000,
            created_by=alice,
            state="planned",
            on=_TODAY,
        )
        return bob, account.id, tx_a, tx_b

    bob, _account_id, tx_a, tx_b = await household_singleton.run_sync(_do)
    # Confirm in chronological order through the real lifecycle service (fires the bus).
    for tx in (tx_a, tx_b):
        await transition_to_confirmed(household_singleton, tx_id=tx)

    assert await _overflow_by_debtor(household_singleton, tx_a) == {}  # earlier: full budget left
    assert await _overflow_by_debtor(household_singleton, tx_b) == {bob: 10000}  # later: all excess
    total = (
        await household_singleton.execute(
            select(func.coalesce(func.sum(Debt.amount_cents), 0)).where(
                Debt.origin == _OVERFLOW, Debt.from_user_id == bob
            )
        )
    ).scalar_one()
    assert total == 10000  # conserved end-to-end: max(0, (100+100) − 100), NOT 200


async def test_single_tx_overflow_non_regression(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # A single `default` tx exceeding on its own sees the FULL budget remaining
    # (no prior tx) → base = M − budget.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("1"), "bob": Decimal("1")},
        amount=10000,
        budget_amount=3000,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    assert await _overflow_by_debtor(household_singleton, sc.tx) == {sc.members["bob"]: 7000}


async def test_prune_stale_on_override_switch(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # D4: a debt created under force_full_debt is PRUNED when a re-materialisation
    # finds it stale (here the override flips to force_no_debt → kept = ∅).
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
        budget_amount=None,
        override="force_full_debt",
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    assert len(await _overflow_debts(household_singleton, sc.tx)) == 1

    # Flip the override column directly, then re-materialise → prune to empty.
    await household_singleton.execute(
        update(Transaction)
        .where(Transaction.id == sc.tx)
        .values(debt_generation_override="force_no_debt")
    )
    await materialize_overflow(
        household_singleton, TransactionConfirmedEvent(transaction_id=sc.tx, account_id=sc.account)
    )
    assert await _overflow_debts(household_singleton, sc.tx) == []


# ---------------------------------------------------------------------------
# P11.3.2 — isolation & edge cases
# ---------------------------------------------------------------------------


async def test_personal_account_ignored(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # AC: a tx on a personal account → no overflow (members is None).
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("1")},
        amount=10000,
        budget_amount=None,
        personal_account=True,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    assert await _overflow_debts(household_singleton, sc.tx) == []


async def test_archived_shared_account_ignored(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # An archived shared account → members is None → no overflow (D2/§4.1).
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
        budget_amount=None,
        archived_account=True,
    )
    await materialize_overflow(
        household_singleton, TransactionConfirmedEvent(transaction_id=sc.tx, account_id=sc.account)
    )
    assert await _overflow_debts(household_singleton, sc.tx) == []


async def test_transfer_no_debt(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # A transfer (no classification leg) → expense_total ≤ 0 → no overflow (D5).
    user_factory, account_factory, _ = await bound_account_factories()

    def _do(s: Session) -> tuple[UUID, UUID]:
        alice = user_factory(email=f"a-{uuid4().hex[:8]}@e.com").id
        bob = user_factory(email=f"b-{uuid4().hex[:8]}@e.com").id
        src = account_factory(owner_id=None, name="Commun")
        dst = account_factory(owner_id=None, name="Commun2")
        for acc in (src, dst):
            s.add_all(
                [
                    AccountMember(
                        account_id=acc.id, user_id=alice, default_share_ratio=Decimal("0.5")
                    ),
                    AccountMember(
                        account_id=acc.id, user_id=bob, default_share_ratio=Decimal("0.5")
                    ),
                ]
            )
        s.flush()
        tx = _add_expense(
            s,
            account_id=src.id,
            category_id=None,
            amount=10000,
            created_by=alice,
            transfer_account_id=dst.id,
        )
        return src.id, tx

    account_id, tx_id = await household_singleton.run_sync(_do)
    await materialize_overflow(
        household_singleton, TransactionConfirmedEvent(transaction_id=tx_id, account_id=account_id)
    )
    assert await _overflow_debts(household_singleton, tx_id) == []


async def test_three_unequal_members(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # 3 members, payer excluded, unequal ratios (Bob 0.3 / Carol 0.2) on a full
    # base of 1000€ (no budget) → Bob 300€, Carol 200€, Alice none.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.3"), "carol": Decimal("0.2")},
        amount=100000,
        budget_amount=None,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    assert await _overflow_by_debtor(household_singleton, sc.tx) == {
        sc.members["bob"]: 30000,
        sc.members["carol"]: 20000,
    }


async def test_sum_ratios_not_one(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # The domain does NOT require Σ ratio == 1: Bob (0.9) on a full base of 100€
    # owes 90€ (overflow ≠ base, by construction) — freeze the behaviour.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.9")},
        amount=10000,
        budget_amount=None,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    assert await _overflow_by_debtor(household_singleton, sc.tx) == {sc.members["bob"]: 9000}


async def test_rounding_degenerate_line_pruned(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # A member whose share rounds to ≤ 0 cent (Bob 0.0001 of base 1¢ → 0) is
    # OMITTED by the domain and PRUNED if it had a prior row.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("1"), "bob": Decimal("0.0001")},
        amount=1,
        budget_amount=None,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    assert await _overflow_debts(household_singleton, sc.tx) == []


async def test_origin_exclusivity_share_request_untouched(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # AC opposable: a personal_share_request debt on the SAME (tx, from, to) is
    # never touched by the overflow upsert/prune (partial-predicate exclusivity).
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
        budget_amount=None,
    )
    bob = sc.members["bob"]

    def _add_sr_debt(s: Session) -> UUID:
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

    sr_debt_id = await household_singleton.run_sync(_add_sr_debt)
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    # Re-materialise once more (upsert + prune) to stress the exclusivity.
    await materialize_overflow(
        household_singleton, TransactionConfirmedEvent(transaction_id=sc.tx, account_id=sc.account)
    )

    sr = (await household_singleton.execute(select(Debt).where(Debt.id == sr_debt_id))).scalar_one()
    assert sr.amount_cents == 777 and sr.origin == "personal_share_request"
    assert await _overflow_by_debtor(household_singleton, sc.tx) == {bob: 5000}


async def test_personal_budget_not_applied_to_shared_expense(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # D8: a `personal` budget never covers a shared-account expense (the shared
    # account is not among the owner's eligible accounts) → resolver returns None
    # → base = full amount.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("1"), "bob": Decimal("1")},
        amount=10000,
        budget_amount=5000,
        personal_budget=True,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    # Full amount (budget ignored) → 100€, not 50€.
    assert await _overflow_by_debtor(household_singleton, sc.tx) == {sc.members["bob"]: 10000}


async def test_child_budget_chosen_over_parent(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # D8: the MOST SPECIFIC budget wins. Budget on child C (amount 50) and on
    # parent P (amount 10000); expense on C, M=100 → base uses C (50) → Bob 50€.
    # If the parent had been chosen, base = max(0, 100 − 10000) = 0 → no debt.
    user_factory, account_factory, _ = await bound_account_factories()

    def _do(s: Session) -> tuple[UUID, UUID, UUID]:
        alice = user_factory(email=f"a-{uuid4().hex[:8]}@e.com").id
        bob = user_factory(email=f"b-{uuid4().hex[:8]}@e.com").id
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
        s.add(parent)
        s.flush()
        child = Category(name="Child", parent_id=parent.id)
        s.add(child)
        s.flush()
        _make_budget(
            s,
            category_id=parent.id,
            created_by=alice,
            amount_cents=1000000,
            contributor_ids=(alice, bob),
        )
        _make_budget(
            s,
            category_id=child.id,
            created_by=alice,
            amount_cents=5000,
            contributor_ids=(alice, bob),
        )
        tx = _add_expense(
            s, account_id=account.id, category_id=child.id, amount=10000, created_by=alice
        )
        return account.id, bob, tx

    account_id, bob, tx_id = await household_singleton.run_sync(_do)
    await materialize_overflow(
        household_singleton, TransactionConfirmedEvent(transaction_id=tx_id, account_id=account_id)
    )
    assert await _overflow_by_debtor(household_singleton, tx_id) == {bob: 5000}


# ---------------------------------------------------------------------------
# P11.3.2 — transaction-agnostic (ADR 0015) & wiring
# ---------------------------------------------------------------------------


async def test_handler_failure_after_write_rolls_back(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # ADR 0015 atomicity: the materializer FLUSHES the overflow debts inside the
    # confirm transaction (never commits). A SIBLING async subscriber that raises
    # AFTER `materialize_overflow` (subscribed first by the autouse fixture, so the
    # debts are already flushed) must PROPAGATE out of the confirm; rolling the unit
    # back leaves NO overflow debt. We wrap the confirm in a SAVEPOINT (the tier shares
    # one transaction with the schema DDL, so a full rollback would drop the tables;
    # the SAVEPOINT models what `get_db` does at the request boundary in prod). Had the
    # materializer self-committed, the rows would outlive the SAVEPOINT rollback and
    # this assertion would catch it. `wrote_overflow` first proves the write happened
    # (else the test would be vacuous).
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
        budget_amount=5000,
    )

    wrote_overflow = False

    async def _boom_after(_session: AsyncSession, _event: TransactionConfirmedEvent) -> None:
        nonlocal wrote_overflow
        # The materializer ran first → its overflow debts are flushed and visible.
        wrote_overflow = await _overflow_debts(household_singleton, sc.tx) != []
        raise RuntimeError("injected post-write failure")

    subscribe_async(TransactionConfirmedEvent, _boom_after)
    with pytest.raises(RuntimeError, match="injected post-write failure"):
        async with household_singleton.begin_nested():
            await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    assert wrote_overflow  # the overflow rows WERE flushed before the failure
    # SAVEPOINT rolled back by the propagated exception → no overflow debt persists.
    assert await _overflow_debts(household_singleton, sc.tx) == []


async def test_overflow_handler_makes_no_self_commit(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # ADR 0015 (direct proof): neither the lifecycle service nor the overflow handler
    # may commit — `get_db` owns the transaction boundary. Spy on the session's
    # `commit`; a REAL confirm that materialises overflow debts must leave the commit
    # count at ZERO (the debts are persisted by FLUSH only).
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
        budget_amount=5000,
    )
    commits = 0
    real_commit = household_singleton.commit

    async def _counting_commit(*args: object, **kwargs: object) -> None:
        nonlocal commits
        commits += 1
        await real_commit(*args, **kwargs)

    monkeypatch.setattr(household_singleton, "commit", _counting_commit)
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    assert await _overflow_by_debtor(household_singleton, sc.tx) == {sc.members["bob"]: 2500}
    assert commits == 0


async def test_confirm_wiring_end_to_end(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # The REAL confirm flow (transition_to_confirmed → dispatch → handler)
    # materialises the overflow — pins the composition-root wiring is load-bearing.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
        budget_amount=5000,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    assert await _overflow_by_debtor(household_singleton, sc.tx) == {sc.members["bob"]: 2500}


# ---------------------------------------------------------------------------
# P11.3.3 — void
# ---------------------------------------------------------------------------


async def test_void_removes_overflow(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # AC + D14 regression: the REAL void() flow (not a manual dispatch) deletes
    # the tx's overflow debts — proving the publish→dispatch switch is in place.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
        budget_amount=None,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    assert await _overflow_debts(household_singleton, sc.tx) != []
    await void(household_singleton, tx_id=sc.tx, reason="erreur de saisie")
    assert await _overflow_debts(household_singleton, sc.tx) == []


async def test_void_keeps_share_request_debt(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # AC opposable: void deletes overflow but leaves a personal_share_request debt
    # on the same source_transaction_id intact.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
        budget_amount=None,
    )
    bob = sc.members["bob"]

    def _add_sr_debt(s: Session) -> UUID:
        d = Debt(
            from_user_id=bob,
            to_user_id=sc.payer,
            amount_cents=321,
            currency="EUR",
            account_id=sc.account,
            source_transaction_id=sc.tx,
            origin="personal_share_request",
        )
        s.add(d)
        s.flush()
        return d.id

    sr_id = await household_singleton.run_sync(_add_sr_debt)
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    await void(household_singleton, tx_id=sc.tx, reason="x")

    assert await _overflow_debts(household_singleton, sc.tx) == []
    sr = (await household_singleton.execute(select(Debt).where(Debt.id == sr_id))).scalar_one()
    assert sr.origin == "personal_share_request" and sr.amount_cents == 321


async def test_void_without_overflow_is_noop(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # void deleting 0 overflow rows raises no error.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
        budget_amount=None,
        override="force_no_debt",
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    await void(household_singleton, tx_id=sc.tx, reason="x")  # no error
    assert await _overflow_debts(household_singleton, sc.tx) == []


async def test_void_handler_failure_propagates(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # Safety property (lifecycle.void docstring, D14): a void async handler that
    # raises PROPAGATES out of void() — so `get_db` rolls the WHOLE void back (no tx
    # left voided with stale/orphaned overflow). `void` switched publish→dispatch
    # precisely so async handlers fire AND their failures are load-bearing. We assert
    # not only that the exception escapes, but the actual TRANSACTIONAL consequence:
    # after the rollback the tx is NOT left voided and its overflow debts survive.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("0.5"), "bob": Decimal("0.5")},
        amount=10000,
        budget_amount=None,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    assert await _overflow_debts(household_singleton, sc.tx) != []

    async def _boom(_session: AsyncSession, _event: TransactionVoidedEvent) -> None:
        raise RuntimeError("injected void handler failure")

    subscribe_async(TransactionVoidedEvent, _boom)
    # SAVEPOINT models the `get_db` request boundary (the tier shares one transaction
    # with the schema DDL, so a full rollback would drop the tables). The propagated
    # failure rolls the whole void back inside it. `remove_overflow_on_void` is
    # subscribed first (autouse fixture), so it already deleted the overflow rows
    # before `_boom` raised — their survival below proves the delete was undone too.
    with pytest.raises(RuntimeError, match="injected void handler failure"):
        async with household_singleton.begin_nested():
            await void(household_singleton, tx_id=sc.tx, reason="boom")
    state = (
        await household_singleton.execute(select(Transaction.state).where(Transaction.id == sc.tx))
    ).scalar_one()
    assert state == "confirmed"  # void rolled back — tx not left in a voided state
    assert await _overflow_debts(household_singleton, sc.tx) != []  # overflow rows survived


async def test_common_account_without_members_no_debt(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # A LIVE shared account with NO member yields `[]` (not None) from
    # `shared_account_members_with_ratios` → the materializer computes zero overflow
    # debts (no debtor) and persists nothing. Distinct from the personal/archived
    # no-op (`members is None`): here the account exists but has no quote-part holder.
    user_factory, account_factory, _ = await bound_account_factories()

    def _do(s: Session) -> tuple[UUID, UUID]:
        alice = user_factory(email=f"nm-{uuid4().hex[:8]}@e.com").id
        account = account_factory(owner_id=None, name="Commun sans membre")
        cat = Category(name="Courses")
        s.add(cat)
        s.flush()
        tx = _add_expense(
            s, account_id=account.id, category_id=cat.id, amount=10000, created_by=alice
        )
        return account.id, tx

    account_id, tx = await household_singleton.run_sync(_do)
    await materialize_overflow(
        household_singleton, TransactionConfirmedEvent(transaction_id=tx, account_id=account_id)
    )
    assert await _overflow_debts(household_singleton, tx) == []


# ---------------------------------------------------------------------------
# P11.3.4 — override edit re-materialisation
# ---------------------------------------------------------------------------


async def test_edit_default_to_force_full_debt_increases(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # AC: default (base = excess) → force_full_debt (base = total) increases debts.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("1"), "bob": Decimal("1")},
        amount=10000,
        budget_amount=3000,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    assert await _overflow_by_debtor(household_singleton, sc.tx) == {sc.members["bob"]: 7000}
    await update_editable_fields(
        household_singleton, tx_id=sc.tx, debt_generation_override="force_full_debt"
    )
    assert await _overflow_by_debtor(household_singleton, sc.tx) == {sc.members["bob"]: 10000}


async def test_edit_default_to_force_no_debt_removes(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # AC: default → force_no_debt removes the overflow debts (prune D4).
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("1"), "bob": Decimal("1")},
        amount=10000,
        budget_amount=3000,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    assert await _overflow_debts(household_singleton, sc.tx) != []
    await update_editable_fields(
        household_singleton, tx_id=sc.tx, debt_generation_override="force_no_debt"
    )
    assert await _overflow_debts(household_singleton, sc.tx) == []


async def test_edit_force_no_debt_to_default_recreates(
    household_singleton: AsyncSession, bound_account_factories: FactoryBundle
) -> None:
    # AC: force_no_debt → default (budget exceeded) recreates the debts.
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("1"), "bob": Decimal("1")},
        amount=10000,
        budget_amount=3000,
        override="force_no_debt",
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    assert await _overflow_debts(household_singleton, sc.tx) == []
    await update_editable_fields(
        household_singleton, tx_id=sc.tx, debt_generation_override="default"
    )
    assert await _overflow_by_debtor(household_singleton, sc.tx) == {sc.members["bob"]: 7000}


async def test_edit_non_override_field_no_churn(
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A non-override editable field (description) → the edit handler's guard
    # SHORT-CIRCUITS before the re-materialisation path runs (no churn). Spy on the
    # materializer's `get_transaction` (the first DB read of `_materialize_for_tx`):
    # it must NOT fire for this edit — proving the path was skipped, not merely that
    # the resulting state happened to be unchanged (the prior assertion-on-state was
    # consistent even with a redundant recompute).
    sc = await _seed(
        household_singleton,
        bound_account_factories,
        member_ratios={"alice": Decimal("1"), "bob": Decimal("1")},
        amount=10000,
        budget_amount=3000,
    )
    await transition_to_confirmed(household_singleton, tx_id=sc.tx)
    before = await _overflow_by_debtor(household_singleton, sc.tx)

    materialize_path_reads = 0
    real_get_transaction = _materializer_module.get_transaction

    async def _spy_get_transaction(*args: object, **kwargs: object) -> object:
        nonlocal materialize_path_reads
        materialize_path_reads += 1
        return await real_get_transaction(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(_materializer_module, "get_transaction", _spy_get_transaction)
    await update_editable_fields(household_singleton, tx_id=sc.tx, description="note libre")
    assert materialize_path_reads == 0  # handler returned before `_materialize_for_tx`
    assert (
        await _overflow_by_debtor(household_singleton, sc.tx) == before == {sc.members["bob"]: 7000}
    )


# ---------------------------------------------------------------------------
# D15 — Hypothesis properties (conservation + idempotence), isolated engine
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def overflow_socle(postgres_container) -> Iterator[str]:  # pyright: ignore[reportUnusedFunction]
    """Schema created ONCE (gabarit `archive_socle`), `drop_all` at teardown.

    Module-scoped ⇒ no `HealthCheck.function_scoped_fixture` on the Hypothesis
    re-run. Each example seeds its own household/users/account/budget/txs in a
    transaction and ROLLS BACK — nothing persists across examples.
    """
    url = postgres_container.get_connection_url()

    async def _setup() -> None:
        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        finally:
            await engine.dispose()

    async def _teardown() -> None:
        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
        finally:
            await engine.dispose()

    asyncio.run(_setup())
    yield url
    asyncio.run(_teardown())


def _seed_period_sync(
    s: Session, *, amounts: list[int], budget_amount: int
) -> tuple[UUID, UUID, list[UUID]]:
    """Seed a shared account (Alice payer, Bob debtor ratio 1.0), a covering budget,
    and one confirmed `default` expense per amount. Returns (account_id, bob, tx_ids)."""
    s.add(Household(name="H", base_currency="EUR"))
    s.flush()
    alice, bob = uuid4(), uuid4()
    s.add_all(
        [
            User(
                id=alice,
                email=f"a-{alice.hex[:8]}@e.com",
                password_hash="x",
                display_name="A",
                role="member",
            ),
            User(
                id=bob,
                email=f"b-{bob.hex[:8]}@e.com",
                password_hash="x",
                display_name="B",
                role="member",
            ),
        ]
    )
    s.flush()
    account = Account(name="Commun", type="courant", currency="EUR", owner_id=None)
    s.add(account)
    s.flush()
    s.add_all(
        [
            AccountMember(account_id=account.id, user_id=alice, default_share_ratio=Decimal("1")),
            AccountMember(account_id=account.id, user_id=bob, default_share_ratio=Decimal("1")),
        ]
    )
    cat = Category(name="Courses")
    s.add(cat)
    s.flush()
    _make_budget(
        s,
        category_id=cat.id,
        created_by=alice,
        amount_cents=budget_amount,
        contributor_ids=(alice, bob),
    )
    tx_ids = [
        _add_expense(s, account_id=account.id, category_id=cat.id, amount=m, created_by=alice)
        for m in amounts
    ]
    return account.id, bob, tx_ids


@given(
    amounts=st.lists(st.integers(min_value=1, max_value=100000), min_size=1, max_size=5),
    budget_amount=st.integers(min_value=1, max_value=100000),
)
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_conservation_property(overflow_socle: str, amounts: list[int], budget_amount: int) -> None:
    # ∀ N tx on one budget/period: Σ overflow == max(0, ΣM − budget) (Bob ratio
    # 1.0 ⇒ Σ debt == Σ base). Reveals any double-counting regression (D7/D15).
    url = overflow_socle

    async def _run() -> None:
        engine = create_async_engine(url)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as s:
                await s.begin()
                account_id, bob, tx_ids = await s.run_sync(
                    lambda sync: _seed_period_sync(
                        sync, amounts=amounts, budget_amount=budget_amount
                    )
                )
                for tx in tx_ids:
                    await materialize_overflow(
                        s, TransactionConfirmedEvent(transaction_id=tx, account_id=account_id)
                    )
                total = (
                    await s.execute(
                        select(func.coalesce(func.sum(Debt.amount_cents), 0)).where(
                            Debt.origin == _OVERFLOW, Debt.from_user_id == bob
                        )
                    )
                ).scalar_one()
                assert total == max(0, sum(amounts) - budget_amount)
                await s.rollback()
        finally:
            await engine.dispose()

    asyncio.run(_run())


@given(
    amounts=st.lists(st.integers(min_value=1, max_value=100000), min_size=1, max_size=4),
    budget_amount=st.integers(min_value=1, max_value=100000),
)
@settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_idempotence_property(overflow_socle: str, amounts: list[int], budget_amount: int) -> None:
    # dispatch∘dispatch == dispatch: a second materialisation of every tx leaves
    # the overflow debt set byte-identical (ON CONFLICT DO UPDATE + prune).
    url = overflow_socle

    async def _run() -> None:
        engine = create_async_engine(url)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as s:
                await s.begin()
                account_id, _bob, tx_ids = await s.run_sync(
                    lambda sync: _seed_period_sync(
                        sync, amounts=amounts, budget_amount=budget_amount
                    )
                )
                events = [
                    TransactionConfirmedEvent(transaction_id=tx, account_id=account_id)
                    for tx in tx_ids
                ]
                for ev in events:
                    await materialize_overflow(s, ev)

                async def _snapshot() -> set[tuple[UUID, UUID, UUID, int]]:
                    rows = await s.execute(
                        select(
                            Debt.source_transaction_id,
                            Debt.from_user_id,
                            Debt.to_user_id,
                            Debt.amount_cents,
                        ).where(Debt.origin == _OVERFLOW)
                    )
                    return {(r[0], r[1], r[2], r[3]) for r in rows.all()}

                first = await _snapshot()
                for ev in events:
                    await materialize_overflow(s, ev)
                assert await _snapshot() == first
                await s.rollback()
        finally:
            await engine.dispose()

    asyncio.run(_run())


@given(
    amount=st.integers(min_value=1, max_value=1_000_000),
    r_bob=st.decimals(min_value=Decimal("0.0001"), max_value=Decimal("1"), places=4),
    r_carol=st.decimals(min_value=Decimal("0.0001"), max_value=Decimal("1"), places=4),
)
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_multi_member_materialisation_matches_domain(
    overflow_socle: str, amount: int, r_bob: Decimal, r_carol: Decimal
) -> None:
    # Multi-debtor effectful-path fidelity (D15 gap): with TWO non-payer members at
    # ARBITRARY quote-parts and NO budget (base = full amount, D9), the PERSISTED
    # overflow debts must equal EXACTLY the pure domain projection per member —
    # `Money(amount).apply_ratio(ratio)`, a line dropped when it rounds to ≤ 0 cent.
    # Scope note: the oracle below REUSES `apply_ratio` (the domain's own function), so
    # this does NOT independently re-verify the ROUND_HALF_UP rule — that is owned by
    # the `money.py` unit tests. What it pins is that the effectful plumbing (member
    # load, payer exclusion, ratio→debt mapping, upsert, currency) faithfully mirrors
    # `compute_for_overflow`; the conservation property only ever uses a single
    # ratio=1.0 debtor and never exercises this multi-member mapping.
    url = overflow_socle
    base = Money(amount, "EUR")

    async def _run() -> None:
        engine = create_async_engine(url)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as s:
                await s.begin()

                def _seed(sync: Session) -> tuple[UUID, UUID, UUID, UUID]:
                    sync.add(Household(name="H", base_currency="EUR"))
                    sync.flush()
                    alice, bob, carol = uuid4(), uuid4(), uuid4()
                    sync.add_all(
                        [
                            User(
                                id=u,
                                email=f"{u.hex[:8]}@e.com",
                                password_hash="x",
                                display_name="X",
                                role="member",
                            )
                            for u in (alice, bob, carol)
                        ]
                    )
                    sync.flush()
                    account = Account(name="Commun", type="courant", currency="EUR", owner_id=None)
                    sync.add(account)
                    sync.flush()
                    sync.add_all(
                        [
                            AccountMember(
                                account_id=account.id,
                                user_id=alice,
                                default_share_ratio=Decimal("1"),
                            ),
                            AccountMember(
                                account_id=account.id, user_id=bob, default_share_ratio=r_bob
                            ),
                            AccountMember(
                                account_id=account.id, user_id=carol, default_share_ratio=r_carol
                            ),
                        ]
                    )
                    cat = Category(name="Courses")
                    sync.add(cat)
                    sync.flush()
                    tx = _add_expense(
                        sync,
                        account_id=account.id,
                        category_id=cat.id,
                        amount=amount,
                        created_by=alice,
                    )
                    return account.id, bob, carol, tx

                account_id, bob, carol, tx = await s.run_sync(_seed)
                await materialize_overflow(
                    s, TransactionConfirmedEvent(transaction_id=tx, account_id=account_id)
                )

                rows = await s.execute(
                    select(Debt.from_user_id, Debt.amount_cents).where(
                        Debt.origin == _OVERFLOW, Debt.source_transaction_id == tx
                    )
                )
                persisted = {uid: cents for uid, cents in rows.all()}
                expected = {
                    uid: base.apply_ratio(ratio).amount_cents
                    for uid, ratio in ((bob, r_bob), (carol, r_carol))
                    if base.apply_ratio(ratio).amount_cents > 0
                }
                assert persisted == expected
                await s.rollback()
        finally:
            await engine.dispose()

    asyncio.run(_run())
