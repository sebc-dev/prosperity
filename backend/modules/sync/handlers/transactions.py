"""Sous-handlers `transactions` + `splits` du write upload handler (S13.4 / P13.4.1).

Mappe `(op, payload)` d'une mutation PowerSync vers le verbe métier de
`transactions.public` (ADR 0014 — jamais d'écriture DB directe depuis `sync`).
Séquence par mutation : **validation Pydantic par-table** (étape 3, `payloads.py`)
→ validation domaine + write (le service, étapes 4-5) → events (déjà émis par les
services via le mini-bus, rien à re-publier ici). Flush-only (D-I) : aucun
`commit()`, aucune capture d'erreur (les exceptions domaine PROPAGENT — codes
typés + isolation par-mutation = S13.6).

Le split est interne à l'aggregate (FK `ON DELETE CASCADE`), donc `splits` est
co-localisé ici (D-C) et enregistré sous sa propre clé `HANDLERS["splits"]`.
"""

from __future__ import annotations

from typing import Literal, assert_never
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.public import User
from backend.modules.sync.handlers.payloads import (
    SplitDeletePayload,
    SplitInsertPayload,
    TransactionDeletePayload,
    TransactionInsertPayload,
    TransactionUpdatePayload,
)
from backend.modules.sync.schemas import Mutation, WriteResult
from backend.modules.transactions.public import (
    add_split,
    create_draft,
    remove_split,
    transition_to_confirmed,
    transition_to_planned,
    update_editable_fields,
    void,
)

_VOID_REASON = "client_delete"  # constante bornée, sans PII client (champ server-derived)


def _ack(mutation: Mutation) -> WriteResult:
    return WriteResult(client_request_id=mutation.client_request_id, success=True)


async def _route_transition(
    session: AsyncSession, tx_id: UUID, target: Literal["planned", "confirmed", "void"]
) -> None:
    """`state` → transition du state-machine (D-K : `state` muté seul). Une transition
    refusée lève `InvalidStateTransitionError` (propage → S13.6)."""
    if target == "planned":
        await transition_to_planned(session, tx_id=tx_id)
    elif target == "confirmed":
        await transition_to_confirmed(session, tx_id=tx_id)
    elif target == "void":
        await void(session, tx_id=tx_id, reason=_VOID_REASON)
    else:  # pragma: no cover — `state` est un Literal fermé (TransactionUpdatePayload)
        assert_never(target)


async def handle_transaction(session: AsyncSession, user: User, mutation: Mutation) -> WriteResult:
    """`transactions/{insert,update,delete}` → `transactions.public`."""
    if mutation.op == "insert":
        p = TransactionInsertPayload.model_validate(mutation.payload)
        await create_draft(session, account_id=p.account_id, by_user_id=user.id, date=p.date)
    elif mutation.op == "update":
        p = TransactionUpdatePayload.model_validate(mutation.payload)
        if p.state is not None:  # transition (D-K : `state` seul, jamais mêlé à une édition)
            await _route_transition(session, p.id, p.state)
        else:
            await update_editable_fields(session, tx_id=p.id, **p.editable_fields())
    elif mutation.op == "delete":
        p = TransactionDeletePayload.model_validate(mutation.payload)
        await void(session, tx_id=p.id, reason=_VOID_REASON)
    else:  # pragma: no cover — op ∉ enum impossible (Pydantic `MutationOp`, D-O)
        assert_never(mutation.op)
    return _ack(mutation)


async def handle_split(session: AsyncSession, user: User, mutation: Mutation) -> WriteResult:
    """`splits/{insert,delete}` → `add_split`/`remove_split`. `update` non supporté
    (intercepté à l'étape 1, D-G — le handler n'est jamais atteint pour `update`)."""
    if mutation.op == "insert":
        p = SplitInsertPayload.model_validate(mutation.payload)
        await add_split(
            session,
            tx_id=p.transaction_id,
            account_id=p.account_id,
            amount_cents=p.amount_cents,
            currency=p.currency,
            category_id=p.category_id,
        )
    elif mutation.op == "delete":
        p = SplitDeletePayload.model_validate(mutation.payload)
        await remove_split(session, tx_id=p.transaction_id, split_id=p.id)
    else:  # pragma: no cover — `splits/update` non supporté → rejeté à l'étape 1 (D-G)
        msg = f"unsupported splits op: {mutation.op}"
        raise AssertionError(msg)
    return _ack(mutation)
