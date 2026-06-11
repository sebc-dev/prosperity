"""Étape 2 (ADR 0014) — lookup d'idempotence du write upload handler.

LECTURE SEULE et SCOPÉE USER (PK composite `(user_id, client_request_id)`,
D10/S13.2 : ferme la pré-emption / l'oracle cross-user, review Sécu F1). Un
`client_request_id` n'est unique QUE par user → le lookup filtre TOUJOURS sur
`user_id`. L'APPEND au journal (étape 9) appartient au write réussi (S13.6) —
jamais ici : ce module ne fait que *lire*.
"""

from __future__ import annotations

import uuid

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.sync.models import SyncRequestLog


async def already_processed(
    session: AsyncSession, *, user_id: uuid.UUID, client_request_id: uuid.UUID
) -> bool:
    """`True` ssi `(user_id, client_request_id)` existe déjà dans `sync_request_log`
    (mutation déjà commitée par un write antérieur réussi). Servi par la PK
    composite en préfixe `user_id` (aucun scan)."""
    stmt = select(
        exists().where(
            SyncRequestLog.user_id == user_id,
            SyncRequestLog.client_request_id == client_request_id,
        )
    )
    return bool((await session.execute(stmt)).scalar_one())
