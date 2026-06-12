"""Étape 8-9 du write upload handler — frontière transactionnelle PAR MUTATION (S13.6).

`process_batch` committe CHAQUE mutation indépendamment (ADR 0014, D-A) : l'échec de
la mutation N rollback N SEULE — 1..N-1 restent committées, N+1..K poursuivent — et
l'append `sync_request_log` (étape 9) vit DANS la transaction du write (D-B). Exercé
avec handlers + checks RÉELS sur vrai Postgres.

Deux tiers : le tier rollback-isolé (`household_singleton`, `db_session` en mode
`create_savepoint` → le `commit()` par-mutation est un release de SAVEPOINT, isolation
préservée) prouve la SÉQUENCE ; le tier commit-réel (`committed_engine` +
`_clean_committed_db`) prouve la DURABILITÉ « 1..N-1 persistent » depuis une session
DISTINCTE. Le code d'erreur des mutations qui lèvent est typé par `to_write_error`
(P13.6.3) ; la table de correspondance exhaustive est verrouillée séparément
(`test_sync_error_mapping`, `test_sync_dispatcher_errors`).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from backend.modules.accounts.models import Household
from backend.modules.auth.models import User
from backend.modules.sync.models import SyncRequestLog
from backend.modules.sync.public import BatchUpload, Mutation
from backend.modules.sync.service.dispatcher import process_batch
from backend.modules.sync.service.idempotency import record_processed
from backend.modules.transactions.models import Split, Transaction
from tests.factories.sqlalchemy import (
    AccountFactory,
    CategoryFactory,
    SplitFactory,
    TransactionFactory,
    UserFactory,
)
from tests.integration.sync._sync_helpers import mut as _mut
from tests.integration.sync._sync_helpers import run_one as _run

_TxFactories = Callable[[], Awaitable[tuple[type, type, type, type]]]


async def _draft_count(session: AsyncSession, account_id: uuid.UUID) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.account_id == account_id, Transaction.state == "draft")
        )
    ).scalar_one()


async def _log_count(session: AsyncSession, *, user_id: uuid.UUID) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(SyncRequestLog)
            .where(SyncRequestLog.user_id == user_id)
        )
    ).scalar_one()


def _insert(account_id: uuid.UUID) -> Mutation:
    return _mut("transactions", "insert", {"account_id": str(account_id)})


# ── frontière par mutation (séquence, tier rollback-isolé) ──────────────────────
async def test_failed_mutation_rolls_back_only_itself(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """Batch `[insert OK, splits/insert qui lève, insert OK]` : la mutation du milieu
    (un `add_split` sur une tx CONFIRMÉE → `ImmutableFieldViolation`) est capturée,
    mappée (`immutable_field_violation`) et rollback ; les deux inserts l'encadrant
    committent. `results == [ok, error, ok]`, le split refusé est ABSENT, deux drafts neufs."""
    user_f, account_f, tx_f, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID, uuid.UUID]:
        owner = user_f(email="boundary@ex.com")
        acc = account_f(owner_id=owner.id)
        confirmed = tx_f(account_id=acc.id, created_by=owner.id, state="confirmed")
        return owner, acc.id, confirmed.id

    owner, account_id, confirmed_id = await household_singleton.run_sync(_seed)
    splits_before = (
        await household_singleton.execute(
            select(func.count()).select_from(Split).where(Split.transaction_id == confirmed_id)
        )
    ).scalar_one()

    failing = _mut(
        "splits",
        "insert",
        {
            "transaction_id": str(confirmed_id),  # tx confirmée → add_split refusé (immutable)
            "account_id": str(account_id),
            "amount_cents": 100,
            "currency": "EUR",
        },
    )
    ok1, fail, ok2 = await process_batch(
        household_singleton,
        owner,
        BatchUpload(mutations=[_insert(account_id), failing, _insert(account_id)]),
    )

    assert ok1.success is True
    assert fail.success is False
    assert fail.error is not None and fail.error.code == "immutable_field_violation"
    assert ok2.success is True
    assert await _draft_count(household_singleton, account_id) == 2  # les 2 inserts committés
    splits_after = (
        await household_singleton.execute(
            select(func.count()).select_from(Split).where(Split.transaction_id == confirmed_id)
        )
    ).scalar_one()
    assert splits_after == splits_before  # la jambe refusée n'a laissé aucune trace


async def test_auth_denied_does_not_rollback_prior_success(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """Une mutation `auth_denied` (étape 1, AVANT le handler — ne touche pas la session)
    n'annule pas le commit de la mutation précédente ni n'empêche la suivante."""
    user_f, account_f, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID, uuid.UUID]:
        owner = user_f(email="ad-owner@ex.com")
        other = user_f(email="ad-other@ex.com")
        acc = account_f(owner_id=owner.id)
        foreign = account_f(owner_id=other.id)  # inaccessible à `owner`
        return owner, acc.id, foreign.id

    owner, account_id, foreign_id = await household_singleton.run_sync(_seed)
    ok1, denied, ok2 = await process_batch(
        household_singleton,
        owner,
        BatchUpload(mutations=[_insert(account_id), _insert(foreign_id), _insert(account_id)]),
    )

    assert ok1.success is True
    assert denied.success is False
    assert denied.error is not None and denied.error.code == "auth_denied"
    assert ok2.success is True
    assert await _draft_count(household_singleton, account_id) == 2


# ── append du journal (étape 9, DANS la transaction du write) ───────────────────
async def test_log_appended_in_same_transaction_as_write(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """Un write réussi appende `(user_id, client_request_id, table_name)` à
    `sync_request_log` — lu dans la MÊME session (release de SAVEPOINT)."""
    user_f, account_f, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="log@ex.com")
        return owner, account_f(owner_id=owner.id).id

    owner, account_id = await household_singleton.run_sync(_seed)
    mutation = _insert(account_id)
    result = await _run(household_singleton, owner, mutation)

    assert result.success is True
    row = (
        await household_singleton.execute(
            select(SyncRequestLog).where(
                SyncRequestLog.user_id == owner.id,
                SyncRequestLog.client_request_id == mutation.client_request_id,
            )
        )
    ).scalar_one()
    assert row.table_name == "transactions"
    assert row.processed_at is not None


async def test_n_successes_append_n_log_rows(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """N inserts distincts réussis ⇒ N lignes d'idempotence (une par write committé)."""
    user_f, account_f, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="nlog@ex.com")
        return owner, account_f(owner_id=owner.id).id

    owner, account_id = await household_singleton.run_sync(_seed)
    n = 3
    results = await process_batch(
        household_singleton,
        owner,
        BatchUpload(mutations=[_insert(account_id) for _ in range(n)]),
    )

    assert all(r.success for r in results)
    assert await _log_count(household_singleton, user_id=owner.id) == n


async def test_replay_within_same_batch_acked_without_rewrite(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """Le MÊME `client_request_id` deux fois dans un batch : le 1er write committe +
    appende le journal ; le 2e est détecté par `already_processed` (la ligne est visible
    après le commit-par-mutation) → ack SANS 2e écriture. Un seul draft, une seule ligne."""
    user_f, account_f, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="replay-batch@ex.com")
        return owner, account_f(owner_id=owner.id).id

    owner, account_id = await household_singleton.run_sync(_seed)
    crid = uuid.uuid4()
    dup = Mutation(
        client_request_id=crid,
        table="transactions",
        op="insert",
        payload={"account_id": str(account_id)},
    )
    first, second = await process_batch(
        household_singleton, owner, BatchUpload(mutations=[dup, dup])
    )

    assert first.success is True
    assert second.success is True
    assert await _draft_count(household_singleton, account_id) == 1  # une seule écriture
    assert await _log_count(household_singleton, user_id=owner.id) == 1


async def test_record_processed_inserts_row(
    household_singleton: AsyncSession,
    bound_account_factories: Callable[[], Awaitable[tuple[type, type, type]]],
) -> None:
    """`record_processed` (étape 9) ajoute une ligne aux bonnes colonnes (appel direct)."""
    user_factory, _, _ = await bound_account_factories()

    def _seed(_s: Session) -> User:
        return user_factory(email="rp@ex.com")

    owner = await household_singleton.run_sync(_seed)
    crid = uuid.uuid4()
    await record_processed(
        household_singleton, user_id=owner.id, client_request_id=crid, table_name="accounts"
    )

    row = (
        await household_singleton.execute(
            select(SyncRequestLog).where(SyncRequestLog.client_request_id == crid)
        )
    ).scalar_one()
    assert row.user_id == owner.id
    assert row.table_name == "accounts"
    assert row.processed_at is not None


# ── durabilité : 1..N-1 persistent réellement (tier commit-réel) ────────────────
def _seed_committed(s: Session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Seed (moteur commit-réel) un owner + un compte + une tx CONFIRMÉE (cible du
    `add_split` qui lèvera). Factories liées à `s` (agnostique du moteur)."""
    for factory in (UserFactory, AccountFactory, CategoryFactory, TransactionFactory, SplitFactory):
        factory._meta.sqlalchemy_session = s  # type: ignore[attr-defined]
    s.add(Household(name="Committed Household", base_currency="EUR"))  # singleton (ADR 0010)
    s.flush()
    owner = UserFactory(email="durable@example.com")
    account = AccountFactory(owner_id=owner.id, name="Perso")
    confirmed = TransactionFactory(account_id=account.id, created_by=owner.id, state="confirmed")
    return owner.id, account.id, confirmed.id


@pytest.mark.usefixtures("_clean_committed_db")
async def test_prior_successes_committed_when_later_fails(committed_engine: AsyncEngine) -> None:
    """Sur des commits RÉELS : un batch `[insert OK, splits/insert qui lève, insert OK]`
    laisse les deux drafts PERSISTÉS et lus depuis une session DISTINCTE (post-commit) —
    preuve « 1..N-1 restent committées » au sens ADR 0014, au-delà du release de SAVEPOINT."""
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)

    async with sm() as session:
        owner_id, account_id, confirmed_id = await session.run_sync(_seed_committed)
        await session.commit()

    async with sm() as session:
        owner = await session.get(User, owner_id)
        assert owner is not None
        failing = _mut(
            "splits",
            "insert",
            {
                "transaction_id": str(confirmed_id),
                "account_id": str(account_id),
                "amount_cents": 100,
                "currency": "EUR",
            },
        )
        ok1, fail, ok2 = await process_batch(
            session,
            owner,
            BatchUpload(mutations=[_insert(account_id), failing, _insert(account_id)]),
        )
        assert [ok1.success, fail.success, ok2.success] == [True, False, True]

    async with sm() as session:  # session DISTINCTE → snapshot post-commit
        drafts = (
            await session.execute(
                select(func.count())
                .select_from(Transaction)
                .where(Transaction.account_id == account_id, Transaction.state == "draft")
            )
        ).scalar_one()
        assert drafts == 2  # les deux inserts ont survécu, indépendamment de l'échec du milieu
        splits = (
            await session.execute(
                select(func.count()).select_from(Split).where(Split.transaction_id == confirmed_id)
            )
        ).scalar_one()
        assert splits == 2  # la jambe refusée n'a rien laissé (form-B factory = 2 jambes)
