"""Intégration — sous-handlers `settlements` + `share_requests` (S13.4 / P13.4.4).

Routent vers `debts.public` — les SEULS writes debts autorisés côté client (delta
D6 : ni `share_ratio` ni `debt_generation_override`). `by_user_id` forcé `user.id`.
`create_share_request` matérialise le `Debt` SYNCHRONIQUEMENT (ADR 0002), donc le
read-after-write est fiable sans le mini-bus. Réutilise `_debts_helpers.seed`
(Alice créancière / Bob débiteur + tx confirmée à jambe de classification).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.modules.auth.models import User
from backend.modules.debts.models import Debt, ShareRequest
from backend.modules.debts.public import ShareRequestNotFoundError, compute_remaining
from backend.modules.sync.public import BatchUpload, Mutation, WriteResult
from backend.modules.sync.service.dispatcher import process_batch
from tests.integration._debts_helpers import Scenario, debt_count, seed, share_request_count

_TxFactories = Callable[[], Awaitable[tuple[type, type, type, type]]]


def _mut(table: str, op: str, payload: Mapping[str, object]) -> Mutation:
    return Mutation(client_request_id=uuid.uuid4(), table=table, op=op, payload=dict(payload))  # type: ignore[arg-type]


async def _run(session: AsyncSession, user: User, mutation: Mutation) -> WriteResult:
    [result] = await process_batch(session, user, BatchUpload(mutations=[mutation]))
    return result


async def _seed_expense(session: AsyncSession, factories: _TxFactories) -> tuple[User, Scenario]:
    """Alice (créancière) + Bob (débiteur) + tx confirmée perso (expense_total=1000)."""
    sc = await seed(session, factories, legs=[(-1000, False), (1000, True)])
    alice = await session.get(User, sc.alice_id)
    assert alice is not None
    return alice, sc


# ── share_requests ──────────────────────────────────────────────────────────
async def test_share_request_insert_materializes_debt(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    alice, sc = await _seed_expense(household_singleton, bound_transaction_factories)
    payload = {
        "transaction_id": str(sc.tx_id),
        "requested_from": str(sc.bob_id),
        "ratio": "0.5",
        "short_label": "diner",
    }
    result = await _run(household_singleton, alice, _mut("share_requests", "insert", payload))

    assert result.success is True
    assert await share_request_count(household_singleton, tx_id=sc.tx_id) == 1
    assert await debt_count(household_singleton, tx_id=sc.tx_id) == 1  # matérialisé in-transaction


async def test_share_request_debt_visible_after_expire_all(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """Read-after-write au niveau DB (S13.5) : après `share_requests/insert` via
    `process_batch`, un `flush()`+`expire_all()`+re-`select(Debt)` relit le `Debt`
    (`origin='personal_share_request'`) — l'`INSERT` SQL est bien émis et relisible
    IN-TRANSACTION (pas un objet `pending`). N.B. : la matérialisation share_request est
    SYNCHRONE IN-FUNCTION (`create_share_request`), PAS via le mini-bus — cette suite ne
    verrouille donc pas le `dispatch`, seulement « le handler appelle bien
    `create_share_request` » ; l'asymétrie insert(`debt_count==1`)/delete(`==0`) des tests
    voisins reste le contrôle anti-always-green."""
    alice, sc = await _seed_expense(household_singleton, bound_transaction_factories)
    payload = {
        "transaction_id": str(sc.tx_id),
        "requested_from": str(sc.bob_id),
        "ratio": "0.5",
        "short_label": "diner",
    }
    result = await _run(household_singleton, alice, _mut("share_requests", "insert", payload))
    assert result.success is True

    await household_singleton.flush()
    household_singleton.expire_all()
    debts = (
        (
            await household_singleton.execute(
                select(Debt).where(
                    Debt.source_transaction_id == sc.tx_id, Debt.origin == "personal_share_request"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(debts) == 1


async def test_share_request_delete_revokes_and_removes_debt(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    alice, sc = await _seed_expense(household_singleton, bound_transaction_factories)
    insert_payload = {
        "transaction_id": str(sc.tx_id),
        "requested_from": str(sc.bob_id),
        "ratio": "0.5",
        "short_label": "diner",
    }
    await _run(household_singleton, alice, _mut("share_requests", "insert", insert_payload))
    sr_id = (
        await household_singleton.execute(
            select(ShareRequest.id).where(ShareRequest.source_transaction_id == sc.tx_id)
        )
    ).scalar_one()

    result = await _run(
        household_singleton, alice, _mut("share_requests", "delete", {"id": str(sr_id)})
    )

    assert result.success is True
    assert await debt_count(household_singleton, tx_id=sc.tx_id) == 0  # Debt retiré


async def test_share_request_revoke_not_owner_raises(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """Bob (≠ requested_by) tente de révoquer la SR d'Alice → `ShareRequestNotFoundError`
    (404 uniforme, anti-oracle) PROPAGE (D-I)."""
    alice, sc = await _seed_expense(household_singleton, bound_transaction_factories)
    insert_payload = {
        "transaction_id": str(sc.tx_id),
        "requested_from": str(sc.bob_id),
        "ratio": "0.5",
        "short_label": "diner",
    }
    await _run(household_singleton, alice, _mut("share_requests", "insert", insert_payload))
    sr_id = (
        await household_singleton.execute(
            select(ShareRequest.id).where(ShareRequest.source_transaction_id == sc.tx_id)
        )
    ).scalar_one()
    bob = await household_singleton.get(User, sc.bob_id)
    assert bob is not None
    assert (
        await debt_count(household_singleton, tx_id=sc.tx_id) == 1
    )  # matérialisé avant la tentative

    with pytest.raises(ShareRequestNotFoundError):
        await _run(household_singleton, bob, _mut("share_requests", "delete", {"id": str(sr_id)}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ratio", "5"),  # ratio > 1 (borne `(0, 1]`, parité REST)
        ("ratio", "0"),  # ratio == 0 (borne `gt=0`)
        ("short_label", "line1\nline2"),  # caractère de contrôle (whitelist anti-injection)
        ("short_label", ""),  # vide (min_length=1 / blank après trim)
    ],
)
async def test_share_request_insert_invalid_payload_rejected(
    household_singleton: AsyncSession,
    bound_transaction_factories: _TxFactories,
    field: str,
    value: str,
) -> None:
    """Bornes de valeur/format de la frontière sync (parité REST) → `ValidationError`
    AVANT tout write : `ratio ∈ (0, 1]` et `short_label` whitelisté (texte imposé au
    débiteur, single-line). L'étape 1 passe (Alice = membre actif), donc le rejet vient
    bien de la validation Pydantic du handler, pas de l'auth."""
    alice, sc = await _seed_expense(household_singleton, bound_transaction_factories)
    payload = {
        "transaction_id": str(sc.tx_id),
        "requested_from": str(sc.bob_id),
        "ratio": "0.5",
        "short_label": "diner",
        field: value,
    }
    with pytest.raises(ValidationError):
        await _run(household_singleton, alice, _mut("share_requests", "insert", payload))


# ── settlements ───────────────────────────────────────────────────────────────
async def test_settlement_insert_creates_with_lines(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """Un règlement `external_transfer` lié à une tx confirmée apure le `Debt` (oracle =
    remaining → 0). Scénario auto-contenu (debt inséré directement, gabarit
    `test_create_settlement`) : prouve que le handler consomme `create_settlement`."""
    user_f, account_f, tx_f, split_f = await bound_transaction_factories()

    def _seed(_s: Session) -> tuple[User, uuid.UUID, uuid.UUID]:
        creditor = user_f(email="set-cred@ex.com")
        debtor = user_f(email="set-deb@ex.com")
        acc = account_f(owner_id=creditor.id, name="Cred perso")
        tx = tx_f(account_id=acc.id, created_by=creditor.id, state="confirmed", splits=False)
        split_f(transaction_id=tx.id, account_id=acc.id, amount_cents=-4200, currency="EUR")
        split_f(transaction_id=tx.id, account_id=acc.id, amount_cents=4200, currency="EUR")
        debt = Debt(
            from_user_id=debtor.id,
            to_user_id=creditor.id,
            amount_cents=4200,
            currency="EUR",
            account_id=acc.id,
            source_transaction_id=tx.id,
            origin="personal_share_request",
        )
        _s.add(debt)
        _s.flush()
        return creditor, debt.id, tx.id

    creditor, debt_id, tx_id = await household_singleton.run_sync(_seed)
    payload = {
        "settlement_type": "external_transfer",
        "linked_transaction_id": str(tx_id),
        "settled_at": "2026-06-05",
        "lines": [{"debt_id": str(debt_id), "amount_cents": 4200}],
    }
    result = await _run(household_singleton, creditor, _mut("settlements", "insert", payload))

    assert result.success is True
    assert await compute_remaining(household_singleton, debt_id=debt_id) == 0


async def test_settlement_update_unsupported_denied(
    household_singleton: AsyncSession, bound_transaction_factories: _TxFactories
) -> None:
    """Un règlement est immuable : `settlements/update` n'a pas de check (D-G) →
    `auth_denied`, le handler n'est jamais atteint."""
    alice, _sc = await _seed_expense(household_singleton, bound_transaction_factories)
    result = await _run(
        household_singleton, alice, _mut("settlements", "update", {"id": str(uuid.uuid4())})
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "auth_denied"


@pytest.mark.parametrize(
    "overrides",
    [
        {"note": "paid\nin cash"},  # caractère de contrôle (whitelist anti-injection)
        {"lines": [{"debt_id": "00000000-0000-0000-0000-000000000001", "amount_cents": 0}]},  # ≤ 0
        {
            "lines": [
                {"debt_id": "00000000-0000-0000-0000-000000000001", "amount_cents": 1}
                for _ in range(101)  # > _MAX_SETTLEMENT_LINES
            ]
        },
    ],
)
async def test_settlement_insert_invalid_payload_rejected(
    household_singleton: AsyncSession,
    bound_transaction_factories: _TxFactories,
    overrides: Mapping[str, object],
) -> None:
    """Bornes de la frontière sync (parité REST) → `ValidationError` AVANT tout write :
    `note` whitelistée (texte imposé, single-line), `amount_cents > 0` par ligne, et
    bornage anti-DoS du nombre de lignes. L'étape 1 passe (Alice = membre actif)."""
    alice, _sc = await _seed_expense(household_singleton, bound_transaction_factories)
    payload: dict[str, object] = {
        "settlement_type": "external_transfer",
        "linked_transaction_id": str(uuid.uuid4()),
        "settled_at": "2026-06-05",
        "lines": [{"debt_id": str(uuid.uuid4()), "amount_cents": 100}],
        **overrides,
    }
    with pytest.raises(ValidationError):
        await _run(household_singleton, alice, _mut("settlements", "insert", payload))
