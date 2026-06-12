"""Sous-handler `accounts` du write upload handler (S13.4 / P13.4.2).

Mappe `(op, payload)` vers `accounts.public` (ADR 0014). `insert` est discriminé
par la présence de `members` au payload : personnel (`create_personal`, `owner_id`
forcé `user.id`) vs commun (`create_shared`). Flush-only (D-I).

⚠️ `create_shared` n'est PAS auth-aware (il ne valide que la forme / Σ ratios == 1),
donc le contrôle d'appartenance (caller ∈ membres, chaque membre actif du foyer)
vit à l'étape 1 du dispatcher (`_check_create_shared_account`, D-M) — pas ici.
"""

from __future__ import annotations

from typing import Any, assert_never

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.public import (
    archive,
    create_personal,
    create_shared,
    rename,
)
from backend.modules.auth.public import User
from backend.modules.sync.handlers.payloads import (
    AccountDeletePayload,
    AccountInsertPersonalPayload,
    AccountInsertSharedPayload,
    AccountUpdatePayload,
)
from backend.modules.sync.schemas import Mutation, WriteResult


def _ack(mutation: Mutation, *, server_values: dict[str, Any] | None = None) -> WriteResult:
    """Ack étape 10 ; `server_values` reporte l'`id` généré serveur pour un `insert`."""
    return WriteResult(
        client_request_id=mutation.client_request_id, success=True, server_values=server_values
    )


async def handle_account(session: AsyncSession, user: User, mutation: Mutation) -> WriteResult:
    """`accounts/{insert,update,delete}` → `accounts.public`."""
    if mutation.op == "insert":
        if "members" in mutation.payload:  # compte commun (D-M : appartenance vérifiée étape 1)
            shared = AccountInsertSharedPayload.model_validate(mutation.payload)
            account = await create_shared(
                session,
                members=shared.to_member_shares(),
                name=shared.name,
                type=shared.type,
                currency=shared.currency,
            )
        else:  # compte personnel : owner forcé `user.id`
            personal = AccountInsertPersonalPayload.model_validate(mutation.payload)
            account = await create_personal(
                session,
                owner_id=user.id,
                name=personal.name,
                type=personal.type,
                currency=personal.currency,
            )
        return _ack(mutation, server_values={"id": str(account.id)})  # id généré serveur
    if mutation.op == "update":
        upd = AccountUpdatePayload.model_validate(mutation.payload)
        await rename(session, account_id=upd.id, user_id=user.id, name=upd.name)
        return _ack(mutation)
    if mutation.op == "delete":
        dele = AccountDeletePayload.model_validate(mutation.payload)
        await archive(session, account_id=dele.id, user_id=user.id)
        return _ack(mutation)
    assert_never(mutation.op)  # pragma: no cover — op ∉ enum (Pydantic `MutationOp`, D-O)
