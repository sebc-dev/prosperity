"""Integration test for `transactions.service.queries._to_domain` (S08.5.1, #136).

`queries._to_domain` is a deliberate verbatim copy of `lifecycle._to_domain`
(D11: no `queries → lifecycle` coupling). The review of #136 flagged that the
copy carrying `leg_role` was untested — a regression on it would be silent. This
pins it with the same DISCRIMINATING divergent-row check used for lifecycle: a
row whose stored `leg_role` ('classification') diverges from what the domain
validator would re-derive from a NULL `category_id` ('funding'). If the mapper
dropped `leg_role=s.leg_role`, this would yield 'funding' and the test fails.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.modules.transactions.service.queries import get_transaction

TxFactoryBundle = Callable[[], Awaitable[tuple[type, type, type, type]]]


async def test_get_transaction_reads_divergent_leg_role_not_re_derived(
    household_singleton: AsyncSession,
    bound_transaction_factories: TxFactoryBundle,
) -> None:
    user_factory, account_factory, tx_factory, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[uuid.UUID, uuid.UUID]:
        owner = user_factory(email="q1@example.com")
        account = account_factory(owner_id=owner.id, name="Mine")
        tx = tx_factory(account_id=account.id, created_by=owner.id, state="draft")
        return account.id, tx.id

    account_id, tx_id = await household_singleton.run_sync(_seed)

    # Raw INSERT bypasses the ORM context default (which would derive 'funding').
    # The factory already attached a zero-sum pair; we target THIS split by id.
    divergent_id = uuid.uuid4()
    await household_singleton.execute(
        text(
            "INSERT INTO splits "
            "(id, transaction_id, account_id, amount_cents, currency, leg_role) "
            "VALUES (:id, :tx, :acc, 0, 'EUR', 'classification')"
        ),
        {"id": divergent_id, "tx": tx_id, "acc": account_id},
    )
    await household_singleton.flush()

    aggregate = await get_transaction(household_singleton, tx_id=tx_id)

    assert aggregate is not None
    # The factory pair is ±1000; our divergent leg is the only one at 0.
    divergent = next(s for s in aggregate.splits if s.amount.amount_cents == 0)
    assert divergent.category_id is None
    # `queries._to_domain` reads `s.leg_role` — keeps 'classification', does NOT
    # re-derive 'funding' from the NULL category.
    assert divergent.leg_role == "classification"
