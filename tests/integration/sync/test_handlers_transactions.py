"""Intégration — sous-handlers `transactions` + `splits` (S13.4 / P13.4.1).

`process_batch` (handlers + checks RÉELS, vrai Postgres, rollback-isolé) route
chaque `(op, payload)` vers `transactions.public` puis flush. Oracle = état DB lu
dans la même session. Depuis S13.6 (P13.6.3) le dispatcher MAPPE les exceptions
domaine en `result.error.code` (plus de propagation) ; les seuls `pytest.raises`
résiduels assertent une `ValidationError` Pydantic (payload mal formé, étape 3 — AVANT
le write, donc inconnue du mapping domaine : elle propage → 500, D-I).

Les entités RÉFÉRENCÉES (tx, split) sont SEED via factories pour disposer d'un id
connu. Depuis S13.6 (P13.6.2) chaque `insert` reporte aussi l'`id` généré serveur
dans `result.server_values` (ack étape 10), asséré ici contre la row créée ;
`update`/`delete` n'en portent pas.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.modules.auth.models import User
from backend.modules.sync.models import SyncRequestLog
from backend.modules.sync.public import BatchUpload, Mutation
from backend.modules.sync.service.dispatcher import process_batch
from backend.modules.transactions.domain import TransactionState
from backend.modules.transactions.models import Split, Transaction
from tests.integration.sync._sync_helpers import mut as _mut
from tests.integration.sync._sync_helpers import run_one as _run

_TxFactories = Callable[[], Awaitable[tuple[type, type, type, type]]]


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
    assert result.server_values == {"id": str(row.id)}  # ack étape 10 : id généré serveur


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
    new_split = (
        await household_singleton.execute(select(Split).where(Split.transaction_id == tx_id))
    ).scalar_one()  # exactement une jambe ajoutée
    # `domain.Split` n'a pas d'`id` : le handler isole l'id du split neuf par diff
    # `list_split_ids` avant/après — l'ack le reporte au client (étape 10).
    assert result.server_values == {"id": str(new_split.id)}


async def test_split_insert_ack_id_is_the_new_leg_not_a_prior_one(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """Verrou du diff `list_split_ids` (D-D adapté) : sur une tx qui porte DÉJÀ une jambe,
    l'ack d'un `splits/insert` reporte l'id de la jambe NEUVE — pas celui de la préexistante.
    Un handler qui renverrait « la dernière » ou un id arbitraire le ferait tomber."""
    user_f, account_f, tx_f, split_f = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID, uuid.UUID, uuid.UUID]:
        owner = user_f(email="o3b@ex.com")
        acc = account_f(owner_id=owner.id)
        tx = tx_f(account_id=acc.id, created_by=owner.id, splits=False)
        existing = split_f(transaction_id=tx.id, account_id=acc.id)  # jambe préexistante
        return owner, acc.id, tx.id, existing.id

    owner, account_id, tx_id, existing_id = await household_singleton.run_sync(_seed)
    payload = {
        "transaction_id": str(tx_id),
        "account_id": str(account_id),
        "amount_cents": 700,
        "currency": "EUR",
    }
    result = await _run(household_singleton, owner, _mut("splits", "insert", payload))

    assert result.success is True
    assert result.server_values is not None
    new_id = result.server_values["id"]
    assert new_id != str(existing_id)  # PAS la jambe préexistante
    all_ids = {
        str(sid)
        for sid in (
            await household_singleton.execute(select(Split.id).where(Split.transaction_id == tx_id))
        )
        .scalars()
        .all()
    }
    assert all_ids == {str(existing_id), new_id}  # l'ack désigne bien la jambe neuve


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


async def test_split_insert_foreign_leg_denied(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """D-N : un `splits/insert` dont la tx PARENTE est accessible MAIS dont la jambe
    (`account_id`) vise un compte d'AUTRUI → `auth_denied`. C'est la garantie « pas de
    jambe glissée vers un compte d'autrui » migrée de `_check_create_transaction` vers
    `_check_mutate_split` sous la décomposition plate — un fail-open ici la perdrait."""
    user_f, account_f, tx_f, _ = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID, uuid.UUID]:
        owner = user_f(email="leg-owner@ex.com")
        other = user_f(email="leg-other@ex.com")
        acc = account_f(owner_id=owner.id)
        foreign = account_f(owner_id=other.id)  # compte d'autrui
        tx = tx_f(account_id=acc.id, created_by=owner.id, splits=False)
        return owner, tx.id, foreign.id

    owner, tx_id, foreign_account_id = await household_singleton.run_sync(_seed)
    payload = {
        "transaction_id": str(tx_id),  # tx parente accessible
        "account_id": str(foreign_account_id),  # jambe vers un compte d'autrui
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


async def test_unbalanced_planned_rejected(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """Une transition `draft → planned` sur une tx déséquilibrée (`assert_zero_sum`
    après `assert_transition`) → `UnbalancedTransactionError`, CAPTURÉE par la frontière
    par-mutation (S13.6) → `success=False`, code typé `unbalanced_transaction` (P13.6.3)."""
    user_f, account_f, tx_f, split_f = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID]:
        owner = user_f(email="o10@ex.com")
        acc = account_f(owner_id=owner.id)
        tx = tx_f(account_id=acc.id, created_by=owner.id, splits=False)
        split_f(transaction_id=tx.id, account_id=acc.id, amount_cents=500)  # 1 jambe → déséquilibré
        return owner, tx.id

    owner, tx_id = await household_singleton.run_sync(_seed)
    result = await _run(
        household_singleton,
        owner,
        _mut("transactions", "update", {"id": str(tx_id), "state": "planned"}),
    )
    assert result.success is False
    assert result.error is not None
    assert result.error.code == "unbalanced_transaction"


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
