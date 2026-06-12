"""Sous-handler `settlements` du write upload handler (S13.4 / P13.4.4).

Mappe `settlements/insert` vers `debts.public.create_settlement` (ADR 0014) —
`by_user_id` forcé `user.id`. C'est l'un des SEULS writes debts autorisés côté
client (delta D6). `update`/`delete` ne sont pas supportés (un règlement est
immuable) : sans entrée `PERMISSION_CHECKS`, ils sont interceptés en `auth_denied`
à l'étape 1 (D-G), le handler n'est jamais atteint pour eux. Flush-only (D-I).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.public import User
from backend.modules.debts.public import create_settlement
from backend.modules.sync.handlers.payloads import SettlementInsertPayload
from backend.modules.sync.schemas import Mutation, WriteResult


def _ack(mutation: Mutation, *, server_values: dict[str, Any] | None = None) -> WriteResult:
    """Ack étape 10 ; `server_values` reporte l'`id` généré serveur pour un `insert`."""
    return WriteResult(
        client_request_id=mutation.client_request_id, success=True, server_values=server_values
    )


async def handle_settlement(session: AsyncSession, user: User, mutation: Mutation) -> WriteResult:
    """`settlements/insert` → `create_settlement`."""
    if mutation.op == "insert":
        p = SettlementInsertPayload.model_validate(mutation.payload)
        settlement = await create_settlement(
            session,
            settlement_type=p.settlement_type,
            linked_transaction_id=p.linked_transaction_id,
            settled_at=p.settled_at,
            note=p.note,
            lines=p.to_line_inputs(),
            by_user_id=user.id,
        )
        return _ack(mutation, server_values={"id": str(settlement.id)})  # id généré serveur
    # `update`/`delete` interceptés à l'étape 1 (D-G) — jamais atteints ici.
    msg = f"unsupported settlements op: {mutation.op}"  # pragma: no cover
    raise AssertionError(msg)  # pragma: no cover
