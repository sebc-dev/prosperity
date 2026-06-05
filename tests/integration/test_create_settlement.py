"""Integration tests for `create_settlement` (S10.4, P10.4.1).

Drives the write service against a real Postgres (testcontainers): the 404-first
anti-oracle verification order, the effectful foyer guard (ADR 0011 §4), the pure
`SettlementValidator` propagation (→ the domain error family), the `Σ positive
splits` transfer-amount derivation (D3), the REAL atomicity of the
`Settlement` + N `SettlementLine` insert (failure between the two `flush()`es →
nothing persists), and the foyer-guard reject branch exercised on the REAL path
via a `_resolve_households` monkeypatch (the singleton ADR 0010 makes a second
foyer un-seedable, so the monkeypatch is how the `cross_household_leak` AC is
covered without a second household — plan §6).

Non-virtual paths need transactions WITH splits (`is_transfer` /
`derive_transfer_amount` read `tx.splits`): `_make_transfer_tx` lays a 2-account
funding pair (a real internal transfer), `_make_external_tx` a 1-account
funding/funding pair (no second account ⇒ not a transfer, but a positive Σ ⇒ a
derivable magnitude). Seed gabarit copied inline from `test_settlement_models.py`.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.domain import AccountType
from backend.modules.accounts.models import Account
from backend.modules.auth.models import User
from backend.modules.debts.domain import (
    ClosedDebtError,
    MixedCurrencyError,
    MultipleCounterpartiesError,
    NetTransferMismatchError,
    OverSettlementError,
    SettlementLineInput,
    SettlementValidator,
)
from backend.modules.debts.models import Debt, Settlement, SettlementLine
from backend.modules.debts.public import compute_remaining
from backend.modules.debts.service import settlement as settlement_svc
from backend.modules.debts.service.settlement import (
    CrossHouseholdError,
    LinkedTransactionNotAccessibleError,
    LinkedTransactionNotConfirmedError,
    LinkedTransactionNotTransferError,
    SettlementDebtNotAccessibleError,
    create_settlement,
)
from backend.modules.transactions.models import Split, Transaction

pytestmark = pytest.mark.usefixtures("household_singleton")

HOUSEHOLD_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

UserFactory = Callable[..., Awaitable[User]]


async def _make_account(
    session: AsyncSession, owner_id: uuid.UUID, *, currency: str = "EUR"
) -> uuid.UUID:
    account = Account(
        name="Compte courant",
        type=AccountType.COURANT,
        currency=currency,
        owner_id=owner_id,
    )
    session.add(account)
    await session.flush()
    return account.id


async def _make_bare_tx(
    session: AsyncSession, *, account_id: uuid.UUID, created_by: uuid.UUID, state: str = "confirmed"
) -> Transaction:
    tx = Transaction(
        account_id=account_id,
        date=dt.date(2026, 6, 1),
        state=state,
        created_by=created_by,
    )
    session.add(tx)
    await session.flush()
    return tx


async def _add_split(  # noqa: PLR0913 — keyword-only seed helper
    session: AsyncSession,
    *,
    transaction_id: uuid.UUID,
    account_id: uuid.UUID,
    amount_cents: int,
    currency: str = "EUR",
    leg_role: str = "funding",
) -> None:
    session.add(
        Split(
            transaction_id=transaction_id,
            account_id=account_id,
            amount_cents=amount_cents,
            currency=currency,
            leg_role=leg_role,
        )
    )
    await session.flush()


async def _make_transfer_tx(  # noqa: PLR0913 — keyword-only seed helper
    session: AsyncSession,
    *,
    account_a: uuid.UUID,
    account_b: uuid.UUID,
    created_by: uuid.UUID,
    amount_cents: int,
    state: str = "confirmed",
    currency: str = "EUR",
) -> uuid.UUID:
    """A real internal transfer: 2 funding legs (−amount / +amount) on 2 accounts.

    `is_transfer` → True (2 distinct accounts), `derive_transfer_amount` → amount
    (Σ positive splits), zero-sum (loadable as a confirmed `domain.Transaction`).
    """
    tx = await _make_bare_tx(session, account_id=account_a, created_by=created_by, state=state)
    await _add_split(
        session,
        transaction_id=tx.id,
        account_id=account_a,
        amount_cents=-amount_cents,
        currency=currency,
    )
    await _add_split(
        session,
        transaction_id=tx.id,
        account_id=account_b,
        amount_cents=amount_cents,
        currency=currency,
    )
    return tx.id


async def _make_external_tx(  # noqa: PLR0913 — keyword-only seed helper
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    created_by: uuid.UUID,
    amount_cents: int,
    state: str = "confirmed",
    currency: str = "EUR",
) -> uuid.UUID:
    """An outgoing transfer on a SINGLE account: funding(−amount)+funding(+amount).

    `is_transfer` → False (1 account), `derive_transfer_amount` → amount. An
    `external_transfer` does NOT require `is_transfer` — only confirmed + accessible.
    """
    tx = await _make_bare_tx(session, account_id=account_id, created_by=created_by, state=state)
    await _add_split(
        session,
        transaction_id=tx.id,
        account_id=account_id,
        amount_cents=-amount_cents,
        currency=currency,
    )
    await _add_split(
        session,
        transaction_id=tx.id,
        account_id=account_id,
        amount_cents=amount_cents,
        currency=currency,
    )
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
) -> Debt:
    debt = Debt(
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        amount_cents=amount_cents,
        currency=currency,
        account_id=account_id,
        source_transaction_id=source_transaction_id,
        origin="personal_share_request",
    )
    session.add(debt)
    await session.flush()
    return debt


def _line(debt_id: uuid.UUID, amount_cents: int) -> SettlementLineInput:
    return SettlementLineInput(debt_id=debt_id, amount_cents=amount_cents)


async def _settlement_count(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(Settlement))).scalar_one())


async def _line_count(session: AsyncSession) -> int:
    return int(
        (await session.execute(select(func.count()).select_from(SettlementLine))).scalar_one()
    )


# ---------------------------------------------------------------------------
# Success paths (the 3 types) + derivation + multi-debts
# ---------------------------------------------------------------------------


async def test_internal_transfer_success(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (i) 2 foyer accounts owned by the creditor, a confirmed transfer tx, one
    # debt fully apaid → Settlement + 1 line; created_by == caller; remaining 0.
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc_a = await _make_account(household_singleton, creditor.id)
    acc_b = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_transfer_tx(
        household_singleton,
        account_a=acc_a,
        account_b=acc_b,
        created_by=creditor.id,
        amount_cents=5000,
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=acc_a,
        source_transaction_id=tx_id,
        amount_cents=5000,
    )

    s = await create_settlement(
        household_singleton,
        settlement_type="internal_transfer",
        linked_transaction_id=tx_id,
        settled_at=dt.date(2026, 6, 3),
        note=None,
        lines=[_line(debt.id, 5000)],
        by_user_id=creditor.id,
    )

    assert s.linked_transaction_id == tx_id
    assert s.created_by == creditor.id  # T-m3: invariant frozen at the service
    lines = (
        (
            await household_singleton.execute(
                select(SettlementLine).where(SettlementLine.settlement_id == s.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(lines) == 1
    assert await compute_remaining(household_singleton, debt_id=debt.id) == 0


async def test_external_transfer_success_and_derivation(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (ii) single-account funding/funding pair → derive == X, no NetTransferMismatch.
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_external_tx(
        household_singleton,
        account_id=acc,
        created_by=creditor.id,
        amount_cents=4200,
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=acc,
        source_transaction_id=tx_id,
        amount_cents=4200,
    )

    s = await create_settlement(
        household_singleton,
        settlement_type="external_transfer",
        linked_transaction_id=tx_id,
        settled_at=dt.date(2026, 6, 3),
        note=None,
        lines=[_line(debt.id, 4200)],
        by_user_id=creditor.id,
    )
    assert s.linked_transaction_id == tx_id
    assert await compute_remaining(household_singleton, debt_id=debt.id) == 0


async def test_virtual_success_cross_direction_nets_to_zero(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (iii) virtual: Bob→Alice + Alice→Bob, both fully apaid, net 0, no linked tx.
    alice, bob = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, alice.id)
    tx_id = await _make_external_tx(
        household_singleton,
        account_id=acc,
        created_by=alice.id,
        amount_cents=1,
    )
    b_to_a = await _make_debt(
        household_singleton,
        from_user_id=bob.id,
        to_user_id=alice.id,
        account_id=acc,
        source_transaction_id=tx_id,
        amount_cents=3000,
    )
    a_to_b = await _make_debt(
        household_singleton,
        from_user_id=alice.id,
        to_user_id=bob.id,
        account_id=acc,
        source_transaction_id=tx_id,
        amount_cents=3000,
    )

    s = await create_settlement(
        household_singleton,
        settlement_type="virtual",
        linked_transaction_id=None,
        settled_at=dt.date(2026, 6, 3),
        note=None,
        lines=[_line(b_to_a.id, 3000), _line(a_to_b.id, 3000)],
        by_user_id=alice.id,
    )
    assert s.linked_transaction_id is None
    assert await compute_remaining(household_singleton, debt_id=b_to_a.id) == 0
    assert await compute_remaining(household_singleton, debt_id=a_to_b.id) == 0


async def test_multi_debts_same_direction_two_lines(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (iv) one virtual settlement apaying 2 same-direction debts → 2 lines. Net is
    # non-zero, so we use a transfer matching the total to stay valid.
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc_a = await _make_account(household_singleton, creditor.id)
    acc_b = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_transfer_tx(
        household_singleton,
        account_a=acc_a,
        account_b=acc_b,
        created_by=creditor.id,
        amount_cents=5000,
    )
    d1 = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=acc_a,
        source_transaction_id=tx_id,
        amount_cents=2000,
    )
    d2 = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=acc_a,
        source_transaction_id=tx_id,
        amount_cents=3000,
    )

    s = await create_settlement(
        household_singleton,
        settlement_type="internal_transfer",
        linked_transaction_id=tx_id,
        settled_at=dt.date(2026, 6, 3),
        note=None,
        lines=[_line(d1.id, 2000), _line(d2.id, 3000)],
        by_user_id=creditor.id,
    )
    lines = (
        (
            await household_singleton.execute(
                select(SettlementLine).where(SettlementLine.settlement_id == s.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(lines) == 2


async def test_transfer_amount_derivation_must_match_net(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (v) transfer of 5000: a 5000 settlement is accepted; a 4000 one trips
    # NetTransferMismatch (net 4000 != derived 5000). Locks the derivation feeds
    # the validator the right scalar.
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc_a = await _make_account(household_singleton, creditor.id)
    acc_b = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_transfer_tx(
        household_singleton,
        account_a=acc_a,
        account_b=acc_b,
        created_by=creditor.id,
        amount_cents=5000,
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=acc_a,
        source_transaction_id=tx_id,
        amount_cents=5000,
    )

    with pytest.raises(NetTransferMismatchError):
        await create_settlement(
            household_singleton,
            settlement_type="internal_transfer",
            linked_transaction_id=tx_id,
            settled_at=dt.date(2026, 6, 3),
            note=None,
            lines=[_line(debt.id, 4000)],  # net 4000 != transfer 5000
            by_user_id=creditor.id,
        )


# ---------------------------------------------------------------------------
# Negative paths — verification order (404 first, anti-oracle)
# ---------------------------------------------------------------------------


async def test_unknown_debt_id_rejected(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (vi) a line targeting a non-existent debt → 404 uniform.
    alice = await bound_user_factory()
    with pytest.raises(SettlementDebtNotAccessibleError):
        await create_settlement(
            household_singleton,
            settlement_type="virtual",
            linked_transaction_id=None,
            settled_at=dt.date(2026, 6, 3),
            note=None,
            lines=[_line(uuid.uuid4(), 1000)],
            by_user_id=alice.id,
        )


async def test_caller_not_party_rejected_indistinctly(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (vii) caller is party to NONE of the targeted debts → 404, indistinct from
    # "unknown debt" (anti-oracle: same exception type).
    debtor, creditor, stranger = (
        await bound_user_factory(),
        await bound_user_factory(),
        await bound_user_factory(),
    )
    acc = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_external_tx(
        household_singleton,
        account_id=acc,
        created_by=creditor.id,
        amount_cents=1,
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=acc,
        source_transaction_id=tx_id,
    )
    with pytest.raises(SettlementDebtNotAccessibleError):
        await create_settlement(
            household_singleton,
            settlement_type="virtual",
            linked_transaction_id=None,
            settled_at=dt.date(2026, 6, 3),
            note=None,
            lines=[_line(debt.id, 1000)],
            by_user_id=stranger.id,  # not from/to of the debt
        )


async def test_non_virtual_without_or_unknown_linked_tx_rejected(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (viii) non-virtual with a missing / unknown linked tx → 404.
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_external_tx(
        household_singleton,
        account_id=acc,
        created_by=creditor.id,
        amount_cents=1,
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=acc,
        source_transaction_id=tx_id,
    )
    # No linked_transaction_id at all.
    with pytest.raises(LinkedTransactionNotAccessibleError):
        await create_settlement(
            household_singleton,
            settlement_type="external_transfer",
            linked_transaction_id=None,
            settled_at=dt.date(2026, 6, 3),
            note=None,
            lines=[_line(debt.id, 1000)],
            by_user_id=creditor.id,
        )
    # A linked id that does not resolve to any tx.
    with pytest.raises(LinkedTransactionNotAccessibleError):
        await create_settlement(
            household_singleton,
            settlement_type="external_transfer",
            linked_transaction_id=uuid.uuid4(),
            settled_at=dt.date(2026, 6, 3),
            note=None,
            lines=[_line(debt.id, 1000)],
            by_user_id=creditor.id,
        )


async def test_inaccessible_tx_account_rejected(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (viii-bis) tx exists but ONE of its accounts is owned by a third party
    # (inaccessible to the caller) → 404 (A-m1: accessibility on ALL tx accounts).
    debtor, creditor, stranger = (
        await bound_user_factory(),
        await bound_user_factory(),
        await bound_user_factory(),
    )
    acc_own = await _make_account(household_singleton, creditor.id)
    acc_foreign = await _make_account(household_singleton, stranger.id)  # same foyer, not caller's
    tx_id = await _make_transfer_tx(
        household_singleton,
        account_a=acc_own,
        account_b=acc_foreign,
        created_by=creditor.id,
        amount_cents=5000,
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=acc_own,
        source_transaction_id=tx_id,
        amount_cents=5000,
    )
    with pytest.raises(LinkedTransactionNotAccessibleError):
        await create_settlement(
            household_singleton,
            settlement_type="internal_transfer",
            linked_transaction_id=tx_id,
            settled_at=dt.date(2026, 6, 3),
            note=None,
            lines=[_line(debt.id, 5000)],
            by_user_id=creditor.id,  # accessible to acc_own, NOT acc_foreign
        )


async def test_non_confirmed_tx_rejected(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (ix) a draft/planned linked tx → 422 (ADR 0001: amount only frozen at confirmed).
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc_a = await _make_account(household_singleton, creditor.id)
    acc_b = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_transfer_tx(
        household_singleton,
        account_a=acc_a,
        account_b=acc_b,
        created_by=creditor.id,
        amount_cents=5000,
        state="draft",
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=acc_a,
        source_transaction_id=tx_id,
        amount_cents=5000,
    )
    with pytest.raises(LinkedTransactionNotConfirmedError):
        await create_settlement(
            household_singleton,
            settlement_type="internal_transfer",
            linked_transaction_id=tx_id,
            settled_at=dt.date(2026, 6, 3),
            note=None,
            lines=[_line(debt.id, 5000)],
            by_user_id=creditor.id,
        )


async def test_internal_transfer_on_non_transfer_tx_rejected(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (x) internal_transfer pointing at a single-account tx (not a transfer) → 422.
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_external_tx(
        household_singleton,
        account_id=acc,
        created_by=creditor.id,
        amount_cents=5000,
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=acc,
        source_transaction_id=tx_id,
        amount_cents=5000,
    )
    with pytest.raises(LinkedTransactionNotTransferError):
        await create_settlement(
            household_singleton,
            settlement_type="internal_transfer",
            linked_transaction_id=tx_id,
            settled_at=dt.date(2026, 6, 3),
            note=None,
            lines=[_line(debt.id, 5000)],
            by_user_id=creditor.id,
        )


# ---------------------------------------------------------------------------
# Validator propagation (one case per representative rule → 422 at the boundary)
# ---------------------------------------------------------------------------


async def test_over_settlement_propagates(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_external_tx(
        household_singleton,
        account_id=acc,
        created_by=creditor.id,
        amount_cents=1,
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=acc,
        source_transaction_id=tx_id,
        amount_cents=5000,
    )
    with pytest.raises(OverSettlementError):
        await create_settlement(
            household_singleton,
            settlement_type="virtual",
            linked_transaction_id=None,
            settled_at=dt.date(2026, 6, 3),
            note=None,
            lines=[_line(debt.id, 8000)],  # > remaining 5000
            by_user_id=creditor.id,
        )


async def test_closed_debt_propagates(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # A debt fully settled (remaining 0) cannot be apaid again → ClosedDebtError.
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_external_tx(
        household_singleton,
        account_id=acc,
        created_by=creditor.id,
        amount_cents=1,
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=acc,
        source_transaction_id=tx_id,
        amount_cents=5000,
    )
    # Pre-settle it fully via a first virtual settlement.
    pre = Settlement(
        household_id=HOUSEHOLD_ID,
        created_by=creditor.id,
        type="virtual",
        linked_transaction_id=None,
        settled_at=dt.date(2026, 6, 2),
    )
    household_singleton.add(pre)
    await household_singleton.flush()
    household_singleton.add(
        SettlementLine(settlement_id=pre.id, debt_id=debt.id, amount_cents=5000, currency="EUR")
    )
    await household_singleton.flush()
    assert await compute_remaining(household_singleton, debt_id=debt.id) == 0

    with pytest.raises(ClosedDebtError):
        await create_settlement(
            household_singleton,
            settlement_type="virtual",
            linked_transaction_id=None,
            settled_at=dt.date(2026, 6, 3),
            note=None,
            lines=[_line(debt.id, 1000)],
            by_user_id=creditor.id,
        )


async def test_mixed_currency_propagates(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc_eur = await _make_account(household_singleton, creditor.id)
    acc_usd = await _make_account(household_singleton, creditor.id, currency="USD")
    tx_eur = await _make_external_tx(
        household_singleton,
        account_id=acc_eur,
        created_by=creditor.id,
        amount_cents=1,
    )
    tx_usd = await _make_external_tx(
        household_singleton,
        account_id=acc_usd,
        created_by=creditor.id,
        amount_cents=1,
        currency="USD",
    )
    d_eur = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=acc_eur,
        source_transaction_id=tx_eur,
        amount_cents=5000,
        currency="EUR",
    )
    d_usd = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=acc_usd,
        source_transaction_id=tx_usd,
        amount_cents=5000,
        currency="USD",
    )
    with pytest.raises(MixedCurrencyError):
        await create_settlement(
            household_singleton,
            settlement_type="virtual",
            linked_transaction_id=None,
            settled_at=dt.date(2026, 6, 3),
            note=None,
            lines=[_line(d_eur.id, 1000), _line(d_usd.id, 1000)],
            by_user_id=creditor.id,
        )


async def test_more_than_two_counterparties_propagates(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    a, b, c = (
        await bound_user_factory(),
        await bound_user_factory(),
        await bound_user_factory(),
    )
    acc = await _make_account(household_singleton, a.id)
    tx_id = await _make_external_tx(
        household_singleton,
        account_id=acc,
        created_by=a.id,
        amount_cents=1,
    )
    a_to_b = await _make_debt(
        household_singleton,
        from_user_id=a.id,
        to_user_id=b.id,
        account_id=acc,
        source_transaction_id=tx_id,
        amount_cents=5000,
    )
    a_to_c = await _make_debt(
        household_singleton,
        from_user_id=a.id,
        to_user_id=c.id,
        account_id=acc,
        source_transaction_id=tx_id,
        amount_cents=5000,
    )
    with pytest.raises(MultipleCounterpartiesError):
        await create_settlement(
            household_singleton,
            settlement_type="virtual",
            linked_transaction_id=None,
            settled_at=dt.date(2026, 6, 3),
            note=None,
            lines=[_line(a_to_b.id, 1000), _line(a_to_c.id, 1000)],
            by_user_id=a.id,  # party to both, but {a,b,c} = 3 parties
        )


# ---------------------------------------------------------------------------
# Atomicity (T-M1) + foyer guard wiring on the real path (xiii-bis)
# ---------------------------------------------------------------------------


async def test_insert_is_atomic_across_two_flushes(
    household_singleton: AsyncSession,
    bound_user_factory: UserFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # (xii) REAL atomicity: with the validator stubbed to a no-op, a multi-line
    # settlement whose 2nd line carries a non-positive amount makes the SECOND
    # flush (lines) raise — AFTER the Settlement's own flush. The whole insert
    # must roll back: zero Settlement, zero line. Run under a savepoint so the
    # IntegrityError reverts only this attempt, leaving the outer tx queryable.
    def _noop_validate(**_kwargs: object) -> None:
        return None

    monkeypatch.setattr(SettlementValidator, "validate", staticmethod(_noop_validate))
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_external_tx(
        household_singleton,
        account_id=acc,
        created_by=creditor.id,
        amount_cents=1,
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=acc,
        source_transaction_id=tx_id,
        amount_cents=5000,
    )
    before = await _settlement_count(household_singleton)

    with pytest.raises(IntegrityError):  # noqa: PT012 — savepoint scope is intentional
        async with household_singleton.begin_nested():
            await create_settlement(
                household_singleton,
                settlement_type="virtual",
                linked_transaction_id=None,
                settled_at=dt.date(2026, 6, 3),
                note=None,
                lines=[_line(debt.id, 1000), _line(debt.id, -1)],  # 2nd line violates the CHECK
                by_user_id=creditor.id,
            )

    assert await _settlement_count(household_singleton) == before  # nothing persisted
    assert await _line_count(household_singleton) == 0


async def test_cross_household_guard_bites_on_real_path(
    household_singleton: AsyncSession,
    bound_user_factory: UserFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # (xiii-bis) The reject branch is un-seedable under the singleton (plan §6):
    # monkeypatch `_resolve_households` to inject a divergent foyer id, then call
    # the REAL create_settlement → CrossHouseholdError + nothing inserted. Proves
    # the guard is WIRED (a happy-path passes whether the guard runs or not).
    async def _fake_resolve(_session: AsyncSession, _account_ids: set[uuid.UUID]) -> set[uuid.UUID]:
        return {HOUSEHOLD_ID, uuid.uuid4()}

    monkeypatch.setattr(settlement_svc, "_resolve_households", _fake_resolve)
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_external_tx(
        household_singleton,
        account_id=acc,
        created_by=creditor.id,
        amount_cents=5000,
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=acc,
        source_transaction_id=tx_id,
        amount_cents=5000,
    )
    before = await _settlement_count(household_singleton)

    with pytest.raises(CrossHouseholdError):
        await create_settlement(
            household_singleton,
            settlement_type="external_transfer",
            linked_transaction_id=tx_id,
            settled_at=dt.date(2026, 6, 3),
            note=None,
            lines=[_line(debt.id, 5000)],
            by_user_id=creditor.id,
        )
    assert await _settlement_count(household_singleton) == before  # no insert


async def test_happy_path_household_resolution_passes(
    household_singleton: AsyncSession, bound_user_factory: UserFactory
) -> None:
    # (xiv) the REAL effectful resolution (all accounts → HOUSEHOLD_ID) does not
    # raise — locks the nominal foyer resolution (complements the monkeypatch).
    debtor, creditor = await bound_user_factory(), await bound_user_factory()
    acc = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_external_tx(
        household_singleton,
        account_id=acc,
        created_by=creditor.id,
        amount_cents=5000,
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=acc,
        source_transaction_id=tx_id,
        amount_cents=5000,
    )
    s = await create_settlement(
        household_singleton,
        settlement_type="external_transfer",
        linked_transaction_id=tx_id,
        settled_at=dt.date(2026, 6, 3),
        note="règlement OK",
        lines=[_line(debt.id, 5000)],
        by_user_id=creditor.id,
    )
    assert s.id is not None
    assert s.note == "règlement OK"
