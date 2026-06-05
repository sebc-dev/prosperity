"""Integration tests for `list_debts_for_user` (S09.4, P09.4.1).

Drives the read path against a real Postgres (testcontainers): bornage to the
token, server-side enrichment (`short_label` from the active share request;
`category_id`/`date` from a fresh join on the source transaction), and the
debtor-side masking of `source_transaction_id` AND `account_id` (review #22 B1).
`materialization_trace` is absent from the DTO by construction.

A debt is seeded the real way — `create_share_request` materialises it from a
confirmed personal-account transaction — so the join targets exercised here are
the production ones (active SR, tx-level `category_id`/`date`).
"""

from __future__ import annotations

import contextlib
import datetime as dt
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import event, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.modules.debts.models import Debt
from backend.modules.debts.public import (
    DebtDirection,
    aggregate_by_counterparty,
    list_debts_for_user,
)
from backend.modules.debts.service.share_request import create_share_request
from backend.modules.transactions.models import Transaction
from tests.factories.sqlalchemy import CategoryFactory
from tests.integration._debts_helpers import debt_id_between, settle_debt


@contextlib.asynccontextmanager
async def _count_select_debts(session: AsyncSession) -> AsyncGenerator[list[str]]:
    """Capture every SQL statement executed on the session's connection.

    Listens on the underlying sync connection (`before_cursor_execute`) so a
    re-introduced N+1 (one `compute_remaining` per debt) would surface as extra
    `SELECT ... FROM debts` statements. The N+1 lock is a real executable assert,
    not a documented invariant.
    """
    sync_conn = (await session.connection()).sync_connection
    statements: list[str] = []

    def _before(conn, cursor, statement, parameters, ctx, executemany) -> None:  # noqa: ANN001, PLR0913
        statements.append(statement)

    event.listen(sync_conn, "before_cursor_execute", _before)
    try:
        yield statements
    finally:
        event.remove(sync_conn, "before_cursor_execute", _before)


TxFactoryBundle = Callable[[], Awaitable[tuple[type, type, type, type]]]

_TX_DATE = dt.date(2026, 3, 15)


@dataclass
class _DebtSeed:
    creditor_id: uuid.UUID
    debtor_id: uuid.UUID
    account_id: uuid.UUID
    tx_id: uuid.UUID
    category_id: uuid.UUID
    short_label: str
    amount_cents: int


class _Builder:
    """Seeds users and materialised debts on the test's session (shared connection)."""

    def __init__(self, session: AsyncSession, factories: TxFactoryBundle) -> None:
        self._session = session
        self._factories = factories
        self._users: dict[str, uuid.UUID] = {}

    async def bind(self) -> None:
        self._uf, self._af, self._tf, self._sf = await self._factories()

    async def user(self, email: str) -> uuid.UUID:
        if email not in self._users:

            def _do(_s: Session) -> uuid.UUID:
                return self._uf(email=email).id

            self._users[email] = await self._session.run_sync(_do)
        return self._users[email]

    async def debt(
        self,
        *,
        creditor: str,
        debtor: str,
        amount_cents: int = 4000,
        short_label: str = "Courses",
    ) -> _DebtSeed:
        creditor_id = await self.user(creditor)
        debtor_id = await self.user(debtor)

        def _do(_s: Session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
            cat = CategoryFactory()
            account = self._af(owner_id=creditor_id, name=f"{creditor} perso")
            tx = self._tf(
                account_id=account.id,
                created_by=creditor_id,
                state="confirmed",
                category_id=cat.id,
                date=_TX_DATE,
                splits__amount_cents=amount_cents,
            )
            return account.id, tx.id, cat.id

        account_id, tx_id, category_id = await self._session.run_sync(_do)
        await create_share_request(
            self._session,
            transaction_id=tx_id,
            requested_from=debtor_id,
            ratio=Decimal("1.0"),
            short_label=short_label,
            by_user_id=creditor_id,
        )
        return _DebtSeed(
            creditor_id=creditor_id,
            debtor_id=debtor_id,
            account_id=account_id,
            tx_id=tx_id,
            category_id=category_id,
            short_label=short_label,
            amount_cents=amount_cents,
        )


async def _builder(session: AsyncSession, factories: TxFactoryBundle) -> _Builder:
    b = _Builder(session, factories)
    await b.bind()
    return b


# ---------------------------------------------------------------------------
# Bornage to the token
# ---------------------------------------------------------------------------


async def test_list_returns_debts_where_user_is_creditor_or_debtor(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    b = await _builder(household_singleton, bound_transaction_factories)
    seed = await b.debt(creditor="alice@example.com", debtor="bob@example.com")
    charlie = await b.user("charlie@example.com")

    as_creditor = await list_debts_for_user(household_singleton, user_id=seed.creditor_id)
    as_debtor = await list_debts_for_user(household_singleton, user_id=seed.debtor_id)
    as_third_party = await list_debts_for_user(household_singleton, user_id=charlie)

    assert len(as_creditor) == 1
    assert len(as_debtor) == 1
    assert as_third_party == []  # a third party never sees the pair's debt


async def test_list_enriches_short_label_from_active_share_request(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    b = await _builder(household_singleton, bound_transaction_factories)
    seed = await b.debt(
        creditor="alice@example.com", debtor="bob@example.com", short_label="Restaurant"
    )

    [debt] = await list_debts_for_user(household_singleton, user_id=seed.creditor_id)
    assert debt.short_label == "Restaurant"


async def test_list_enriches_category_id_and_date_by_join(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    b = await _builder(household_singleton, bound_transaction_factories)
    seed = await b.debt(creditor="alice@example.com", debtor="bob@example.com")

    [debt] = await list_debts_for_user(household_singleton, user_id=seed.creditor_id)
    assert debt.category_id == seed.category_id
    assert debt.date == _TX_DATE

    # Freshness: re-categorising the source tx changes the read (not denormalised).
    new_cat_id = await household_singleton.run_sync(lambda _s: CategoryFactory().id)
    await household_singleton.execute(
        update(Transaction).where(Transaction.id == seed.tx_id).values(category_id=new_cat_id)
    )
    await household_singleton.flush()

    [debt_after] = await list_debts_for_user(household_singleton, user_id=seed.creditor_id)
    assert debt_after.category_id == new_cat_id


# ---------------------------------------------------------------------------
# Masking (non-leak) — the security core of the story
# ---------------------------------------------------------------------------


async def test_debtor_does_not_see_source_transaction_id_nor_account_id(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    b = await _builder(household_singleton, bound_transaction_factories)
    seed = await b.debt(creditor="alice@example.com", debtor="bob@example.com")

    [debt] = await list_debts_for_user(household_singleton, user_id=seed.debtor_id)
    assert debt.source_transaction_id is None
    assert debt.account_id is None
    # The debtor still gets the contextual fields they are entitled to.
    assert debt.short_label == seed.short_label
    assert debt.category_id == seed.category_id
    assert debt.date == _TX_DATE


async def test_owner_sees_source_transaction_id_and_account_id(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    b = await _builder(household_singleton, bound_transaction_factories)
    seed = await b.debt(creditor="alice@example.com", debtor="bob@example.com")

    [debt] = await list_debts_for_user(household_singleton, user_id=seed.creditor_id)
    assert debt.source_transaction_id == seed.tx_id
    assert debt.account_id == seed.account_id


async def test_materialization_trace_never_in_dto(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    b = await _builder(household_singleton, bound_transaction_factories)
    seed = await b.debt(creditor="alice@example.com", debtor="bob@example.com")

    [debt] = await list_debts_for_user(household_singleton, user_id=seed.creditor_id)
    assert not hasattr(debt, "materialization_trace")


async def test_masking_is_per_debt_not_per_user(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # Alice is creditor on one debt (Bob→Alice) AND debtor on another with the
    # same counterparty Bob (Alice→Bob, via Bob's SR). Masking must operate
    # per-debt: owner side reveals source fields, debtor side hides them.
    b = await _builder(household_singleton, bound_transaction_factories)
    alice = await b.user("alice@example.com")
    owned = await b.debt(creditor="alice@example.com", debtor="bob@example.com")
    owed = await b.debt(creditor="bob@example.com", debtor="alice@example.com")

    debts = await list_debts_for_user(household_singleton, user_id=alice)
    assert len(debts) == 2

    creditor_side = next(d for d in debts if d.to_user_id == alice)
    debtor_side = next(d for d in debts if d.from_user_id == alice)
    assert creditor_side.source_transaction_id == owned.tx_id
    assert creditor_side.account_id == owned.account_id
    assert debtor_side.source_transaction_id is None
    assert debtor_side.account_id is None
    # `owed` is the Alice→Bob debt; its source tx must stay hidden from Alice.
    assert debtor_side.source_transaction_id != owed.tx_id


# ---------------------------------------------------------------------------
# direction + counterparty (anti-IDOR)
# ---------------------------------------------------------------------------


async def test_direction_owed_to_me_and_owed_by_me(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    b = await _builder(household_singleton, bound_transaction_factories)
    seed = await b.debt(creditor="alice@example.com", debtor="bob@example.com")

    alice_to_me = await list_debts_for_user(
        household_singleton, user_id=seed.creditor_id, direction=DebtDirection.OWED_TO_ME
    )
    alice_by_me = await list_debts_for_user(
        household_singleton, user_id=seed.creditor_id, direction=DebtDirection.OWED_BY_ME
    )
    bob_to_me = await list_debts_for_user(
        household_singleton, user_id=seed.debtor_id, direction=DebtDirection.OWED_TO_ME
    )
    bob_by_me = await list_debts_for_user(
        household_singleton, user_id=seed.debtor_id, direction=DebtDirection.OWED_BY_ME
    )

    assert len(alice_to_me) == 1  # Alice is creditor
    assert alice_by_me == []
    assert bob_to_me == []
    assert len(bob_by_me) == 1  # Bob is debtor


async def test_counterparty_filter_after_bornage(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    b = await _builder(household_singleton, bound_transaction_factories)
    seed = await b.debt(creditor="alice@example.com", debtor="bob@example.com")
    charlie = await b.user("charlie@example.com")

    with_bob = await list_debts_for_user(
        household_singleton, user_id=seed.creditor_id, counterparty=seed.debtor_id
    )
    with_charlie = await list_debts_for_user(
        household_singleton, user_id=seed.creditor_id, counterparty=charlie
    )

    assert len(with_bob) == 1
    assert with_charlie == []


async def test_counterparty_is_not_an_ownership_selector(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # A third-party debt (Charlie→Dave) never surfaces for Alice, even when she
    # passes counterparty=charlie — `with` filters, it never selects an owner.
    b = await _builder(household_singleton, bound_transaction_factories)
    alice = await b.user("alice@example.com")
    await b.debt(creditor="charlie@example.com", debtor="dave@example.com")
    charlie = await b.user("charlie@example.com")

    via_filter = await list_debts_for_user(household_singleton, user_id=alice, counterparty=charlie)
    assert via_filter == []


async def test_order_follows_created_at(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # Absolute order, not mere stability: back-date the SECOND-inserted debt
    # (Charlie's) BEFORE the first (Bob's), decoupling `created_at` from insertion
    # and from the random `id`. A correct `ORDER BY created_at, id` then returns
    # Charlie first; an order driven by insertion order would return Bob first.
    b = await _builder(household_singleton, bound_transaction_factories)
    alice = await b.user("alice@example.com")
    bob = await b.debt(creditor="alice@example.com", debtor="bob@example.com")
    charlie = await b.debt(creditor="alice@example.com", debtor="charlie@example.com")

    await household_singleton.execute(
        update(Debt)
        .where(Debt.from_user_id == charlie.debtor_id)
        .values(created_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC))
    )
    await household_singleton.execute(
        update(Debt)
        .where(Debt.from_user_id == bob.debtor_id)
        .values(created_at=dt.datetime(2026, 6, 1, tzinfo=dt.UTC))
    )
    await household_singleton.flush()

    debts = await list_debts_for_user(household_singleton, user_id=alice)
    assert len(debts) == 2
    # `from_user_id` of a debt is its debtor → Charlie's debt, back-dated, comes first.
    assert [d.from_user_id for d in debts] == [charlie.debtor_id, bob.debtor_id]
    # And the order is stable across reads.
    again = await list_debts_for_user(household_singleton, user_id=alice)
    assert [d.from_user_id for d in again] == [charlie.debtor_id, bob.debtor_id]


async def test_order_tie_break_by_id_on_equal_created_at(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # Tie-break: when two debts share the SAME `created_at`, the second key of
    # `ORDER BY created_at, id` decides. Force both `created_at` equal, then assert
    # the rows come back in `id`-ascending order (not insertion order).
    b = await _builder(household_singleton, bound_transaction_factories)
    alice = await b.user("alice@example.com")
    bob = await b.debt(creditor="alice@example.com", debtor="bob@example.com")
    charlie = await b.debt(creditor="alice@example.com", debtor="charlie@example.com")

    same = dt.datetime(2026, 3, 1, tzinfo=dt.UTC)
    debtors = [bob.debtor_id, charlie.debtor_id]
    await household_singleton.execute(
        update(Debt).where(Debt.from_user_id.in_(debtors)).values(created_at=same)
    )
    await household_singleton.flush()

    # Resolve each debt's (debtor, id) to derive the expected id-ascending order.
    id_rows = (
        (
            await household_singleton.execute(
                select(Debt.from_user_id, Debt.id).where(Debt.from_user_id.in_(debtors))
            )
        )
        .tuples()
        .all()
    )
    # Postgres orders `uuid` by its 16 bytes big-endian == Python `UUID` (`.int`).
    expected = [debtor_id for debtor_id, _ in sorted(id_rows, key=lambda r: r[1])]

    debts = await list_debts_for_user(household_singleton, user_id=alice)
    assert [d.from_user_id for d in debts] == expected


# ---------------------------------------------------------------------------
# remaining_cents (S10.3) — read path enrichment + aggregate on the net balance
# ---------------------------------------------------------------------------


async def test_remaining_cents_visible_to_both_parties(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # 50€ debt − 30€ settled → remaining 2000, visible to creditor AND debtor.
    b = await _builder(household_singleton, bound_transaction_factories)
    seed = await b.debt(creditor="alice@example.com", debtor="bob@example.com", amount_cents=5000)
    debt_id = await debt_id_between(
        household_singleton, creditor_id=seed.creditor_id, debtor_id=seed.debtor_id
    )
    await settle_debt(
        household_singleton, debt_id=debt_id, amount_cents=3000, created_by=seed.creditor_id
    )

    [as_creditor] = await list_debts_for_user(household_singleton, user_id=seed.creditor_id)
    [as_debtor] = await list_debts_for_user(household_singleton, user_id=seed.debtor_id)
    assert as_creditor.remaining_cents == 2000
    assert as_debtor.remaining_cents == 2000  # legitimate debtor info (D5)


async def test_settled_debt_listed_with_zero_remaining(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # D7: a fully settled debt stays in GET /debts (complete register) with
    # remaining_cents = 0 — only list_open_debts_between filters it out.
    b = await _builder(household_singleton, bound_transaction_factories)
    seed = await b.debt(creditor="alice@example.com", debtor="bob@example.com", amount_cents=5000)
    debt_id = await debt_id_between(
        household_singleton, creditor_id=seed.creditor_id, debtor_id=seed.debtor_id
    )
    await settle_debt(
        household_singleton, debt_id=debt_id, amount_cents=5000, created_by=seed.creditor_id
    )

    [debt] = await list_debts_for_user(household_singleton, user_id=seed.creditor_id)
    assert debt.remaining_cents == 0


async def test_aggregate_uses_remaining_balance(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # D6: by-counterparty aggregates the NET of remainings — a partially settled
    # debt contributes its remaining (3000), not its initial amount (5000), yet
    # still counts toward debts_count.
    b = await _builder(household_singleton, bound_transaction_factories)
    seed = await b.debt(creditor="alice@example.com", debtor="bob@example.com", amount_cents=5000)
    debt_id = await debt_id_between(
        household_singleton, creditor_id=seed.creditor_id, debtor_id=seed.debtor_id
    )
    await settle_debt(
        household_singleton, debt_id=debt_id, amount_cents=2000, created_by=seed.creditor_id
    )

    [row] = await aggregate_by_counterparty(household_singleton, user_id=seed.creditor_id)
    assert row.user_id == seed.debtor_id
    assert row.net_amount_cents == 3000  # remaining, not the 5000 initial
    assert row.debts_count == 1
    # D8: the net carries the debt currency through the remaining-based aggregate.
    assert row.currency == "EUR"


async def test_list_debts_is_single_query_no_n_plus_1(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    # K = 2 debts (Alice creditor on Bob AND Charlie), each partially settled.
    # The remaining is computed in the SAME query (shared `_settled_subq`), so a
    # SINGLE `SELECT ... FROM debts` is issued regardless of the row count — a
    # re-introduced per-debt `compute_remaining` (N+1) would fail this.
    b = await _builder(household_singleton, bound_transaction_factories)
    alice = await b.user("alice@example.com")
    bob = await b.debt(creditor="alice@example.com", debtor="bob@example.com", amount_cents=5000)
    charlie = await b.debt(
        creditor="alice@example.com", debtor="charlie@example.com", amount_cents=4000
    )
    for seed in (bob, charlie):
        debt_id = await debt_id_between(
            household_singleton, creditor_id=seed.creditor_id, debtor_id=seed.debtor_id
        )
        await settle_debt(
            household_singleton, debt_id=debt_id, amount_cents=1000, created_by=seed.creditor_id
        )

    async with _count_select_debts(household_singleton) as statements:
        debts = await list_debts_for_user(household_singleton, user_id=alice)

    assert len(debts) == 2  # K ≥ 2, so an N+1 would be observable
    select_debts = [s for s in statements if "FROM debts" in s]
    assert len(select_debts) == 1, select_debts
