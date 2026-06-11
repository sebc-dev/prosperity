"""Intégration — matérialisation synchrone du share_request via le CHEMIN SYNC (S13.5).

Verrou de régression (ADR 0002, read-after-write fort) : `share_requests/insert` passé
par le write upload handler matérialise le `Debt` (`origin='personal_share_request'`)
SYNCHRONIQUEMENT dans `create_share_request` (in-function, PAS via le mini-bus).

Le read-after-write SAME-SESSION (et l'asymétrie insert(`debt_count==1`)/delete(`==0`),
contrôle anti-always-green) est DÉJÀ couvert par `test_handlers_debts.py` (S13.4). Cette
suite ajoute le SEUL verrou non redondant : la projection PERSISTE POST-COMMIT (AC #3),
prouvé sur le moteur à commits réels depuis une transaction DISTINCTE — symétrique de
`test_materialization_overflow.py::test_confirm_via_sync_persists_after_commit`.

Le câblage du mini-bus est sans objet ici (matérialisation in-function) ; le tier
commit-réel (`committed_engine` + `_clean_committed_db`) reste isolé des tests rollback.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.orm import Session

from backend.modules.accounts.models import Household
from backend.modules.auth.models import User
from tests.factories.sqlalchemy import (
    AccountFactory,
    CategoryFactory,
    SplitFactory,
    TransactionFactory,
    UserFactory,
)
from tests.integration._debts_helpers import debt_count
from tests.integration.sync._sync_helpers import mut as _mut
from tests.integration.sync._sync_helpers import run_one as _run


def _seed_personal_expense(s: Session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Seed (moteur commit-réel) Alice (créancière) + Bob (débiteur) + une tx perso
    CONFIRMÉE à 2 jambes (funding NULL / classification). Retourne `(alice, bob, tx)`.
    Factories liées à `s` (pas via `bound_*`) pour rester agnostique du moteur."""
    for factory in (UserFactory, AccountFactory, CategoryFactory, TransactionFactory, SplitFactory):
        factory._meta.sqlalchemy_session = s  # type: ignore[attr-defined]
    s.add(Household(name="Committed Household", base_currency="EUR"))  # singleton (ADR 0010)
    s.flush()

    alice = UserFactory(email="alice-sr@example.com")
    bob = UserFactory(email="bob-sr@example.com")
    account = AccountFactory(owner_id=alice.id, name="Alice perso")
    tx = TransactionFactory(
        account_id=account.id, created_by=alice.id, state="confirmed", splits=False
    )
    SplitFactory(transaction_id=tx.id, account_id=account.id, amount_cents=-1000, currency="EUR")
    SplitFactory(  # classification leg → consumes a category, makes the expense shareable
        transaction_id=tx.id,
        account_id=account.id,
        amount_cents=1000,
        currency="EUR",
        category_id=CategoryFactory().id,
    )
    return alice.id, bob.id, tx.id


@pytest.mark.usefixtures("_clean_committed_db")
async def test_share_request_persists_after_commit(committed_engine: AsyncEngine) -> None:
    """AC #3 « persiste post-commit » à la lettre : un `share_requests/insert` via
    `process_batch` + `commit()` rend le `Debt` (`origin='personal_share_request'`)
    visible depuis une transaction DISTINCTE (nouvelle session) — au-delà du flush
    in-transaction déjà couvert par S13.4."""
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)

    async with sm() as session:
        alice_id, bob_id, tx_id = await session.run_sync(_seed_personal_expense)
        await session.commit()

    async with sm() as session:
        alice = await session.get(User, alice_id)
        assert alice is not None
        result = await _run(
            session,
            alice,
            _mut(
                "share_requests",
                "insert",
                {
                    "transaction_id": str(tx_id),
                    "requested_from": str(bob_id),
                    "ratio": "0.5",
                    "short_label": "diner",
                },
            ),
        )
        assert result.success is True
        await session.commit()

    async with sm() as session:  # fresh transaction, post-commit snapshot
        assert await debt_count(session, tx_id=tx_id, origin="personal_share_request") == 1
