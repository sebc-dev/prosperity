"""Helpers d'intégration partagés du module `debts` (S09.3 + S09.5).

Extraits de `test_share_request_service.py` (review S09.5 m3) pour que
`test_debts_invariants.py` les consomme sans importer un symbole privé d'un
module de test (couplage test→test + `reportPrivateUsage`). Module NON collecté
(pas de préfixe `test_`, précédent `tests/e2e/_helpers.py`), hors `root_package`
import-linter. Aucun comportement modifié : mêmes corps, noms rendus publics
(`seed` ex-`_seed`, `Scenario` ex-`_Scenario`, `debt_count` ex-`_debt_count`),
plus `share_request_count` (nouveau, typé) pour le consommateur S09.5.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.modules.accounts.models import AccountMember
from backend.modules.debts.models import Debt, ShareRequest
from tests.factories.sqlalchemy import CategoryFactory

TxFactoryBundle = Callable[[], Awaitable[tuple[type, type, type, type]]]

# (amount_cents, is_classification) — a classification leg carries a category,
# a funding leg does not (leg_role derived by the ORM default). Legs must sum to
# zero for a `confirmed` tx (the domain re-checks zero-sum on read).
Leg = tuple[int, bool]


@dataclass
class Scenario:
    alice_id: uuid.UUID  # owner of the personal account = creditor
    bob_id: uuid.UUID  # active foyer member = debtor
    account_id: uuid.UUID
    tx_id: uuid.UUID


async def seed(  # noqa: PLR0913 — keyword-only scenario knobs
    session: AsyncSession,
    factories: TxFactoryBundle,
    *,
    legs: list[Leg],
    state: str = "confirmed",
    personal: bool = True,
    tx_owner_is_alice: bool = True,
    bob_disabled: bool = False,
) -> Scenario:
    """Seed Alice (owner/creditor), Bob (debtor) + a tx with the given legs.

    `personal=False` builds a *shared* account (owner NULL) with Alice as member
    (accessible but not owned-personal → vérif ii). `tx_owner_is_alice=False`
    puts the tx on a third user's personal account (inaccessible to Alice →
    vérif i). `bob_disabled=True` disables Bob (F02 → vérif iv).
    """
    user_factory, account_factory, tx_factory, split_factory = await factories()

    def _do(sync_session: Session) -> Scenario:
        alice = user_factory(email="alice@example.com")
        bob_kwargs: dict[str, object] = {"email": "bob@example.com"}
        if bob_disabled:
            bob_kwargs["disabled_at"] = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
        bob = user_factory(**bob_kwargs)

        if not tx_owner_is_alice:
            carol = user_factory(email="carol@example.com")
            account = account_factory(owner_id=carol.id, name="Carol perso")
            tx_creator = carol.id
        elif personal:
            account = account_factory(owner_id=alice.id, name="Alice perso")
            tx_creator = alice.id
        else:  # shared account: owner NULL + Alice as member
            account = account_factory(owner_id=None, name="Commun")
            sync_session.add(
                AccountMember(
                    account_id=account.id,
                    user_id=alice.id,
                    default_share_ratio=Decimal("1.0"),
                )
            )
            sync_session.flush()
            tx_creator = alice.id

        tx = tx_factory(account_id=account.id, created_by=tx_creator, state=state, splits=False)
        for amount, is_classification in legs:
            category_id = CategoryFactory().id if is_classification else None
            split_factory(
                transaction_id=tx.id,
                account_id=account.id,
                amount_cents=amount,
                currency="EUR",
                category_id=category_id,
            )
        return Scenario(alice.id, bob.id, account.id, tx.id)

    return await session.run_sync(_do)


async def debt_count(session: AsyncSession, *, tx_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Debt).where(Debt.source_transaction_id == tx_id)
    return int((await session.execute(stmt)).scalar_one())


async def share_request_count(session: AsyncSession, *, tx_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(ShareRequest)
        .where(ShareRequest.source_transaction_id == tx_id)
    )
    return int((await session.execute(stmt)).scalar_one())
