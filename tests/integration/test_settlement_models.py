"""Integration tests for `debts.models` (S10.1 `Settlement` / `SettlementLine`).

Exercise the persisted behaviour the unit tier and the level-1 snapshot cannot
reach: the `ON DELETE CASCADE`/`RESTRICT` FK matrix, the strictly-positive line
CHECK (`amount_cents > 0`, D-SIGN), the relational virtual/link biconditional
CHECK (both directions), and the assumed "non-virtual settlement orphaned of its
lines after a debt CASCADE" behaviour (ADR 0011, encart Refined-by E10). Pure
`flush` + rollback isolation (`household_singleton`) — FK/CHECK violations
surface at `flush` because they are DB-level.

The `_make_account`/`_make_transaction`/`_make_debt` helpers are copied inline
from `test_debts_models.py` (they live there under a `test_` module and are not
importable cleanly — `_debts_helpers.py` only exposes the `seed`/`Scenario`
surface).
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.domain import AccountType
from backend.modules.accounts.models import Account
from backend.modules.auth.models import User
from backend.modules.debts.models import Debt, Settlement, SettlementLine
from backend.modules.transactions.models import Transaction

# Every test inserts an `Account`, whose `household_id` FK requires the
# singleton `household` row to exist (ADR 0010); seed it for the whole module.
pytestmark = pytest.mark.usefixtures("household_singleton")

# Singleton household id (ADR 0010) — `Settlement.household_id` scopes the foyer.
HOUSEHOLD_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


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
    origin: str = "personal_share_request",
) -> Debt:
    debt = Debt(
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        amount_cents=amount_cents,
        currency="EUR",
        account_id=account_id,
        source_transaction_id=source_transaction_id,
        origin=origin,
    )
    session.add(debt)
    await session.flush()
    return debt


async def _make_settlement(  # noqa: PLR0913 — keyword-only seed helper
    session: AsyncSession,
    *,
    created_by: uuid.UUID,
    type: str = "internal_transfer",
    linked_transaction_id: uuid.UUID | None,
    settled_at: dt.date = dt.date(2026, 6, 3),
    note: str | None = None,
) -> Settlement:
    settlement = Settlement(
        household_id=HOUSEHOLD_ID,
        created_by=created_by,
        type=type,
        linked_transaction_id=linked_transaction_id,
        settled_at=settled_at,
        note=note,
    )
    session.add(settlement)
    await session.flush()
    return settlement


async def _make_line(
    session: AsyncSession,
    *,
    settlement_id: uuid.UUID,
    debt_id: uuid.UUID,
    amount_cents: int = 5000,
) -> SettlementLine:
    line = SettlementLine(
        settlement_id=settlement_id,
        debt_id=debt_id,
        amount_cents=amount_cents,
        currency="EUR",
    )
    session.add(line)
    await session.flush()
    return line


# ---------------------------------------------------------------------------
# Settlement (P10.1.2)
# ---------------------------------------------------------------------------


async def test_settlement_persists_with_defaults(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # Livrable observable: a non-virtual settlement (tx link) + a line persist;
    # `created_at` rounds the server_default, `note` NULL is fine, `settled_at`
    # round-trips as the inserted `date`.
    debtor = await bound_user_factory()
    creditor = await bound_user_factory()
    account_id = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_transaction(
        household_singleton, account_id=account_id, created_by=creditor.id
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=account_id,
        source_transaction_id=tx_id,
    )
    settlement = await _make_settlement(
        household_singleton,
        created_by=creditor.id,
        linked_transaction_id=tx_id,
        settled_at=dt.date(2026, 6, 3),
    )
    await _make_line(
        household_singleton, settlement_id=settlement.id, debt_id=debt.id
    )
    settlement_id = settlement.id

    household_singleton.expire_all()
    reloaded = (
        await household_singleton.execute(
            select(Settlement).where(Settlement.id == settlement_id)
        )
    ).scalar_one()
    assert reloaded.created_at is not None
    assert reloaded.note is None
    assert reloaded.settled_at == dt.date(2026, 6, 3)
    assert reloaded.type == "internal_transfer"


async def test_virtual_settlement_persists_with_null_link(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # `ck_settlements_virtual_no_link`, direction « virtual ⇒ lien NULL » :
    # `type='virtual'` + `linked_transaction_id=None` flushes clean.
    creator = await bound_user_factory()
    settlement = await _make_settlement(
        household_singleton,
        created_by=creator.id,
        type="virtual",
        linked_transaction_id=None,
    )
    assert settlement.id is not None  # no IntegrityError


async def test_type_accepts_arbitrary_string(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # No DB CHECK enumerates the `type` set (it lives at the Pydantic boundary,
    # S10.2/S10.4). A future non-virtual type with a link persists — behavioural
    # twin of `test_origin_accepts_arbitrary_string`.
    creator = await bound_user_factory()
    account_id = await _make_account(household_singleton, creator.id)
    tx_id = await _make_transaction(
        household_singleton, account_id=account_id, created_by=creator.id
    )
    settlement = await _make_settlement(
        household_singleton,
        created_by=creator.id,
        type="some_future_type",
        linked_transaction_id=tx_id,
    )
    assert settlement.type == "some_future_type"  # no IntegrityError


async def test_virtual_with_link_violates_check(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # `ck_settlements_virtual_no_link`, sens 1 : `virtual` + lien NOT NULL rejeté.
    creator = await bound_user_factory()
    account_id = await _make_account(household_singleton, creator.id)
    tx_id = await _make_transaction(
        household_singleton, account_id=account_id, created_by=creator.id
    )
    with pytest.raises(IntegrityError):
        await _make_settlement(
            household_singleton,
            created_by=creator.id,
            type="virtual",
            linked_transaction_id=tx_id,
        )


async def test_non_virtual_with_null_link_violates_check(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # `ck_settlements_virtual_no_link`, sens 2 du biconditionnel : un type
    # non-virtuel SANS lien est rejeté.
    creator = await bound_user_factory()
    with pytest.raises(IntegrityError):
        await _make_settlement(
            household_singleton,
            created_by=creator.id,
            type="internal_transfer",
            linked_transaction_id=None,
        )


async def test_delete_settlement_cascades_lines(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # `settlement_id` ON DELETE CASCADE: deleting a settlement removes its lines.
    debtor = await bound_user_factory()
    creditor = await bound_user_factory()
    account_id = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_transaction(
        household_singleton, account_id=account_id, created_by=creditor.id
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=account_id,
        source_transaction_id=tx_id,
    )
    settlement = await _make_settlement(
        household_singleton, created_by=creditor.id, linked_transaction_id=tx_id
    )
    await _make_line(
        household_singleton, settlement_id=settlement.id, debt_id=debt.id
    )
    settlement_id = settlement.id

    await household_singleton.delete(settlement)
    await household_singleton.flush()

    count = (
        await household_singleton.execute(
            text("SELECT count(*) FROM settlement_lines WHERE settlement_id = :id"),
            {"id": settlement_id},
        )
    ).scalar_one()
    assert count == 0


async def test_delete_debt_cascades_lines(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # `debt_id` ON DELETE CASCADE: deleting the source debt removes its
    # settlement lines (regenerable projection).
    debtor = await bound_user_factory()
    creditor = await bound_user_factory()
    account_id = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_transaction(
        household_singleton, account_id=account_id, created_by=creditor.id
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=account_id,
        source_transaction_id=tx_id,
    )
    settlement = await _make_settlement(
        household_singleton, created_by=creditor.id, linked_transaction_id=tx_id
    )
    await _make_line(
        household_singleton, settlement_id=settlement.id, debt_id=debt.id
    )
    debt_id = debt.id

    await household_singleton.delete(debt)
    await household_singleton.flush()

    count = (
        await household_singleton.execute(
            text("SELECT count(*) FROM settlement_lines WHERE debt_id = :id"),
            {"id": debt_id},
        )
    ).scalar_one()
    assert count == 0


@pytest.mark.parametrize("amount", [0, -1])
async def test_non_positive_line_amount_violates_check(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
    amount: int,
) -> None:
    # `ck_settlement_lines_amount_positive` (D-SIGN): a line always carries a
    # strictly positive amount; the netting direction is carried by the Debt's
    # orientation, not a sign on the line.
    debtor = await bound_user_factory()
    creditor = await bound_user_factory()
    account_id = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_transaction(
        household_singleton, account_id=account_id, created_by=creditor.id
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=account_id,
        source_transaction_id=tx_id,
    )
    settlement = await _make_settlement(
        household_singleton, created_by=creditor.id, linked_transaction_id=tx_id
    )
    with pytest.raises(IntegrityError):
        await _make_line(
            household_singleton,
            settlement_id=settlement.id,
            debt_id=debt.id,
            amount_cents=amount,
        )


async def test_delete_linked_transaction_is_restricted(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # `linked_transaction_id` ON DELETE RESTRICT: the wire transfer tx cannot be
    # hard-deleted while a non-virtual settlement still references it (the
    # settlement must not be silently erased; ADR 0011).
    creator = await bound_user_factory()
    account_id = await _make_account(household_singleton, creator.id)
    tx_id = await _make_transaction(
        household_singleton, account_id=account_id, created_by=creator.id
    )
    await _make_settlement(
        household_singleton, created_by=creator.id, linked_transaction_id=tx_id
    )

    tx = (
        await household_singleton.execute(select(Transaction).where(Transaction.id == tx_id))
    ).scalar_one()
    await household_singleton.delete(tx)
    with pytest.raises(IntegrityError):  # ON DELETE RESTRICT
        await household_singleton.flush()


async def test_delete_creator_is_restricted(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # `created_by` ON DELETE RESTRICT (F02): the settlement author cannot be
    # hard-deleted while a settlement references them. The creator is a SEPARATE
    # user from the account/tx owner AND from both sides of the underlying debt,
    # so the RESTRICT under test is isolated from the (also-RESTRICT) account /
    # debt user FKs (gabarit `test_delete_user_referenced_by_share_request`).
    owner = await bound_user_factory()
    debtor = await bound_user_factory()
    creator = await bound_user_factory()
    account_id = await _make_account(household_singleton, owner.id)
    tx_id = await _make_transaction(
        household_singleton, account_id=account_id, created_by=owner.id
    )
    await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=owner.id,
        account_id=account_id,
        source_transaction_id=tx_id,
    )
    await _make_settlement(
        household_singleton, created_by=creator.id, linked_transaction_id=tx_id
    )

    await household_singleton.delete(creator)
    with pytest.raises(IntegrityError):  # ON DELETE RESTRICT
        await household_singleton.flush()


async def test_delete_debt_orphans_non_virtual_settlement(
    household_singleton: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # Assumed behaviour (ADR 0011, Refined-by E10): a non-virtual settlement with
    # a single line on a debt; deleting the debt CASCADEs the line, yet the
    # settlement AND its `linked_transaction` survive without lines — the wire
    # transfer stays traced by `linked_transaction_id` (RESTRICT, accounting
    # proof preserved), the distribution is regenerable like the debt itself.
    debtor = await bound_user_factory()
    creditor = await bound_user_factory()
    account_id = await _make_account(household_singleton, creditor.id)
    tx_id = await _make_transaction(
        household_singleton, account_id=account_id, created_by=creditor.id
    )
    debt = await _make_debt(
        household_singleton,
        from_user_id=debtor.id,
        to_user_id=creditor.id,
        account_id=account_id,
        source_transaction_id=tx_id,
    )
    settlement = await _make_settlement(
        household_singleton, created_by=creditor.id, linked_transaction_id=tx_id
    )
    await _make_line(
        household_singleton, settlement_id=settlement.id, debt_id=debt.id
    )
    settlement_id = settlement.id

    await household_singleton.delete(debt)
    await household_singleton.flush()

    line_count = (
        await household_singleton.execute(
            text("SELECT count(*) FROM settlement_lines WHERE settlement_id = :id"),
            {"id": settlement_id},
        )
    ).scalar_one()
    assert line_count == 0  # line CASCADEd away with the debt
    # ... but the settlement itself survives.
    survivor = (
        await household_singleton.execute(
            select(Settlement).where(Settlement.id == settlement_id)
        )
    ).scalar_one_or_none()
    assert survivor is not None
    assert survivor.linked_transaction_id == tx_id  # wire transfer still traced
