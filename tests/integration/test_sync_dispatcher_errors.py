"""Erreurs typées via un CHEMIN MÉTIER réel (S13.6 / P13.6.3).

Complète le verrou unitaire `test_sync_error_mapping` (table exhaustive, DB-free) en
prouvant que, sur un VRAI passage par `process_batch` + Postgres, une exception domaine
remonte bien au code wire attendu — et que les deux comportements critiques du
dispatcher tiennent : une exception INCONNUE PROPAGE (→ 500, jamais un faux `success`,
D-H) sans annuler les mutations déjà committées, et une erreur typée n'interrompt pas
la suite du batch (`continue` N+1).

Les autres catégories (`validation_error`, `not_found`, `immutable_field_violation`)
sont déjà couvertes end-to-end par les suites de handlers / la frontière par-mutation ;
on ne les re-teste pas ici (non-redondance).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.modules.auth.models import User
from backend.modules.sync.models import SyncRequestLog
from backend.modules.sync.public import BatchUpload, Mutation, WriteResult
from backend.modules.sync.schemas import MutationOp
from backend.modules.sync.service.dispatcher import (
    HANDLERS,
    PERMISSION_CHECKS,
    Handler,
    PermissionCheck,
    process_batch,
)
from backend.modules.transactions.models import Transaction
from tests.integration.sync._sync_helpers import mut as _mut
from tests.integration.sync._sync_helpers import run_one as _run

_TxFactories = Callable[[], Awaitable[tuple[type, type, type, type]]]


def _insert(account_id: uuid.UUID) -> Mutation:
    return _mut("transactions", "insert", {"account_id": str(account_id)})


async def test_invalid_transition_maps_to_invalid_state_transition(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """Une transition refusée par le state-machine (`void → confirmed`, terminal) →
    `InvalidStateTransitionError` → code `invalid_state_transition` (assert_transition
    précède le zero-sum, donc l'erreur est bien la transition, pas un déséquilibre)."""
    user_f, account_f, tx_f, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="invtrans@ex.com")
        acc = account_f(owner_id=owner.id)
        return owner, tx_f(account_id=acc.id, created_by=owner.id, state="void").id

    owner, tx_id = await household_singleton.run_sync(_seed)
    result = await _run(
        household_singleton,
        owner,
        _mut("transactions", "update", {"id": str(tx_id), "state": "confirmed"}),
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "invalid_state_transition"


async def test_failed_then_success_continues_with_typed_error(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """Batch `[insert OK, planned déséquilibré, insert OK]` → `[success,
    error(unbalanced_transaction), success]` : l'erreur typée n'interrompt pas le batch
    (continue N+1), et les deux inserts committent."""
    user_f, account_f, tx_f, split_f = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID, uuid.UUID]:
        owner = user_f(email="fts@ex.com")
        acc = account_f(owner_id=owner.id)
        tx = tx_f(account_id=acc.id, created_by=owner.id, splits=False)
        split_f(transaction_id=tx.id, account_id=acc.id, amount_cents=500)  # 1 jambe → déséquilibré
        return owner, acc.id, tx.id

    owner, account_id, unbalanced_id = await household_singleton.run_sync(_seed)
    plan = _mut("transactions", "update", {"id": str(unbalanced_id), "state": "planned"})
    ok1, fail, ok2 = await process_batch(
        household_singleton,
        owner,
        BatchUpload(mutations=[_insert(account_id), plan, _insert(account_id)]),
    )

    assert ok1.success is True
    assert fail.success is False
    assert fail.error is not None and fail.error.code == "unbalanced_transaction"
    assert ok2.success is True
    drafts = (
        await household_singleton.execute(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.account_id == account_id, Transaction.state == "draft")
        )
    ).scalar_one()
    # 1 (le seed déséquilibré : sa transition a rollback → reste `draft`) + 2 inserts committés.
    assert drafts == 3
    still_draft = (
        await household_singleton.execute(
            select(Transaction.state).where(Transaction.id == unbalanced_id)
        )
    ).scalar_one()
    assert still_draft == "draft"  # la mutation N a bien rollback (transition annulée)


async def _allow(session: AsyncSession, user: User, mutation: Mutation) -> bool:
    return True


async def _boom(session: AsyncSession, user: User, mutation: Mutation) -> WriteResult:
    raise RuntimeError("infra down")  # exception NON mappée (hors domaine)


async def test_unknown_exception_propagates_500_and_keeps_prior_commits(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """Une exception INCONNUE (`RuntimeError`) → `to_write_error` renvoie `None` → le
    dispatcher RE-RAISE (→ 500, retry PowerSync, D-H), JAMAIS un faux `success`. La
    mutation précédente, déjà committée, survit (skip au retry par idempotence)."""
    user_f, account_f, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="boom@ex.com")
        return owner, account_f(owner_id=owner.id).id

    owner, account_id = await household_singleton.run_sync(_seed)
    # m1 passe par le chemin RÉEL (commit) ; m2 est routée vers un handler qui lève.
    handlers: dict[str, Handler] = dict(HANDLERS)
    handlers["kaboom"] = _boom
    checks: dict[tuple[str, MutationOp], PermissionCheck] = dict(PERMISSION_CHECKS)
    checks["kaboom", "insert"] = _allow
    batch = BatchUpload(mutations=[_insert(account_id), _mut("kaboom", "insert", {})])

    with pytest.raises(RuntimeError):
        await process_batch(
            household_singleton, owner, batch, handlers=handlers, permission_checks=checks
        )

    drafts = (
        await household_singleton.execute(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.account_id == account_id, Transaction.state == "draft")
        )
    ).scalar_one()
    assert drafts == 1  # le write committé AVANT le 500 a survécu (1..N-1 committées)


async def test_invalid_payload_propagates_500_and_keeps_prior_commits(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """CHEMIN RÉEL d'une `pydantic.ValidationError` (payload étape 3 mal formé) : un
    `categories/insert {}` passe l'auth (membre actif) mais échoue à `model_validate`
    dans le handler. `to_write_error` renvoie `None` (hors domaine) → le dispatcher
    RE-RAISE → 500 (D-I), JAMAIS un faux `success` ni un code typé. L'insert précédent,
    déjà committé, survit."""
    user_f, account_f, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="badpayload@ex.com")
        return owner, account_f(owner_id=owner.id).id

    owner, account_id = await household_singleton.run_sync(_seed)
    # m1 = insert valide (commit) ; m2 = categories/insert SANS `name` → ValidationError handler.
    batch = BatchUpload(mutations=[_insert(account_id), _mut("categories", "insert", {})])

    with pytest.raises(ValidationError):
        await process_batch(household_singleton, owner, batch)

    drafts = (
        await household_singleton.execute(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.account_id == account_id, Transaction.state == "draft")
        )
    ).scalar_one()
    assert drafts == 1  # le write committé AVANT le 500 a survécu


async def _dup_pk(session: AsyncSession, user: User, mutation: Mutation) -> WriteResult:
    """Handler qui force une violation d'intégrité DB au `flush` (deux lignes au MÊME
    PK composite `sync_request_log`) → `IntegrityError` (erreur INFRA, hors domaine)."""
    for table in ("a", "b"):
        session.add(
            SyncRequestLog(
                user_id=user.id, client_request_id=mutation.client_request_id, table_name=table
            )
        )
    await session.flush()  # PK (user_id, client_request_id) en double → IntegrityError
    raise AssertionError  # pragma: no cover — le flush ci-dessus lève toujours


async def test_db_integrity_error_propagates_500_and_keeps_prior_commits(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """Un échec AU FLUSH DB (`IntegrityError`, pas une exception domaine pré-flush) est
    aussi une erreur INCONNUE → `to_write_error` `None` → re-raise → 500. Prouve que la
    frontière par-mutation rollback proprement une transaction Postgres ABORTÉE (l'accès
    suivant exigerait un nouveau cycle) et que 1..N-1 survivent."""
    user_f, account_f, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="integrity@ex.com")
        return owner, account_f(owner_id=owner.id).id

    owner, account_id = await household_singleton.run_sync(_seed)
    handlers: dict[str, Handler] = dict(HANDLERS)
    handlers["kaboom"] = _dup_pk
    checks: dict[tuple[str, MutationOp], PermissionCheck] = dict(PERMISSION_CHECKS)
    checks["kaboom", "insert"] = _allow
    batch = BatchUpload(mutations=[_insert(account_id), _mut("kaboom", "insert", {})])

    with pytest.raises(IntegrityError):
        await process_batch(
            household_singleton, owner, batch, handlers=handlers, permission_checks=checks
        )

    drafts = (
        await household_singleton.execute(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.account_id == account_id, Transaction.state == "draft")
        )
    ).scalar_one()
    assert drafts == 1  # le write committé AVANT l'abort a survécu (rollback ciblé)
