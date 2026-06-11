"""Oracles de lecture de l'overflow F10 partagés entre tiers de tests.

`OVERFLOW_ORIGIN` + `overflow_debts`/`overflow_by_debtor` étaient dupliqués entre la
suite matérialiseur E11 (`test_overflow_materializer.py`) et la suite sync S13.5
(`sync/test_materialization_overflow.py`). Factorisés ici (review S13.5, parité avec
`_debts_helpers.py`) : un seul corps à maintenir. Module NON collecté (pas de préfixe
`test_`), hors `root_package` import-linter.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.debts.models import Debt

OVERFLOW_ORIGIN = "shared_account_overflow"


async def overflow_debts(session: AsyncSession, tx_id: uuid.UUID) -> list[Debt]:
    """The materialised overflow `Debt` rows for a transaction (ordered by debtor)."""
    rows = await session.execute(
        select(Debt)
        .where(Debt.source_transaction_id == tx_id, Debt.origin == OVERFLOW_ORIGIN)
        .order_by(Debt.from_user_id)
    )
    return list(rows.scalars().all())


async def overflow_by_debtor(session: AsyncSession, tx_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """`{from_user_id: amount_cents}` of the overflow debts for a transaction."""
    return {d.from_user_id: d.amount_cents for d in await overflow_debts(session, tx_id)}
