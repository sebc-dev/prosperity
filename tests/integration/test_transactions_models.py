"""Integration tests for `transactions.models` (S07.2, P07.2.3).

Exercise the persisted behaviour the unit tier and the level-1 snapshot
cannot reach: the `ON DELETE CASCADE`/`RESTRICT` FKs, the `text[]` round-trip,
the dormant `savings_goal_id` (no active FK), and nullable `category_id` on
both tables. Pure `flush` + rollback isolation (`auth_schema`/`db_session`) —
FK violations surface at `flush` because they are DB-level.
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
from backend.modules.budget.models import Category
from backend.modules.transactions.models import Split, Transaction

# Every test inserts an `Account`, whose `household_id` FK requires the
# singleton `household` row to exist (ADR 0010); seed it for the whole module.
pytestmark = pytest.mark.usefixtures("household_singleton")


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


async def _make_category(session: AsyncSession) -> uuid.UUID:
    category = Category(name="Courses")
    session.add(category)
    await session.flush()
    return category.id


async def test_transaction_and_splits_persist(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    user = await bound_user_factory()
    user_id = user.id
    account_id = await _make_account(auth_schema, user_id)

    tx = Transaction(
        account_id=account_id,
        date=dt.date(2026, 1, 15),
        state="draft",
        created_by=user_id,
    )
    auth_schema.add(tx)
    await auth_schema.flush()
    tx_id = tx.id
    auth_schema.add_all(
        [
            Split(transaction_id=tx_id, account_id=account_id, amount_cents=-1000, currency="EUR"),
            Split(transaction_id=tx_id, account_id=account_id, amount_cents=1000, currency="EUR"),
        ]
    )
    await auth_schema.flush()

    # `expire_all()` forces a re-hydrate from Postgres — without it the
    # identity-map returns the in-memory object and only the ORM default is
    # tested, not the round-trip.
    auth_schema.expire_all()
    reloaded = (
        await auth_schema.execute(select(Transaction).where(Transaction.id == tx_id))
    ).scalar_one()
    assert reloaded.created_at is not None
    assert reloaded.tags == []  # ORM `default=list`
    assert reloaded.debt_generation_override == "default"
    assert reloaded.confirmed_at is None
    assert reloaded.voided_at is None


async def test_delete_transaction_cascades_splits(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # Livrable observable: deleting a Transaction removes its Splits (CASCADE).
    user = await bound_user_factory()
    account_id = await _make_account(auth_schema, user.id)
    tx = Transaction(
        account_id=account_id, date=dt.date(2026, 1, 1), state="draft", created_by=user.id
    )
    auth_schema.add(tx)
    await auth_schema.flush()
    tx_id = tx.id
    auth_schema.add_all(
        [
            Split(transaction_id=tx_id, account_id=account_id, amount_cents=-500, currency="EUR"),
            Split(transaction_id=tx_id, account_id=account_id, amount_cents=500, currency="EUR"),
        ]
    )
    await auth_schema.flush()

    await auth_schema.delete(tx)
    await auth_schema.flush()

    count = (
        await auth_schema.execute(
            text("SELECT count(*) FROM splits WHERE transaction_id = :id"), {"id": tx_id}
        )
    ).scalar_one()
    assert count == 0


async def test_delete_account_referenced_by_transaction_raises_restrict(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # Delta vs acceptance criteria: `transactions.account_id` is RESTRICT
    # (F02 — an account is archived, never hard-deleted).
    user = await bound_user_factory()
    account_id = await _make_account(auth_schema, user.id)
    tx = Transaction(
        account_id=account_id, date=dt.date(2026, 1, 1), state="draft", created_by=user.id
    )
    auth_schema.add(tx)
    await auth_schema.flush()

    account = (
        await auth_schema.execute(select(Account).where(Account.id == account_id))
    ).scalar_one()
    await auth_schema.delete(account)
    with pytest.raises(IntegrityError):
        await auth_schema.flush()


async def test_delete_account_referenced_by_split_raises_restrict(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # A split can target ANOTHER account of the household (transfer case);
    # that account is RESTRICT too.
    user = await bound_user_factory()
    tx_account_id = await _make_account(auth_schema, user.id)
    other_account_id = await _make_account(auth_schema, user.id)
    tx = Transaction(
        account_id=tx_account_id, date=dt.date(2026, 1, 1), state="draft", created_by=user.id
    )
    auth_schema.add(tx)
    await auth_schema.flush()
    auth_schema.add(
        Split(
            transaction_id=tx.id,
            account_id=other_account_id,
            amount_cents=1000,
            currency="EUR",
        )
    )
    await auth_schema.flush()

    other = (
        await auth_schema.execute(select(Account).where(Account.id == other_account_id))
    ).scalar_one()
    await auth_schema.delete(other)
    with pytest.raises(IntegrityError):
        await auth_schema.flush()


async def test_delete_category_referenced_by_split_raises_restrict(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # RESTRICT is the DB twin of "pas de cascade". Use the least obvious case:
    # the transaction has `category_id=None` but a split is categorised.
    user = await bound_user_factory()
    account_id = await _make_account(auth_schema, user.id)
    category_id = await _make_category(auth_schema)
    tx = Transaction(
        account_id=account_id, date=dt.date(2026, 1, 1), state="draft", created_by=user.id
    )
    auth_schema.add(tx)
    await auth_schema.flush()
    auth_schema.add(
        Split(
            transaction_id=tx.id,
            account_id=account_id,
            category_id=category_id,
            amount_cents=1000,
            currency="EUR",
        )
    )
    await auth_schema.flush()

    category = (
        await auth_schema.execute(select(Category).where(Category.id == category_id))
    ).scalar_one()
    await auth_schema.delete(category)
    with pytest.raises(IntegrityError):
        await auth_schema.flush()


async def test_delete_user_creator_raises_restrict(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # F02: the creator user is disabled, never deleted — `created_by` RESTRICT.
    user = await bound_user_factory()
    account_id = await _make_account(auth_schema, user.id)
    tx = Transaction(
        account_id=account_id, date=dt.date(2026, 1, 1), state="draft", created_by=user.id
    )
    auth_schema.add(tx)
    await auth_schema.flush()

    await auth_schema.delete(user)
    with pytest.raises(IntegrityError):
        await auth_schema.flush()


async def test_split_savings_goal_id_accepts_arbitrary_uuid(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # The dormant column has NO active FK: an arbitrary UUID inserts cleanly.
    user = await bound_user_factory()
    account_id = await _make_account(auth_schema, user.id)
    tx = Transaction(
        account_id=account_id, date=dt.date(2026, 1, 1), state="draft", created_by=user.id
    )
    auth_schema.add(tx)
    await auth_schema.flush()
    orphan = uuid.uuid4()
    auth_schema.add(
        Split(
            transaction_id=tx.id,
            account_id=account_id,
            amount_cents=1000,
            currency="EUR",
            savings_goal_id=orphan,
        )
    )
    await auth_schema.flush()  # no IntegrityError — no FK on savings_goal_id

    stored = (
        await auth_schema.execute(
            text("SELECT savings_goal_id FROM splits WHERE transaction_id = :id"), {"id": tx.id}
        )
    ).scalar_one()
    assert stored == orphan


async def test_tags_array_round_trips(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    user = await bound_user_factory()
    account_id = await _make_account(auth_schema, user.id)
    tx = Transaction(
        account_id=account_id,
        date=dt.date(2026, 1, 1),
        state="draft",
        created_by=user.id,
        tags=["courses", "monoprix"],
    )
    auth_schema.add(tx)
    await auth_schema.flush()
    tx_id = tx.id

    auth_schema.expire_all()
    reloaded = (
        await auth_schema.execute(select(Transaction).where(Transaction.id == tx_id))
    ).scalar_one()
    assert reloaded.tags == ["courses", "monoprix"]


async def test_split_leg_role_defaults_to_funding_when_category_null(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # S08.5.1: the context-sensitive ORM default derives `leg_role` from
    # `category_id` at INSERT — a categoryless split is a funding leg.
    user = await bound_user_factory()
    account_id = await _make_account(auth_schema, user.id)
    tx = Transaction(
        account_id=account_id, date=dt.date(2026, 1, 1), state="draft", created_by=user.id
    )
    auth_schema.add(tx)
    await auth_schema.flush()
    split = Split(transaction_id=tx.id, account_id=account_id, amount_cents=-1000, currency="EUR")
    auth_schema.add(split)
    await auth_schema.flush()

    # Read via raw SQL (gabarit `savings_goal_id`): the context-sensitive Python
    # default leaves the in-memory attribute expired, and an ORM refresh would
    # attempt sync IO inside the async session.
    stored = (
        await auth_schema.execute(
            text("SELECT leg_role FROM splits WHERE id = :id"), {"id": split.id}
        )
    ).scalar_one()
    assert stored == "funding"


async def test_split_leg_role_defaults_to_classification_when_category_set(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # A categorised split derives `classification` (same rule as the back-fill).
    user = await bound_user_factory()
    account_id = await _make_account(auth_schema, user.id)
    category_id = await _make_category(auth_schema)
    tx = Transaction(
        account_id=account_id, date=dt.date(2026, 1, 1), state="draft", created_by=user.id
    )
    auth_schema.add(tx)
    await auth_schema.flush()
    split = Split(
        transaction_id=tx.id,
        account_id=account_id,
        category_id=category_id,
        amount_cents=-1000,
        currency="EUR",
    )
    auth_schema.add(split)
    await auth_schema.flush()

    stored = (
        await auth_schema.execute(
            text("SELECT leg_role FROM splits WHERE id = :id"), {"id": split.id}
        )
    ).scalar_one()
    assert stored == "classification"


async def test_split_leg_role_explicit_value_overrides_default(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # An explicit value wins over the context default (mapper-authoritative path):
    # a categoryless split persisted as `classification` keeps that value.
    user = await bound_user_factory()
    account_id = await _make_account(auth_schema, user.id)
    tx = Transaction(
        account_id=account_id, date=dt.date(2026, 1, 1), state="draft", created_by=user.id
    )
    auth_schema.add(tx)
    await auth_schema.flush()
    split = Split(
        transaction_id=tx.id,
        account_id=account_id,
        category_id=None,
        amount_cents=-1000,
        currency="EUR",
        leg_role="classification",
    )
    auth_schema.add(split)
    await auth_schema.flush()

    stored = (
        await auth_schema.execute(
            text("SELECT leg_role FROM splits WHERE id = :id"), {"id": split.id}
        )
    ).scalar_one()
    assert stored == "classification"


async def test_split_leg_role_check_rejects_unknown_value(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # The defense-in-depth CHECK `ck_splits_leg_role` rejects any out-of-set
    # value reaching the DB via raw SQL (bypassing the ORM default / domain).
    user = await bound_user_factory()
    account_id = await _make_account(auth_schema, user.id)
    tx = Transaction(
        account_id=account_id, date=dt.date(2026, 1, 1), state="draft", created_by=user.id
    )
    auth_schema.add(tx)
    await auth_schema.flush()
    with pytest.raises(IntegrityError):
        await auth_schema.execute(
            text(
                "INSERT INTO splits "
                "(id, transaction_id, account_id, amount_cents, currency, leg_role) "
                "VALUES (:id, :tx, :acc, :amt, :ccy, 'bogus')"
            ),
            {
                "id": uuid.uuid4(),
                "tx": tx.id,
                "acc": account_id,
                "amt": 0,
                "ccy": "EUR",
            },
        )
        await auth_schema.flush()


async def test_category_id_nullable_on_both(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    # Transfer / draft case: both the transaction and its splits may carry
    # `category_id=None` (CONTEXT.md §`splits.category_id NULL`).
    user = await bound_user_factory()
    account_id = await _make_account(auth_schema, user.id)
    tx = Transaction(
        account_id=account_id,
        date=dt.date(2026, 1, 1),
        state="draft",
        created_by=user.id,
        category_id=None,
    )
    auth_schema.add(tx)
    await auth_schema.flush()
    auth_schema.add(
        Split(
            transaction_id=tx.id,
            account_id=account_id,
            category_id=None,
            amount_cents=0,
            currency="EUR",
        )
    )
    await auth_schema.flush()  # persists without violating NOT NULL

    count = (
        await auth_schema.execute(
            text("SELECT count(*) FROM splits WHERE transaction_id = :id AND category_id IS NULL"),
            {"id": tx.id},
        )
    ).scalar_one()
    assert count == 1
