"""Integration tests for `transactions.service.lifecycle` — draft + splits (S07.4, P07.4.1).

Drives `create_draft` / `add_split` / `remove_split` (+ the private mapper
`_to_domain` / `_load_aggregate`) against a real Postgres so the DB-level
behaviour fires: the `Transaction`/`Split` INSERTs/DELETEs, the
`(amount_cents, currency) ↔ Money` round-trip, the draft-only split window
(D5), and — on `committed_engine` — the no-commit contract (flush-only,
ADR 0015) verified from an independent session.

Two tiers (gabarit `test_accounts_service.py` / `test_budget_categories_service.py`):

* Rollback-isolated (`bound_transaction_factories`): persistence, mapper
  round-trips (expense vs transfer), and the not-found / draft-only guards.
* Real-commit (`committed_engine` / `_clean_committed_db`): the flush-only
  proof, checked from a fresh session.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.modules.accounts.domain import AccountType
from backend.modules.accounts.models import Account, Household
from backend.modules.auth.models import User, UserRole
from backend.modules.transactions import domain
from backend.modules.transactions.models import Split as SplitModel
from backend.modules.transactions.models import Transaction as TxModel
from backend.modules.transactions.service.lifecycle import (
    SplitNotFoundError,
    TransactionNotFoundError,
    _load_aggregate,  # pyright: ignore[reportPrivateUsage]
    _to_domain,  # pyright: ignore[reportPrivateUsage]
    add_split,
    create_draft,
    remove_split,
)
from backend.shared.money import Money

Factories = tuple[type, type, type, type]
BoundFactories = Callable[[], Awaitable[Factories]]


# ---------------------------------------------------------------------------
# Rollback-isolated tier helpers
# ---------------------------------------------------------------------------


async def _seed_account(
    session: AsyncSession, bound: BoundFactories
) -> tuple[uuid.UUID, uuid.UUID]:
    """Build a user + personal account, returning `(account_id, user_id)`."""
    user_factory, account_factory, _tx, _split = await bound()

    def _build(_sync: object) -> tuple[uuid.UUID, uuid.UUID]:
        user = user_factory()
        account = account_factory(owner_id=user.id)
        return account.id, user.id

    return await session.run_sync(_build)


async def _seed_second_account(session: AsyncSession, bound: BoundFactories) -> uuid.UUID:
    """Build a second personal account (transfer counterparty)."""
    user_factory, account_factory, _tx, _split = await bound()

    def _build(_sync: object) -> uuid.UUID:
        user = user_factory()
        return account_factory(owner_id=user.id).id

    return await session.run_sync(_build)


async def _seed_transaction(
    session: AsyncSession,
    bound: BoundFactories,
    account_id: uuid.UUID,
    user_id: uuid.UUID,
    **tx_kwargs: object,
) -> uuid.UUID:
    """Build a transaction (factory) in the given shape; returns its id."""
    _u, _a, tx_factory, _split = await bound()

    def _build(_sync: object) -> uuid.UUID:
        return tx_factory(account_id=account_id, created_by=user_id, **tx_kwargs).id

    return await session.run_sync(_build)


# ---------------------------------------------------------------------------
# create_draft
# ---------------------------------------------------------------------------


async def test_create_draft_persists_empty_draft(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)

    tx = await create_draft(household_singleton, account_id=account_id, by_user_id=user_id)

    assert tx.id is not None  # PK surfaced at flush
    assert tx.state is domain.TransactionState.DRAFT
    assert tx.created_by == user_id
    assert tx.date == datetime.now(UTC).date()
    assert tx.splits == ()
    # 0 split rows persisted.
    split_count = (
        await household_singleton.execute(
            select(func.count()).select_from(SplitModel).where(SplitModel.transaction_id == tx.id)
        )
    ).scalar_one()
    assert split_count == 0


async def test_create_draft_honours_explicit_date(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    explicit = dt.date(2025, 3, 14)

    tx = await create_draft(
        household_singleton, account_id=account_id, by_user_id=user_id, date=explicit
    )

    assert tx.date == explicit


# ---------------------------------------------------------------------------
# add_split / remove_split
# ---------------------------------------------------------------------------


async def test_add_split_appends_and_maps_money(
    household_singleton: AsyncSession,
    bound_transaction_factories: BoundFactories,
    bound_category_factory: Callable[..., Awaitable[object]],
) -> None:
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx = await create_draft(household_singleton, account_id=account_id, by_user_id=user_id)
    category = await bound_category_factory()
    cat = category.id  # type: ignore[attr-defined]

    after = await add_split(
        household_singleton,
        tx_id=tx.id,
        account_id=account_id,
        amount_cents=-1500,
        currency="EUR",
        category_id=cat,
    )

    assert len(after.splits) == 1
    assert after.splits[0].amount == Money(-1500, "EUR")
    assert after.splits[0].category_id == cat
    assert after.splits[0].account_id == account_id


async def test_add_split_keeps_null_category(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx = await create_draft(household_singleton, account_id=account_id, by_user_id=user_id)

    after = await add_split(
        household_singleton, tx_id=tx.id, account_id=account_id, amount_cents=1000, currency="EUR"
    )

    assert after.splits[0].category_id is None


async def test_to_domain_carries_leg_role_from_db(
    household_singleton: AsyncSession,
    bound_transaction_factories: BoundFactories,
    bound_category_factory: Callable[..., Awaitable[object]],
) -> None:
    # S08.5.1: `_to_domain` must reflect the AUTHORITATIVE column, not re-derive
    # it — a categoryless leg maps to `funding`, a categorised one to
    # `classification` (proves the mapper reads `s.leg_role`).
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx = await create_draft(household_singleton, account_id=account_id, by_user_id=user_id)
    category = await bound_category_factory()
    cat = category.id  # type: ignore[attr-defined]

    await add_split(
        household_singleton, tx_id=tx.id, account_id=account_id, amount_cents=-1500, currency="EUR"
    )
    await add_split(
        household_singleton,
        tx_id=tx.id,
        account_id=account_id,
        amount_cents=1500,
        currency="EUR",
        category_id=cat,
    )

    tx_model, splits = await _load_aggregate(household_singleton, tx.id)
    aggregate = _to_domain(tx_model, splits)

    by_role = {s.leg_role for s in aggregate.splits}
    assert by_role == {"funding", "classification"}
    funding = next(s for s in aggregate.splits if s.category_id is None)
    classified = next(s for s in aggregate.splits if s.category_id is not None)
    assert funding.leg_role == "funding"
    assert classified.leg_role == "classification"


async def test_to_domain_reads_divergent_leg_role_not_re_derived(
    household_singleton: AsyncSession,
    bound_transaction_factories: BoundFactories,
) -> None:
    # Review #136: DISCRIMINATING proof that `_to_domain` READS the column and
    # does not re-derive it. We persist a DIVERGENT row — `leg_role` is
    # 'classification' while `category_id` IS NULL — which is exactly what the
    # domain validator would re-derive as 'funding'. Because the mapper passes
    # `leg_role=s.leg_role`, the aggregate keeps 'classification'; a fortuitous
    # re-derivation would instead yield 'funding'. This is the case S08.5.2 must
    # be able to flag (a classification leg with no category = to be refused).
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx = await create_draft(household_singleton, account_id=account_id, by_user_id=user_id)

    # Raw INSERT bypasses the ORM context default (which would derive 'funding').
    await household_singleton.execute(
        text(
            "INSERT INTO splits "
            "(id, transaction_id, account_id, amount_cents, currency, leg_role) "
            "VALUES (:id, :tx, :acc, 0, 'EUR', 'classification')"
        ),
        {"id": uuid.uuid4(), "tx": tx.id, "acc": account_id},
    )
    await household_singleton.flush()

    tx_model, splits = await _load_aggregate(household_singleton, tx.id)
    aggregate = _to_domain(tx_model, splits)

    assert len(aggregate.splits) == 1
    assert aggregate.splits[0].category_id is None
    # Authoritative DB value preserved — NOT the 'funding' the validator derives.
    assert aggregate.splits[0].leg_role == "classification"


async def test_remove_split_removes_the_right_one(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx = await create_draft(household_singleton, account_id=account_id, by_user_id=user_id)
    await add_split(
        household_singleton, tx_id=tx.id, account_id=account_id, amount_cents=-1000, currency="EUR"
    )
    await add_split(
        household_singleton, tx_id=tx.id, account_id=account_id, amount_cents=1000, currency="EUR"
    )
    # Re-read to grab a concrete split id.
    _tx, splits = await _load_aggregate(household_singleton, tx.id)
    victim = splits[0].id

    after = await remove_split(household_singleton, tx_id=tx.id, split_id=victim)

    assert len(after.splits) == 1
    remaining_ids = (
        (
            await household_singleton.execute(
                select(SplitModel.id).where(SplitModel.transaction_id == tx.id)
            )
        )
        .scalars()
        .all()
    )
    assert victim not in remaining_ids


async def test_remove_unknown_split_raises_split_not_found(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx = await create_draft(household_singleton, account_id=account_id, by_user_id=user_id)
    ghost = uuid.uuid4()

    with pytest.raises(SplitNotFoundError) as exc:
        await remove_split(household_singleton, tx_id=tx.id, split_id=ghost)
    assert exc.value.code == "split_not_found"
    assert exc.value.split_id == ghost


async def test_unknown_transaction_raises_not_found(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    # Needs the schema present; no seeding required beyond that.
    await _seed_account(household_singleton, bound_transaction_factories)
    ghost = uuid.uuid4()

    with pytest.raises(TransactionNotFoundError) as exc:
        await add_split(
            household_singleton,
            tx_id=ghost,
            account_id=uuid.uuid4(),
            amount_cents=1,
            currency="EUR",
        )
    assert exc.value.code == "transaction_not_found"
    assert exc.value.transaction_id == ghost


# ---------------------------------------------------------------------------
# Draft-only split window (D5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("state", ["planned", "confirmed", "void"])
async def test_add_split_rejected_outside_draft(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories, state: str
) -> None:
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    # The factory sets the column directly; a balanced pair keeps a `confirmed`
    # row readable by the validating mapper (zero-sum holds).
    tx_id = await _seed_transaction(
        household_singleton, bound_transaction_factories, account_id, user_id, state=state
    )

    with pytest.raises(domain.ImmutableFieldViolation) as exc:
        await add_split(
            household_singleton,
            tx_id=tx_id,
            account_id=account_id,
            amount_cents=1,
            currency="EUR",
        )
    assert exc.value.field == "splits"


@pytest.mark.parametrize("state", ["planned", "confirmed", "void"])
async def test_remove_split_rejected_outside_draft(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories, state: str
) -> None:
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_transaction(
        household_singleton, bound_transaction_factories, account_id, user_id, state=state
    )
    _tx, splits = await _load_aggregate(household_singleton, tx_id)

    with pytest.raises(domain.ImmutableFieldViolation) as exc:
        await remove_split(household_singleton, tx_id=tx_id, split_id=splits[0].id)
    assert exc.value.field == "splits"


# ---------------------------------------------------------------------------
# Mapper round-trips
# ---------------------------------------------------------------------------


async def test_mapper_round_trip_expense(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    # Default factory: a balanced pair on the SAME account → not a transfer.
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_transaction(
        household_singleton, bound_transaction_factories, account_id, user_id, state="confirmed"
    )

    tx, splits = await _load_aggregate(household_singleton, tx_id)
    agg = _to_domain(tx, splits)

    assert not domain.is_transfer(agg)
    assert len({s.amount.currency for s in agg.splits}) == 1


async def test_mapper_round_trip_transfer(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    # Two splits on DISTINCT accounts + non-empty tags → is_transfer True, and
    # `_load_aggregate` orders splits by id deterministically.
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    other_account = await _seed_second_account(household_singleton, bound_transaction_factories)
    _u, _a, tx_factory, split_factory = await bound_transaction_factories()

    def _build(_sync: object) -> uuid.UUID:
        tx = tx_factory(
            account_id=account_id,
            created_by=user_id,
            state="confirmed",
            splits=False,
            tags=["voyage"],
        )
        split_factory(transaction_id=tx.id, account_id=account_id, amount_cents=-2000)
        split_factory(transaction_id=tx.id, account_id=other_account, amount_cents=2000)
        return tx.id

    tx_id = await household_singleton.run_sync(_build)

    tx, splits = await _load_aggregate(household_singleton, tx_id)
    agg = _to_domain(tx, splits)

    assert domain.is_transfer(agg)
    assert agg.tags == ("voyage",)
    # Deterministic order: the loaded split ids are ascending.
    loaded_ids = [s.id for s in splits]
    assert loaded_ids == sorted(loaded_ids)


async def test_mapper_raises_on_unbalanced_confirmed_row(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    # Defense-in-depth (D11): `_to_domain` builds via the VALIDATING constructor,
    # so a `confirmed` row that became unbalanced in the DB (no zero-sum CHECK at
    # the SQL level — the invariant lives in the domain) raises on read instead of
    # silently yielding a broken aggregate. The DB row is forged directly via the
    # factory (same currency → it is `UnbalancedTransactionError`, not the mixed-
    # currency `IncompatibleCurrencyError`).
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    _u, _a, tx_factory, split_factory = await bound_transaction_factories()

    def _build(_sync: object) -> uuid.UUID:
        tx = tx_factory(account_id=account_id, created_by=user_id, state="confirmed", splits=False)
        split_factory(transaction_id=tx.id, account_id=account_id, amount_cents=-2000)
        split_factory(transaction_id=tx.id, account_id=account_id, amount_cents=1000)
        return tx.id

    tx_id = await household_singleton.run_sync(_build)

    tx, splits = await _load_aggregate(household_singleton, tx_id)
    with pytest.raises(domain.UnbalancedTransactionError):
        _to_domain(tx, splits)


# ---------------------------------------------------------------------------
# Real-commit tier — flush-only (ADR 0015)
# ---------------------------------------------------------------------------


async def _seed_committed_account(
    sm: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID]:
    """Seed the singleton household + a user + a personal account (committed)."""
    async with sm() as session:
        session.add(Household(name="Committed", base_currency="EUR"))
        await session.commit()
    async with sm() as session:
        user = User(
            email="tx-owner@example.com",
            password_hash="x" * 60,
            display_name="owner",
            role=UserRole.MEMBER,
        )
        session.add(user)
        await session.flush()
        account = Account(name="Perso", type=AccountType.COURANT, currency="EUR", owner_id=user.id)
        session.add(account)
        await session.flush()
        account_id, user_id = account.id, user.id
        await session.commit()
    return account_id, user_id


@pytest.mark.usefixtures("_clean_committed_db")
async def test_create_draft_does_not_commit(committed_engine: AsyncEngine) -> None:
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    account_id, user_id = await _seed_committed_account(sm)

    async with sm() as session:
        tx = await create_draft(session, account_id=account_id, by_user_id=user_id)
        assert tx.id is not None
        # Deliberately no commit — closing the session rolls back.

    async with sm() as session:
        count = (await session.execute(select(func.count()).select_from(TxModel))).scalar_one()
        assert count == 0
