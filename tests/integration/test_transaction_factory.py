"""Integration tests for `TransactionFactory` / `SplitFactory` (S07.2, P07.2.4).

Livrable observable: `TransactionFactory()` instantiates a balanced
(zero-sum) transaction by default, with an override path for unbalanced
negative cases. All factory calls run inside a `run_sync(_build)` so they use
the single sync session bound by `bound_transaction_factories` — otherwise
objects attach to a divergent session and the flush breaks (gabarit
`test_account_member_factory_builds_shared_account`).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.usefixtures("household_singleton")


async def _seed_account(
    session: AsyncSession,
    bound: Callable[[], Awaitable[tuple[type, type, type, type]]],
) -> tuple[uuid.UUID, uuid.UUID, tuple[type, type, type, type]]:
    """Build a user + personal account.

    Returns `(account_id, user_id, factories)` — binding the four factories
    once and handing the tuple back, so callers reuse it instead of awaiting
    `bound()` a second time (the bind is idempotent but the extra call is noise).
    """
    factories = await bound()
    user_factory, account_factory, _tx_factory, _split_factory = factories

    def _build(_sync_session: object) -> tuple[uuid.UUID, uuid.UUID]:
        user = user_factory()
        account = account_factory(owner_id=user.id)
        return account.id, user.id

    account_id, user_id = await session.run_sync(_build)
    return account_id, user_id, factories


async def test_default_transaction_is_zero_sum(
    auth_schema: AsyncSession,
    bound_transaction_factories: Callable[[], Awaitable[tuple[type, type, type, type]]],
) -> None:
    account_id, user_id, factories = await _seed_account(auth_schema, bound_transaction_factories)
    _u, _a, transaction_factory, _s = factories

    def _build(_sync_session: object) -> uuid.UUID:
        tx = transaction_factory(account_id=account_id, created_by=user_id)
        return tx.id

    tx_id = await auth_schema.run_sync(_build)

    total, count, currencies = (
        await auth_schema.execute(
            text(
                "SELECT coalesce(sum(amount_cents), 0), count(*), count(distinct currency) "
                "FROM splits WHERE transaction_id = :id"
            ),
            {"id": tx_id},
        )
    ).one()
    assert total == 0
    assert count == 2
    assert currencies == 1


async def test_amount_override_stays_balanced(
    auth_schema: AsyncSession,
    bound_transaction_factories: Callable[[], Awaitable[tuple[type, type, type, type]]],
) -> None:
    account_id, user_id, factories = await _seed_account(auth_schema, bound_transaction_factories)
    _u, _a, transaction_factory, _s = factories

    def _build(_sync_session: object) -> uuid.UUID:
        tx = transaction_factory(
            account_id=account_id, created_by=user_id, splits__amount_cents=5000
        )
        return tx.id

    tx_id = await auth_schema.run_sync(_build)

    rows = (
        (
            await auth_schema.execute(
                text(
                    "SELECT amount_cents FROM splits "
                    "WHERE transaction_id = :id ORDER BY amount_cents"
                ),
                {"id": tx_id},
            )
        )
        .scalars()
        .all()
    )
    assert list(rows) == [-5000, 5000]


async def test_splits_false_yields_no_splits(
    auth_schema: AsyncSession,
    bound_transaction_factories: Callable[[], Awaitable[tuple[type, type, type, type]]],
) -> None:
    account_id, user_id, factories = await _seed_account(auth_schema, bound_transaction_factories)
    _u, _a, transaction_factory, _s = factories

    def _build(_sync_session: object) -> uuid.UUID:
        tx = transaction_factory(account_id=account_id, created_by=user_id, splits=False)
        return tx.id

    tx_id = await auth_schema.run_sync(_build)

    count = (
        await auth_schema.execute(
            text("SELECT count(*) FROM splits WHERE transaction_id = :id"), {"id": tx_id}
        )
    ).scalar_one()
    assert count == 0


async def test_explicit_unbalanced_splits_for_negative_case(
    auth_schema: AsyncSession,
    bound_transaction_factories: Callable[[], Awaitable[tuple[type, type, type, type]]],
) -> None:
    # Documents generating an UNbalanced transaction for S07.3 negative tests:
    # opt out of the auto pair, then add two mismatched legs.
    account_id, user_id, factories = await _seed_account(auth_schema, bound_transaction_factories)
    _u, _a, transaction_factory, split_factory = factories

    def _build(_sync_session: object) -> uuid.UUID:
        tx = transaction_factory(account_id=account_id, created_by=user_id, splits=False)
        split_factory(transaction_id=tx.id, account_id=account_id, amount_cents=-1000)
        split_factory(transaction_id=tx.id, account_id=account_id, amount_cents=700)
        return tx.id

    tx_id = await auth_schema.run_sync(_build)

    total = (
        await auth_schema.execute(
            text("SELECT sum(amount_cents) FROM splits WHERE transaction_id = :id"), {"id": tx_id}
        )
    ).scalar_one()
    assert total == -300  # deliberately != 0


async def test_factory_defaults(
    auth_schema: AsyncSession,
    bound_transaction_factories: Callable[[], Awaitable[tuple[type, type, type, type]]],
) -> None:
    account_id, user_id, factories = await _seed_account(auth_schema, bound_transaction_factories)
    _u, _a, transaction_factory, _s = factories

    def _build(_sync_session: object) -> tuple[str, list[str], str, object]:
        tx = transaction_factory(account_id=account_id, created_by=user_id)
        return tx.state, tx.tags, tx.debt_generation_override, tx.category_id

    state, tags, override, category_id = await auth_schema.run_sync(_build)
    assert state == "draft"
    assert tags == []
    assert override == "default"
    assert category_id is None


async def test_currency_override_propagates_to_both_legs(
    auth_schema: AsyncSession,
    bound_transaction_factories: Callable[[], Awaitable[tuple[type, type, type, type]]],
) -> None:
    # `splits__currency` must reach BOTH legs (the only post-generation param
    # not otherwise exercised): a single-currency zero-sum pair in CHF.
    account_id, user_id, factories = await _seed_account(auth_schema, bound_transaction_factories)
    _u, _a, transaction_factory, _s = factories

    def _build(_sync_session: object) -> uuid.UUID:
        tx = transaction_factory(
            account_id=account_id,
            created_by=user_id,
            splits__amount_cents=2500,
            splits__currency="CHF",
        )
        return tx.id

    tx_id = await auth_schema.run_sync(_build)

    rows = (
        (
            await auth_schema.execute(
                text("SELECT currency FROM splits WHERE transaction_id = :id"),
                {"id": tx_id},
            )
        )
        .scalars()
        .all()
    )
    assert list(rows) == ["CHF", "CHF"]
