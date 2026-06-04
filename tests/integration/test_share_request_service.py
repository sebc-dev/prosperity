"""Integration tests for `debts.service.share_request` (S09.3, P09.3.1/2).

Drives `create_share_request` / `revoke_share_request` against a real Postgres
schema (testcontainers). The service is transaction-agnostic (commit by
`get_db`, ADR 0015 — D1): these tests call it with the test session directly and
read back the flushed rows from that same session.

Covers the full verification order (i)…(ix) with one negative per check, the
`expense_total` derivation from classification legs (funding excluded, ADR 0017),
the degenerate-rounding guard (review #144 F1), and the revoke flow including the
"no orphan Debt" invariant (review #144 D12).

Factories are bound to the test session via `bound_transaction_factories` (and
`CategoryFactory`, bound on the same session, is used directly for the
classification legs). Each test runs in its own rolled-back transaction, so
fixed emails never collide across tests.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.debts.domain import (
    NonPositiveDebtAmountError,
    NonPositiveExpenseError,
    RatioOutOfBoundsError,
)
from backend.modules.debts.models import Debt, ShareRequest
from backend.modules.debts.service.share_request import (
    DuplicateActiveShareRequestError,
    RequestedFromNotMemberError,
    SelfShareError,
    ShareRequestNotFoundError,
    SourceAccountNotShareableError,
    SourceTransactionNotConfirmedError,
    SourceTransactionNotFoundError,
    create_share_request,
    revoke_share_request,
)
from tests.integration._debts_helpers import (
    Scenario,
    TxFactoryBundle,
    debt_count,
    seed,
)

# ---------------------------------------------------------------------------
# Happy path + amount derivation
# ---------------------------------------------------------------------------


async def test_create_materialises_share_request_and_debt(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await seed(
        household_singleton, bound_transaction_factories, legs=[(-300, False), (300, True)]
    )

    sr = await create_share_request(
        household_singleton,
        transaction_id=s.tx_id,
        requested_from=s.bob_id,
        ratio=Decimal("1.0"),
        short_label="Courses",
        by_user_id=s.alice_id,
    )

    assert sr.requested_by == s.alice_id
    assert sr.requested_from == s.bob_id
    assert sr.revoked_at is None

    debt = (
        await household_singleton.execute(select(Debt).where(Debt.source_transaction_id == s.tx_id))
    ).scalar_one()
    assert debt.from_user_id == s.bob_id
    assert debt.to_user_id == s.alice_id
    assert debt.amount_cents == 300
    assert debt.currency == "EUR"
    assert debt.account_id == s.account_id
    assert debt.source_transaction_id == s.tx_id
    assert debt.origin == "personal_share_request"
    assert float(debt.share_ratio) == 1.0
    assert debt.materialization_trace is not None  # server-only marker posted


async def test_create_non_trivial_ratio_rounds_half_up(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await seed(
        household_singleton, bound_transaction_factories, legs=[(-333, False), (333, True)]
    )

    await create_share_request(
        household_singleton,
        transaction_id=s.tx_id,
        requested_from=s.bob_id,
        ratio=Decimal("0.5"),
        short_label="Moitie",
        by_user_id=s.alice_id,
    )

    debt = (
        await household_singleton.execute(select(Debt).where(Debt.source_transaction_id == s.tx_id))
    ).scalar_one()
    assert debt.amount_cents == 167  # 333 * 0.5 = 166.5 → ROUND_HALF_UP → 167


async def test_create_degenerate_rounding_raises(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # review #144 F1: 1¢ × 0.4 = 0.4 → ROUND_HALF_UP → 0 → NonPositiveDebtAmountError.
    s = await seed(household_singleton, bound_transaction_factories, legs=[(-1, False), (1, True)])

    with pytest.raises(NonPositiveDebtAmountError):
        await create_share_request(
            household_singleton,
            transaction_id=s.tx_id,
            requested_from=s.bob_id,
            ratio=Decimal("0.4"),
            short_label="Centime",
            by_user_id=s.alice_id,
        )
    assert await debt_count(household_singleton, tx_id=s.tx_id) == 0


async def test_expense_total_derives_from_classification_legs_only(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # funding(-300) + classification(+100) + classification(+200): expense_total
    # = 300 (funding EXCLUDED). If the funding leg were summed in, the total
    # would be 0. Exactly ONE Debt (the classification legs aggregate into a
    # single expense_total — F9).
    s = await seed(
        household_singleton,
        bound_transaction_factories,
        legs=[(-300, False), (100, True), (200, True)],
    )

    await create_share_request(
        household_singleton,
        transaction_id=s.tx_id,
        requested_from=s.bob_id,
        ratio=Decimal("1.0"),
        short_label="Multi",
        by_user_id=s.alice_id,
    )

    debts = (
        (
            await household_singleton.execute(
                select(Debt).where(Debt.source_transaction_id == s.tx_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(debts) == 1
    assert debts[0].amount_cents == 300  # NOT 0 (funding excluded), NOT per-leg


# ---------------------------------------------------------------------------
# Negative cases — one per verification (i)…(ix)
# ---------------------------------------------------------------------------


async def test_i_unknown_transaction_raises_not_found(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await seed(
        household_singleton, bound_transaction_factories, legs=[(-300, False), (300, True)]
    )
    with pytest.raises(SourceTransactionNotFoundError):
        await create_share_request(
            household_singleton,
            transaction_id=uuid.uuid4(),  # unknown id
            requested_from=s.bob_id,
            ratio=Decimal("1.0"),
            short_label="X",
            by_user_id=s.alice_id,
        )


async def test_i_inaccessible_transaction_raises_not_found(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # tx on Carol's personal account → not accessible to Alice → uniform 404.
    s = await seed(
        household_singleton,
        bound_transaction_factories,
        legs=[(-300, False), (300, True)],
        tx_owner_is_alice=False,
    )
    with pytest.raises(SourceTransactionNotFoundError):
        await create_share_request(
            household_singleton,
            transaction_id=s.tx_id,
            requested_from=s.bob_id,
            ratio=Decimal("1.0"),
            short_label="X",
            by_user_id=s.alice_id,
        )


async def test_ii_shared_account_not_shareable(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # Accessible (Alice is a member) but NOT an owned personal account → 422.
    s = await seed(
        household_singleton,
        bound_transaction_factories,
        legs=[(-300, False), (300, True)],
        personal=False,
    )
    with pytest.raises(SourceAccountNotShareableError):
        await create_share_request(
            household_singleton,
            transaction_id=s.tx_id,
            requested_from=s.bob_id,
            ratio=Decimal("1.0"),
            short_label="X",
            by_user_id=s.alice_id,
        )


async def test_iii_non_confirmed_transaction(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await seed(
        household_singleton,
        bound_transaction_factories,
        legs=[(-300, False), (300, True)],
        state="draft",
    )
    with pytest.raises(SourceTransactionNotConfirmedError):
        await create_share_request(
            household_singleton,
            transaction_id=s.tx_id,
            requested_from=s.bob_id,
            ratio=Decimal("1.0"),
            short_label="X",
            by_user_id=s.alice_id,
        )


async def test_iv_requested_from_unknown(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await seed(
        household_singleton, bound_transaction_factories, legs=[(-300, False), (300, True)]
    )
    with pytest.raises(RequestedFromNotMemberError):
        await create_share_request(
            household_singleton,
            transaction_id=s.tx_id,
            requested_from=uuid.uuid4(),  # not a member
            ratio=Decimal("1.0"),
            short_label="X",
            by_user_id=s.alice_id,
        )


async def test_iv_requested_from_disabled(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # F02: a disabled user is not a valid counterparty → 422 (no phantom debt).
    s = await seed(
        household_singleton,
        bound_transaction_factories,
        legs=[(-300, False), (300, True)],
        bob_disabled=True,
    )
    with pytest.raises(RequestedFromNotMemberError):
        await create_share_request(
            household_singleton,
            transaction_id=s.tx_id,
            requested_from=s.bob_id,
            ratio=Decimal("1.0"),
            short_label="X",
            by_user_id=s.alice_id,
        )


async def test_v_self_share(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await seed(
        household_singleton, bound_transaction_factories, legs=[(-300, False), (300, True)]
    )
    with pytest.raises(SelfShareError):
        await create_share_request(
            household_singleton,
            transaction_id=s.tx_id,
            requested_from=s.alice_id,  # == by_user_id
            ratio=Decimal("1.0"),
            short_label="X",
            by_user_id=s.alice_id,
        )


async def test_vi_ratio_out_of_bounds_failsafe(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # Direct service call with an out-of-bounds ratio (the 422 boundary is the
    # schema, tested in the route suite): the DebtCalculator is the fail-safe.
    s = await seed(
        household_singleton, bound_transaction_factories, legs=[(-300, False), (300, True)]
    )
    with pytest.raises(RatioOutOfBoundsError):
        await create_share_request(
            household_singleton,
            transaction_id=s.tx_id,
            requested_from=s.bob_id,
            ratio=Decimal("1.5"),
            short_label="X",
            by_user_id=s.alice_id,
        )


async def test_viii_transfer_has_no_shareable_expense(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # A transfer = two funding legs, zero classification → expense_total = 0.
    s = await seed(
        household_singleton,
        bound_transaction_factories,
        legs=[(-300, False), (300, False)],
    )
    with pytest.raises(NonPositiveExpenseError):
        await create_share_request(
            household_singleton,
            transaction_id=s.tx_id,
            requested_from=s.bob_id,
            ratio=Decimal("1.0"),
            short_label="X",
            by_user_id=s.alice_id,
        )


async def test_viii_income_has_no_shareable_expense(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # An income/refund: classification legs sum ≤ 0 → expense_total ≤ 0. One does
    # not "share" a money inflow (review #144 #2, D3).
    s = await seed(
        household_singleton,
        bound_transaction_factories,
        legs=[(300, False), (-300, True)],
    )
    with pytest.raises(NonPositiveExpenseError):
        await create_share_request(
            household_singleton,
            transaction_id=s.tx_id,
            requested_from=s.bob_id,
            ratio=Decimal("1.0"),
            short_label="X",
            by_user_id=s.alice_id,
        )


async def test_ix_duplicate_active_share_request(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await seed(
        household_singleton, bound_transaction_factories, legs=[(-300, False), (300, True)]
    )
    await create_share_request(
        household_singleton,
        transaction_id=s.tx_id,
        requested_from=s.bob_id,
        ratio=Decimal("1.0"),
        short_label="First",
        by_user_id=s.alice_id,
    )
    with pytest.raises(DuplicateActiveShareRequestError):
        await create_share_request(
            household_singleton,
            transaction_id=s.tx_id,
            requested_from=s.bob_id,
            ratio=Decimal("1.0"),
            short_label="Second",
            by_user_id=s.alice_id,
        )
    # Exactly one Debt — the duplicate attempt materialised nothing.
    assert await debt_count(household_singleton, tx_id=s.tx_id) == 1


# ---------------------------------------------------------------------------
# revoke_share_request (P09.3.2)
# ---------------------------------------------------------------------------


async def _create_ok(session: AsyncSession, s: Scenario, *, label: str = "L") -> ShareRequest:
    return await create_share_request(
        session,
        transaction_id=s.tx_id,
        requested_from=s.bob_id,
        ratio=Decimal("1.0"),
        short_label=label,
        by_user_id=s.alice_id,
    )


async def test_revoke_by_creditor_deletes_debt_keeps_share_request(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await seed(
        household_singleton, bound_transaction_factories, legs=[(-300, False), (300, True)]
    )
    sr = await _create_ok(household_singleton, s)
    sr_id = sr.id  # capture before expire (an expired attr would reload sync)

    await revoke_share_request(household_singleton, share_request_id=sr_id, by_user_id=s.alice_id)

    household_singleton.expire_all()
    reloaded = (
        await household_singleton.execute(select(ShareRequest).where(ShareRequest.id == sr_id))
    ).scalar_one()
    assert reloaded.revoked_at is not None  # SR kept, marked revoked
    assert await debt_count(household_singleton, tx_id=s.tx_id) == 0  # Debt hard-deleted


async def test_revoke_by_non_creditor_raises_not_found(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await seed(
        household_singleton, bound_transaction_factories, legs=[(-300, False), (300, True)]
    )
    sr = await _create_ok(household_singleton, s)
    sr_id = sr.id  # capture before expire

    with pytest.raises(ShareRequestNotFoundError):
        # Bob (the debtor) cannot revoke → uniform 404 (anti-oracle).
        await revoke_share_request(household_singleton, share_request_id=sr_id, by_user_id=s.bob_id)

    household_singleton.expire_all()
    reloaded = (
        await household_singleton.execute(select(ShareRequest).where(ShareRequest.id == sr_id))
    ).scalar_one()
    assert reloaded.revoked_at is None  # untouched
    assert await debt_count(household_singleton, tx_id=s.tx_id) == 1  # Debt intact


async def test_revoke_unknown_id_raises_not_found(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await seed(
        household_singleton, bound_transaction_factories, legs=[(-300, False), (300, True)]
    )
    with pytest.raises(ShareRequestNotFoundError):
        await revoke_share_request(
            household_singleton, share_request_id=uuid.uuid4(), by_user_id=s.alice_id
        )


async def test_double_revoke_is_noop(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await seed(
        household_singleton, bound_transaction_factories, legs=[(-300, False), (300, True)]
    )
    sr = await _create_ok(household_singleton, s)
    sr_id = sr.id  # capture before expire
    await revoke_share_request(household_singleton, share_request_id=sr_id, by_user_id=s.alice_id)

    household_singleton.expire_all()
    first_revoked_at = (
        await household_singleton.execute(
            select(ShareRequest.revoked_at).where(ShareRequest.id == sr_id)
        )
    ).scalar_one()

    # Second revoke → no-op (no crash, no Debt recreated, revoked_at unchanged).
    await revoke_share_request(household_singleton, share_request_id=sr_id, by_user_id=s.alice_id)

    household_singleton.expire_all()
    second_revoked_at = (
        await household_singleton.execute(
            select(ShareRequest.revoked_at).where(ShareRequest.id == sr_id)
        )
    ).scalar_one()
    assert second_revoked_at == first_revoked_at
    assert await debt_count(household_singleton, tx_id=s.tx_id) == 0


async def test_recreate_after_revoke_succeeds(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    s = await seed(
        household_singleton, bound_transaction_factories, legs=[(-300, False), (300, True)]
    )
    sr = await _create_ok(household_singleton, s, label="First")
    await revoke_share_request(household_singleton, share_request_id=sr.id, by_user_id=s.alice_id)

    # The partial-unique slot is freed → a new SR on the same pair succeeds.
    sr2 = await _create_ok(household_singleton, s, label="Second")
    assert sr2.id != sr.id
    assert await debt_count(household_singleton, tx_id=s.tx_id) == 1


async def test_no_orphan_debt_across_create_revoke_cycles(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # review #144 D12: repeated create→revoke leaves no residual / over-deleted
    # Debt. After each revoke, exactly 0 live Debt on the triplet.
    s = await seed(
        household_singleton, bound_transaction_factories, legs=[(-300, False), (300, True)]
    )
    for _ in range(3):
        sr = await _create_ok(household_singleton, s)
        assert await debt_count(household_singleton, tx_id=s.tx_id) == 1
        await revoke_share_request(
            household_singleton, share_request_id=sr.id, by_user_id=s.alice_id
        )
        assert await debt_count(household_singleton, tx_id=s.tx_id) == 0
    assert await debt_count(household_singleton, tx_id=s.tx_id) == 0
