"""Integration tests for the remaining-balance primitives (S10.3, P10.3.1).

Drives `compute_remaining` and `list_open_debts_between` against a real Postgres
(testcontainers): the `remaining = debt.amount_cents − Σ settlement_lines` formula
(never materialised, ADR 0011), the `DebtNotFoundError` on a missing debt
(≠ remaining 0), the symmetric/oriented listing of OPEN debts only, the
deterministic order, third-party + cross-debt isolation, the cross-settlement
aggregation invariant, and — crucially — the NON-clamped negative remaining when
an over-settlement somehow slipped past the validator (D2).

Seed helpers (`_make_account`/`_make_transaction`/`_make_debt`/`_make_settlement`/
`_make_line`) follow the inline gabarit of `test_settlement_models.py` (those live
under a `test_` module and are not importable cleanly).
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.domain import AccountType
from backend.modules.accounts.models import Account
from backend.modules.auth.models import User
from backend.modules.debts.models import Debt, Settlement, SettlementLine
from backend.modules.debts.public import (
    DebtNotFoundError,
    compute_remaining,
    list_open_debts_between,
)
from backend.modules.transactions.models import Transaction

# Every test inserts an `Account`, whose `household_id` FK requires the singleton
# `household` row to exist (ADR 0010); seed it for the whole module.
pytestmark = pytest.mark.usefixtures("household_singleton")

HOUSEHOLD_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

UserFactory = Callable[..., Awaitable[User]]


async def _make_account(session: AsyncSession, owner_id: uuid.UUID) -> uuid.UUID:
    account = Account(
        name="Compte courant",
        type=AccountType.COURANT,
        currency="EUR",
        owner_id=owner_id,
    )
    session.add(account)
    await session.flush()
    return account.id


async def _make_transaction(
    session: AsyncSession, *, account_id: uuid.UUID, created_by: uuid.UUID
) -> uuid.UUID:
    tx = Transaction(
        account_id=account_id,
        date=dt.date(2026, 6, 1),
        state="confirmed",
        created_by=created_by,
    )
    session.add(tx)
    await session.flush()
    return tx.id


async def _make_debt(  # noqa: PLR0913 — keyword-only seed helper
    session: AsyncSession,
    *,
    from_user_id: uuid.UUID,
    to_user_id: uuid.UUID,
    account_id: uuid.UUID,
    source_transaction_id: uuid.UUID,
    amount_cents: int = 5000,
    currency: str = "EUR",
    origin: str = "personal_share_request",
) -> Debt:
    debt = Debt(
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        amount_cents=amount_cents,
        currency=currency,
        account_id=account_id,
        source_transaction_id=source_transaction_id,
        origin=origin,
    )
    session.add(debt)
    await session.flush()
    return debt


async def _make_settlement(session: AsyncSession, *, created_by: uuid.UUID) -> Settlement:
    # `virtual` (no linked tx) keeps the seed self-contained — the remaining
    # formula is orthogonal to the settlement `type`.
    settlement = Settlement(
        household_id=HOUSEHOLD_ID,
        created_by=created_by,
        type="virtual",
        linked_transaction_id=None,
        settled_at=dt.date(2026, 6, 3),
    )
    session.add(settlement)
    await session.flush()
    return settlement


async def _make_line(
    session: AsyncSession,
    *,
    settlement_id: uuid.UUID,
    debt_id: uuid.UUID,
    amount_cents: int,
    currency: str = "EUR",
) -> SettlementLine:
    line = SettlementLine(
        settlement_id=settlement_id,
        debt_id=debt_id,
        amount_cents=amount_cents,
        currency=currency,
    )
    session.add(line)
    await session.flush()
    return line


async def _seed_debt(
    session: AsyncSession,
    *,
    from_user_id: uuid.UUID,
    to_user_id: uuid.UUID,
    amount_cents: int = 5000,
    currency: str = "EUR",
) -> Debt:
    """Full debt with its own source account + transaction (owned by the creditor)."""
    account_id = await _make_account(session, to_user_id)
    tx_id = await _make_transaction(session, account_id=account_id, created_by=to_user_id)
    return await _make_debt(
        session,
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        account_id=account_id,
        source_transaction_id=tx_id,
        amount_cents=amount_cents,
        currency=currency,
    )


# ---------------------------------------------------------------------------
# compute_remaining
# ---------------------------------------------------------------------------


async def test_remaining_equals_amount_without_lines(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (i) no settlement line → remaining == amount.
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    debt = await _seed_debt(
        household_singleton, from_user_id=debtor.id, to_user_id=creditor.id, amount_cents=5000
    )

    assert await compute_remaining(household_singleton, debt_id=debt.id) == 5000


async def test_remaining_subtracts_one_partial_line(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (ii) one partial line → remaining == amount − line (5000 − 3000 = 2000).
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    debt = await _seed_debt(
        household_singleton, from_user_id=debtor.id, to_user_id=creditor.id, amount_cents=5000
    )
    s = await _make_settlement(household_singleton, created_by=creditor.id)
    await _make_line(household_singleton, settlement_id=s.id, debt_id=debt.id, amount_cents=3000)

    assert await compute_remaining(household_singleton, debt_id=debt.id) == 2000


async def test_remaining_subtracts_n_lines_same_settlement(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (iii) N lines (same debt, same settlement) → remaining == amount − Σ.
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    debt = await _seed_debt(
        household_singleton, from_user_id=debtor.id, to_user_id=creditor.id, amount_cents=5000
    )
    s = await _make_settlement(household_singleton, created_by=creditor.id)
    await _make_line(household_singleton, settlement_id=s.id, debt_id=debt.id, amount_cents=1000)
    await _make_line(household_singleton, settlement_id=s.id, debt_id=debt.id, amount_cents=1500)

    assert await compute_remaining(household_singleton, debt_id=debt.id) == 2500


async def test_remaining_cross_settlement_aggregation(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (xii) a debt cleared by ONE line of S1 + ONE line of S2 (two distinct
    # parents) → remaining == amount − (l1 + l2). Locks that `_settled_subq`
    # aggregates CROSS-settlement (no `settlement_id` filter) — the central S10.3
    # invariant.
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    debt = await _seed_debt(
        household_singleton, from_user_id=debtor.id, to_user_id=creditor.id, amount_cents=5000
    )
    s1 = await _make_settlement(household_singleton, created_by=creditor.id)
    s2 = await _make_settlement(household_singleton, created_by=creditor.id)
    await _make_line(household_singleton, settlement_id=s1.id, debt_id=debt.id, amount_cents=2000)
    await _make_line(household_singleton, settlement_id=s2.id, debt_id=debt.id, amount_cents=3000)

    assert await compute_remaining(household_singleton, debt_id=debt.id) == 0


async def test_remaining_zero_when_fully_settled_and_excluded_from_open(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (iv) fully settled (Σ == amount) → remaining 0 AND excluded from
    # list_open_debts_between (HAVING remaining > 0).
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    debt = await _seed_debt(
        household_singleton, from_user_id=debtor.id, to_user_id=creditor.id, amount_cents=5000
    )
    s = await _make_settlement(household_singleton, created_by=creditor.id)
    await _make_line(household_singleton, settlement_id=s.id, debt_id=debt.id, amount_cents=5000)

    assert await compute_remaining(household_singleton, debt_id=debt.id) == 0
    open_debts = await list_open_debts_between(
        household_singleton, user_a=debtor.id, user_b=creditor.id
    )
    assert open_debts == []  # settled debt is excluded


async def test_compute_remaining_raises_on_missing_debt(
    household_singleton: AsyncSession,
) -> None:
    # (v) a random (non-existent) debt_id → DebtNotFoundError (≠ remaining 0).
    with pytest.raises(DebtNotFoundError):
        await compute_remaining(household_singleton, debt_id=uuid.uuid4())


async def test_remaining_not_clamped_on_over_settlement(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (vii) over-settlement inserted directly in DB (bypassing the validator):
    # Σ lines > amount → remaining is the REAL negative value, not 0 (D2). A
    # clamp would mask a bug; over-settlement is prevented at the boundary, not
    # corrected at read.
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    debt = await _seed_debt(
        household_singleton, from_user_id=debtor.id, to_user_id=creditor.id, amount_cents=5000
    )
    s = await _make_settlement(household_singleton, created_by=creditor.id)
    await _make_line(household_singleton, settlement_id=s.id, debt_id=debt.id, amount_cents=8000)

    assert await compute_remaining(household_singleton, debt_id=debt.id) == -3000


async def test_lines_of_other_debt_do_not_affect_remaining(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (x) lines of a second debt D2 do not alter D1's remaining (the correlation
    # `sl.debt_id = debts.id` is correct).
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    d1 = await _seed_debt(
        household_singleton, from_user_id=debtor.id, to_user_id=creditor.id, amount_cents=5000
    )
    d2 = await _seed_debt(
        household_singleton, from_user_id=debtor.id, to_user_id=creditor.id, amount_cents=9000
    )
    s = await _make_settlement(household_singleton, created_by=creditor.id)
    await _make_line(household_singleton, settlement_id=s.id, debt_id=d2.id, amount_cents=3000)

    # Distinct expected remainings (5000 vs 6000) remove any value-collision
    # ambiguity: D1 stays at its full 5000 (untouched), D2 reflects only its OWN
    # line (9000 − 3000 = 6000).
    assert await compute_remaining(household_singleton, debt_id=d1.id) == 5000  # untouched
    assert await compute_remaining(household_singleton, debt_id=d2.id) == 6000  # 9000 − 3000


# ---------------------------------------------------------------------------
# list_open_debts_between
# ---------------------------------------------------------------------------


async def test_list_open_debts_is_symmetric_and_oriented(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (vi) both directions A→B AND B→A surface, orientation (from/to) preserved.
    a, b = await bound_user_factory(), await bound_user_factory()
    a_to_b = await _seed_debt(
        household_singleton, from_user_id=a.id, to_user_id=b.id, amount_cents=3000
    )
    b_to_a = await _seed_debt(
        household_singleton, from_user_id=b.id, to_user_id=a.id, amount_cents=7000
    )

    open_debts = await list_open_debts_between(household_singleton, user_a=a.id, user_b=b.id)
    by_id = {od.debt_id: od for od in open_debts}
    assert set(by_id) == {a_to_b.id, b_to_a.id}
    assert by_id[a_to_b.id].from_user_id == a.id and by_id[a_to_b.id].to_user_id == b.id
    assert by_id[b_to_a.id].from_user_id == b.id and by_id[b_to_a.id].to_user_id == a.id
    # symmetric call returns the same set regardless of argument order.
    swapped = await list_open_debts_between(household_singleton, user_a=b.id, user_b=a.id)
    assert {od.debt_id for od in swapped} == {a_to_b.id, b_to_a.id}


async def test_list_open_debts_carries_remaining_and_currency(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (xi) currency reported AS-IS from the Debt row; remaining is the partial
    # balance. A non-EUR currency ("USD") locks that `OpenDebt.currency` is read
    # from `Debt.currency` and not coincidentally matching a single seeded EUR.
    a, b = await bound_user_factory(), await bound_user_factory()
    debt = await _seed_debt(
        household_singleton, from_user_id=a.id, to_user_id=b.id, amount_cents=5000, currency="USD"
    )
    s = await _make_settlement(household_singleton, created_by=b.id)
    await _make_line(
        household_singleton, settlement_id=s.id, debt_id=debt.id, amount_cents=2000, currency="USD"
    )

    [od] = await list_open_debts_between(household_singleton, user_a=a.id, user_b=b.id)
    assert od.amount_cents == 5000
    assert od.remaining_cents == 3000
    assert od.currency == "USD"


async def test_list_open_debts_excludes_over_settled_debt(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # An over-settled debt (Σ lines > amount → remaining < 0) is NOT "open": the
    # `WHERE remaining > 0` filter excludes it, just like a fully settled one
    # (remaining == 0). Locks the strict `> 0` boundary on the negative side.
    a, b = await bound_user_factory(), await bound_user_factory()
    over = await _seed_debt(
        household_singleton, from_user_id=a.id, to_user_id=b.id, amount_cents=5000
    )
    still_open = await _seed_debt(
        household_singleton, from_user_id=a.id, to_user_id=b.id, amount_cents=4000
    )
    s = await _make_settlement(household_singleton, created_by=b.id)
    await _make_line(household_singleton, settlement_id=s.id, debt_id=over.id, amount_cents=8000)

    # Sanity: the over-settled debt really has a negative remaining (D2).
    assert await compute_remaining(household_singleton, debt_id=over.id) == -3000
    open_debts = await list_open_debts_between(household_singleton, user_a=a.id, user_b=b.id)
    assert [od.debt_id for od in open_debts] == [still_open.id]  # over-settled excluded


async def test_list_open_debts_excludes_third_parties(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (ix) list_open_debts_between(a, b) excludes a→c and b→c (third party c).
    a, b, c = (
        await bound_user_factory(),
        await bound_user_factory(),
        await bound_user_factory(),
    )
    a_to_b = await _seed_debt(
        household_singleton, from_user_id=a.id, to_user_id=b.id, amount_cents=1000
    )
    await _seed_debt(household_singleton, from_user_id=a.id, to_user_id=c.id, amount_cents=2000)
    await _seed_debt(household_singleton, from_user_id=b.id, to_user_id=c.id, amount_cents=3000)

    open_debts = await list_open_debts_between(household_singleton, user_a=a.id, user_b=b.id)
    assert [od.debt_id for od in open_debts] == [a_to_b.id]


async def test_list_open_debts_deterministic_order(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (viii) 4 open debts between {a, b} returned sorted by (created_at, id).
    a, b = await bound_user_factory(), await bound_user_factory()
    d1 = await _seed_debt(
        household_singleton, from_user_id=a.id, to_user_id=b.id, amount_cents=1000
    )
    d2 = await _seed_debt(
        household_singleton, from_user_id=b.id, to_user_id=a.id, amount_cents=2000
    )
    d3 = await _seed_debt(
        household_singleton, from_user_id=a.id, to_user_id=b.id, amount_cents=3000
    )
    # d4 shares d1's created_at → exercises the `id` tiebreaker of the sort.
    d4 = await _seed_debt(
        household_singleton, from_user_id=a.id, to_user_id=b.id, amount_cents=4000
    )
    # Back-date created_at out of insertion order to prove ORDER BY created_at.
    await household_singleton.execute(
        update(Debt)
        .where(Debt.id.in_([d1.id, d4.id]))
        .values(created_at=dt.datetime(2026, 3, 1, tzinfo=dt.UTC))
    )
    await household_singleton.execute(
        update(Debt)
        .where(Debt.id == d2.id)
        .values(created_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC))
    )
    await household_singleton.execute(
        update(Debt)
        .where(Debt.id == d3.id)
        .values(created_at=dt.datetime(2026, 2, 1, tzinfo=dt.UTC))
    )
    await household_singleton.flush()

    open_debts = await list_open_debts_between(household_singleton, user_a=a.id, user_b=b.id)
    # d1 & d4 share created_at (2026-03-01) ⇒ the second sort key `Debt.id`
    # decides their relative order. Dropping `, Debt.id` from ORDER BY would make
    # this tail non-deterministic (UUIDs are random vs insertion order).
    tied_tail = sorted([d1.id, d4.id])
    assert [od.debt_id for od in open_debts] == [d2.id, d3.id, *tied_tail]
