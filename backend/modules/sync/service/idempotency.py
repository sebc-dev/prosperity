"""Étapes 2 & 9 (ADR 0014) — lecture et écriture du journal d'idempotence.

`already_processed` (étape 2) est LECTURE SEULE ; `record_processed` (étape 9)
APPEND une ligne. Les deux sont SCOPÉS USER par la PK composite
`(user_id, client_request_id)` (D10/S13.2 : ferme la pré-emption / l'oracle
cross-user, review Sécu F1). Un `client_request_id` n'est unique QUE par user → le
lookup filtre TOUJOURS sur `user_id`.

L'append (étape 9) appartient au write RÉUSSI et vit DANS sa transaction (avant le
`commit()` par-mutation du dispatcher, S13.6 / D-B) : si le crash survenait entre
le commit du write et l'append, un replay ré-écrirait (double-write). Co-localisé
ici (à côté du lookup), il ne committe RIEN — la frontière reste au dispatcher
(UoW de l'appelant, ADR 0015).
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


async def record_processed(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    client_request_id: uuid.UUID,
    table_name: str,
) -> None:
    """Étape 9 (ADR 0014) — APPEND la ligne d'idempotence DANS la transaction du
    write réussi (avant le `commit()` par-mutation du dispatcher, D-B). `table_name`
    = `Mutation.table` (mapping wire → colonne `SyncRequestLog.table_name`).

    `flush` (pas `commit`) : la frontière transactionnelle est l'affaire du
    dispatcher (UoW de l'appelant, ADR 0015). L'unicité est portée par la PK
    composite ; un doublon intra-batch est intercepté EN AMONT par
    `already_processed` (la ligne devient visible après le commit-par-mutation)."""
    session.add(
        SyncRequestLog(
            user_id=user_id,
            client_request_id=client_request_id,
            table_name=table_name,
        )
    )
    await session.flush()
