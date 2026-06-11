"""Intégration — sous-handlers `transactions` + `splits` (S13.4 / P13.4.1).

`process_batch` (handlers + checks RÉELS, vrai Postgres, rollback-isolé) route
chaque `(op, payload)` vers `transactions.public` puis flush. Oracle = état DB lu
dans la même session (les cas « lève » via `pytest.raises` autour de `process_batch`,
D-I : pas de try/except dans le dispatcher en S13.4).

Les entités RÉFÉRENCÉES (tx, split) sont SEED via factories pour disposer d'un id
connu : la réconciliation des ids générés serveur (`server_values`) appartient à
S13.6, donc un batch « create draft → add split sur cet id » end-to-end n'est pas
encore tissable. Ici on prouve le ROUTAGE de chaque op.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.modules.auth.models import User
from backend.modules.sync.models import SyncRequestLog
from backend.modules.sync.public import BatchUpload, Mutation, WriteResult
from backend.modules.sync.service.dispatcher import process_batch
from backend.modules.transactions.domain import TransactionError, TransactionState
from backend.modules.transactions.models import Split, Transaction

_TxFactories = Callable[[], Awaitable[tuple[type, type, type, type]]]


def _mut(table: str, op: str, payload: Mapping[str, object]) -> Mutation:
    return Mutation(
        client_request_id=uuid.uuid4(),
        table=table,
        op=op,  # type: ignore[arg-type]
        payload=dict(payload),
    )


async def _run(session: AsyncSession, user: User, mutation: Mutation) -> WriteResult:
    [result] = await process_batch(session, user, BatchUpload(mutations=[mutation]))
    return result


# ── insert → create_draft ─────────────────────────────────────────────────────
async def test_insert_creates_draft(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    user_f, account_f, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="owner@ex.com")
        acc = account_f(owner_id=owner.id, name="Perso")
        return owner, acc.id

    owner, account_id = await household_singleton.run_sync(_seed)
    result = await _run(
        household_singleton, owner, _mut("transactions", "insert", {"account_id": str(account_id)})
    )

    assert result.success is True
    row = (
        await household_singleton.execute(
            select(Transaction).where(Transaction.account_id == account_id)
        )
    ).scalar_one()
    assert row.state == TransactionState.DRAFT.value
    assert row.created_by == owner.id


async def test_insert_rejects_server_derived_field(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """Un `created_by` au payload → `ValidationError` (D-L, `extra="forbid"`) AVANT tout write."""
    user_f, account_f, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="o2@ex.com")
        return owner, account_f(owner_id=owner.id).id

    owner, account_id = await household_singleton.run_sync(_seed)
    payload = {"account_id": str(account_id), "created_by": str(uuid.uuid4())}
    with pytest.raises(ValidationError):
        await _run(household_singleton, owner, _mut("transactions", "insert", payload))


# ── splits/insert + splits/delete ──────────────────────────────────────────────
async def test_split_insert_adds_leg(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    user_f, account_f, tx_f, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID, uuid.UUID]:
        owner = user_f(email="o3@ex.com")
        acc = account_f(owner_id=owner.id)
        tx = tx_f(account_id=acc.id, created_by=owner.id, splits=False)
        return owner, acc.id, tx.id

    owner, account_id, tx_id = await household_singleton.run_sync(_seed)
    payload = {
        "transaction_id": str(tx_id),
        "account_id": str(account_id),
        "amount_cents": 1500,
        "currency": "EUR",
    }
    result = await _run(household_singleton, owner, _mut("splits", "insert", payload))

    assert result.success is True
    count = (
        await household_singleton.execute(
            select(func.count()).select_from(Split).where(Split.transaction_id == tx_id)
        )
    ).scalar_one()
    assert count == 1


async def test_split_delete_removes_leg(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    user_f, account_f, tx_f, split_f = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID, uuid.UUID, uuid.UUID]:
        owner = user_f(email="o4@ex.com")
        acc = account_f(owner_id=owner.id)
        tx = tx_f(account_id=acc.id, created_by=owner.id, splits=False)
        split = split_f(transaction_id=tx.id, account_id=acc.id)
        return owner, acc.id, tx.id, split.id

    owner, _account_id, tx_id, split_id = await household_singleton.run_sync(_seed)
    payload = {"transaction_id": str(tx_id), "id": str(split_id)}
    result = await _run(household_singleton, owner, _mut("splits", "delete", payload))

    assert result.success is True
    count = (
        await household_singleton.execute(
            select(func.count()).select_from(Split).where(Split.transaction_id == tx_id)
        )
    ).scalar_one()
    assert count == 0


async def test_split_insert_missing_transaction_id_denied(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """Payload sans `transaction_id` → étape 1 fail-closed `auth_denied`, SANS exception."""
    user_f, account_f, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="o5@ex.com")
        return owner, account_f(owner_id=owner.id).id

    owner, account_id = await household_singleton.run_sync(_seed)
    payload = {"account_id": str(account_id), "amount_cents": 100, "currency": "EUR"}
    result = await _run(household_singleton, owner, _mut("splits", "insert", payload))

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "auth_denied"


async def test_split_insert_unknown_transaction_denied(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """`splits/insert` dont le `transaction_id` (bien formé) ne désigne aucune tx →
    `_check_mutate_split` fail-closed `auth_denied` (la tx parente n'existe pas)."""
    user_f, account_f, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="o15@ex.com")
        return owner, account_f(owner_id=owner.id).id

    owner, account_id = await household_singleton.run_sync(_seed)
    payload = {
        "transaction_id": str(uuid.uuid4()),  # aucune tx
        "account_id": str(account_id),
        "amount_cents": 100,
        "currency": "EUR",
    }
    result = await _run(household_singleton, owner, _mut("splits", "insert", payload))

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "auth_denied"


async def test_splits_update_unsupported_denied(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """`splits/update` n'a pas d'entrée `PERMISSION_CHECKS` (D-G) → `auth_denied`,
    le handler n'est jamais atteint (pas de branche morte)."""
    user_f, account_f, tx_f, split_f = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID, uuid.UUID]:
        owner = user_f(email="o6@ex.com")
        acc = account_f(owner_id=owner.id)
        tx = tx_f(account_id=acc.id, created_by=owner.id, splits=False)
        split = split_f(transaction_id=tx.id, account_id=acc.id)
        return owner, tx.id, split.id

    owner, tx_id, split_id = await household_singleton.run_sync(_seed)
    payload = {"transaction_id": str(tx_id), "id": str(split_id), "amount_cents": 9}
    result = await _run(household_singleton, owner, _mut("splits", "update", payload))

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "auth_denied"


# ── update → transition (state seul, D-K) / édition de champs ───────────────────
async def test_update_state_planned_then_confirmed(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    user_f, account_f, tx_f, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="o7@ex.com")
        acc = account_f(owner_id=owner.id)
        tx = tx_f(account_id=acc.id, created_by=owner.id)  # form B équilibrée, draft
        return owner, tx.id

    owner, tx_id = await household_singleton.run_sync(_seed)

    await _run(
        household_singleton,
        owner,
        _mut("transactions", "update", {"id": str(tx_id), "state": "planned"}),
    )
    planned = (
        await household_singleton.execute(select(Transaction).where(Transaction.id == tx_id))
    ).scalar_one()
    assert planned.state == TransactionState.PLANNED.value

    await _run(
        household_singleton,
        owner,
        _mut("transactions", "update", {"id": str(tx_id), "state": "confirmed"}),
    )
    await household_singleton.refresh(planned)
    assert planned.state == TransactionState.CONFIRMED.value


async def test_update_editable_fields_routes_update(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """`update` sans `state` → `update_editable_fields` (oracle DB)."""
    user_f, account_f, tx_f, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="o8@ex.com")
        acc = account_f(owner_id=owner.id)
        tx = tx_f(account_id=acc.id, created_by=owner.id, splits=False)
        return owner, tx.id

    owner, tx_id = await household_singleton.run_sync(_seed)
    await _run(
        household_singleton,
        owner,
        _mut("transactions", "update", {"id": str(tx_id), "description": "courses"}),
    )
    row = (
        await household_singleton.execute(select(Transaction).where(Transaction.id == tx_id))
    ).scalar_one()
    assert row.description == "courses"


async def test_update_rejects_state_and_field_together(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """`{state, description}` ensemble → `ValidationError` (D-K) — pas de perte silencieuse."""
    user_f, account_f, tx_f, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="o9@ex.com")
        acc = account_f(owner_id=owner.id)
        return owner, tx_f(account_id=acc.id, created_by=owner.id, splits=False).id

    owner, tx_id = await household_singleton.run_sync(_seed)
    payload = {"id": str(tx_id), "state": "confirmed", "description": "x"}
    with pytest.raises(ValidationError):
        await _run(household_singleton, owner, _mut("transactions", "update", payload))


async def test_confirm_unbalanced_raises(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """Une transition refusée par le domaine PROPAGE (D-I) — oracle = `pytest.raises`."""
    user_f, account_f, tx_f, split_f = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="o10@ex.com")
        acc = account_f(owner_id=owner.id)
        tx = tx_f(account_id=acc.id, created_by=owner.id, splits=False)
        split_f(transaction_id=tx.id, account_id=acc.id, amount_cents=500)  # 1 jambe → déséquilibré
        return owner, tx.id

    owner, tx_id = await household_singleton.run_sync(_seed)
    with pytest.raises(TransactionError):
        await _run(
            household_singleton,
            owner,
            _mut("transactions", "update", {"id": str(tx_id), "state": "confirmed"}),
        )


async def test_update_state_void_routes_transition(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """`update {state:"void"}` → `_route_transition` branche `void` (distincte du
    chemin `delete`, qui appelle `void` directement)."""
    user_f, account_f, tx_f, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="o14@ex.com")
        acc = account_f(owner_id=owner.id)
        return owner, tx_f(account_id=acc.id, created_by=owner.id).id

    owner, tx_id = await household_singleton.run_sync(_seed)
    result = await _run(
        household_singleton,
        owner,
        _mut("transactions", "update", {"id": str(tx_id), "state": "void"}),
    )

    assert result.success is True
    row = (
        await household_singleton.execute(select(Transaction).where(Transaction.id == tx_id))
    ).scalar_one()
    assert row.state == TransactionState.VOID.value


# ── delete → void ──────────────────────────────────────────────────────────────
async def test_delete_routes_void(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    user_f, account_f, tx_f, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="o11@ex.com")
        acc = account_f(owner_id=owner.id)
        return owner, tx_f(account_id=acc.id, created_by=owner.id).id

    owner, tx_id = await household_singleton.run_sync(_seed)
    result = await _run(
        household_singleton, owner, _mut("transactions", "delete", {"id": str(tx_id)})
    )

    assert result.success is True
    row = (
        await household_singleton.execute(select(Transaction).where(Transaction.id == tx_id))
    ).scalar_one()
    assert row.state == TransactionState.VOID.value


# ── étape 1 : isolation + fail-closed ──────────────────────────────────────────
async def test_step1_denies_inaccessible_account(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    user_f, account_f, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        intruder = user_f(email="intruder@ex.com")
        other = user_f(email="other@ex.com")
        foreign = account_f(owner_id=other.id, name="Autrui")
        return intruder, foreign.id

    intruder, foreign_id = await household_singleton.run_sync(_seed)
    result = await _run(
        household_singleton,
        intruder,
        _mut("transactions", "insert", {"account_id": str(foreign_id)}),
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "auth_denied"


async def test_update_malformed_id_denied_without_exception(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """`transactions/update` sans `id` exploitable → `_check_mutate_transaction`
    fail-closed `auth_denied`, JAMAIS de `KeyError`/`ValueError` qui remonte."""
    user_f, _, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> User:
        return user_f(email="o12@ex.com")

    owner = await household_singleton.run_sync(_seed)
    result = await _run(
        household_singleton, owner, _mut("transactions", "update", {"state": "planned"})
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "auth_denied"


# ── batch ordonné multi-tables ──────────────────────────────────────────────────
async def test_unknown_table_continues_batch(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """Une table inconnue → `unknown_table` ; la mutation suivante (valide) commit
    quand même (ADR 0014 : la suite du batch continue)."""
    user_f, account_f, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="o13@ex.com")
        return owner, account_f(owner_id=owner.id).id

    owner, account_id = await household_singleton.run_sync(_seed)
    batch = BatchUpload(
        mutations=[
            _mut("not_a_table", "insert", {}),
            _mut("transactions", "insert", {"account_id": str(account_id)}),
        ]
    )
    unknown, created = await process_batch(household_singleton, owner, batch)

    assert unknown.success is False
    assert unknown.error is not None
    assert unknown.error.code == "unknown_table"
    assert created.success is True


async def test_replay_real_handler_is_idempotent(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """Étape 2 (idempotence) sur un handler RÉEL : une mutation dont le
    `client_request_id` est déjà dans `sync_request_log` (scopé user) est ack-ée
    `success=True` SANS ré-écrire — oracle = aucune tx créée. (L'append réel du log
    par le write réussi est S13.6 ; ici on pré-remplit le log.)"""
    user_f, account_f, _, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="replay@ex.com")
        return owner, account_f(owner_id=owner.id).id

    owner, account_id = await household_singleton.run_sync(_seed)
    crid = uuid.uuid4()

    def _prefill_log(s: Session) -> None:
        s.add(SyncRequestLog(user_id=owner.id, client_request_id=crid, table_name="transactions"))
        s.flush()

    await household_singleton.run_sync(_prefill_log)

    mutation = Mutation(
        client_request_id=crid,
        table="transactions",
        op="insert",
        payload={"account_id": str(account_id)},
    )
    [result] = await process_batch(household_singleton, owner, BatchUpload(mutations=[mutation]))

    assert result.success is True
    created = (
        await household_singleton.execute(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.account_id == account_id)
        )
    ).scalar_one()
    assert created == 0  # replay : aucun draft créé
