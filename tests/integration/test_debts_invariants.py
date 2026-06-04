"""Consolidation CASCADE de la projection RÉELLE (S09.5, P09.5.1).

Delta vs l'existant (recadré, review #146 M3) :
- la mécanique FK `ON DELETE CASCADE` est déjà couverte par S09.1
  (`test_debts_models.py`, lignes CONSTRUITES À LA MAIN, une projection à la fois) ;
- la symétrie persistée `create↔revoke` par S09.3
  (`test_share_request_service.py::test_revoke_..._keeps_share_request`).
SEUL delta ici : les DEUX projections (`Debt` + `ShareRequest`) MATÉRIALISÉES
ENSEMBLE par le flux réel `create_share_request` suivent leur tx d'origine en
UNE suppression — attrape un hypothétique bug où le service poserait la `Debt`
sur un `source_transaction_id` différent de la `ShareRequest`. (ADR 0002 : la
projection serveur suit sa tx d'origine.)
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.debts.service.share_request import create_share_request
from backend.modules.transactions.models import Transaction
from tests.integration._debts_helpers import (
    TxFactoryBundle,
    debt_count,
    seed,
    share_request_count,
)


async def test_real_flow_projections_both_follow_source_tx(
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
        short_label="Courses",
        by_user_id=s.alice_id,
    )
    # Sanity : le flux réel a posé les DEUX projections.
    assert await share_request_count(household_singleton, tx_id=s.tx_id) == 1
    assert await debt_count(household_singleton, tx_id=s.tx_id) == 1

    tx = (
        await household_singleton.execute(select(Transaction).where(Transaction.id == s.tx_id))
    ).scalar_one()
    await household_singleton.delete(tx)
    await household_singleton.flush()

    # Delta : les DEUX projections du flux réel suivent la tx en une suppression.
    assert await share_request_count(household_singleton, tx_id=s.tx_id) == 0
    assert await debt_count(household_singleton, tx_id=s.tx_id) == 0
