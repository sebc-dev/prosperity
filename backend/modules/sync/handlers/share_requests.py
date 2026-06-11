"""Sous-handler `share_requests` du write upload handler (S13.4 / P13.4.4).

Mappe vers `debts.public` (ADR 0014) : `insert → create_share_request` (matérialise
le `Debt` synchroniquement dans la même transaction, ADR 0002), `delete →
revoke_share_request` (supprime le `Debt` matérialisé). `by_user_id` forcé `user.id` ;
`requested_from` est une cible légitime au payload. `update` non supporté (intercepté
à l'étape 1, D-G). Flush-only (D-I)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.public import User
from backend.modules.debts.public import create_share_request, revoke_share_request
from backend.modules.sync.handlers.payloads import (
    ShareRequestDeletePayload,
    ShareRequestInsertPayload,
)
from backend.modules.sync.schemas import Mutation, WriteResult


async def handle_share_request(
    session: AsyncSession, user: User, mutation: Mutation
) -> WriteResult:
    """`share_requests/{insert,delete}` → `debts.public`."""
    if mutation.op == "insert":
        ins = ShareRequestInsertPayload.model_validate(mutation.payload)
        await create_share_request(
            session,
            transaction_id=ins.transaction_id,
            requested_from=ins.requested_from,
            ratio=ins.ratio,
            short_label=ins.short_label,
            by_user_id=user.id,
        )
    elif mutation.op == "delete":
        dele = ShareRequestDeletePayload.model_validate(mutation.payload)
        await revoke_share_request(session, share_request_id=dele.id, by_user_id=user.id)
    else:  # pragma: no cover — `share_requests/update` non supporté → rejeté à l'étape 1 (D-G)
        msg = f"unsupported share_requests op: {mutation.op}"
        raise AssertionError(msg)
    return WriteResult(client_request_id=mutation.client_request_id, success=True)
