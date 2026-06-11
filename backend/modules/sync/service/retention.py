"""Rétention du journal d'idempotence `sync_request_log` (S13.2 / D2).

Fonction PURE de purge : `now` est INJECTÉ (déterminisme + testabilité) et le
commit appartient à l'appelant (ADR 0015 — l'entrypoint script
`backend.scripts.purge_sync_request_log`, seul appelant de prod). Pas
d'APScheduler runtime ici : la planification est portée par le cron CI
`.github/workflows/nightly.yml` (D2 ; APScheduler reporté à l'épic récurrences,
ADR 0007 / F06). Le livrable testable — la purge idempotente — est identique
quel que soit l'ordonnanceur ; seul le déclencheur change.
"""

from __future__ import annotations

import datetime as dt
from typing import cast

from sqlalchemy import delete
from sqlalchemy.engine.cursor import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.sync.models import SyncRequestLog

# Rétention par défaut (jours). 30j : large fenêtre de replay côté client tout
# en bornant la croissance du journal (ADR 0014).
SYNC_REQUEST_LOG_RETENTION_DAYS = 30


async def purge_expired_sync_request_log(
    session: AsyncSession,
    *,
    now: dt.datetime,
    retention_days: int = SYNC_REQUEST_LOG_RETENTION_DAYS,
) -> int:
    """Supprime les lignes `processed_at < now - retention_days`.

    Idempotente (un 2ᵉ appel ne trouve plus rien → `0`) et déterministe (`now`
    injecté). Renvoie le nombre de lignes supprimées. Borne STRICTE : une ligne
    exactement à `cutoff` n'est PAS supprimée. Le `commit` appartient à
    l'appelant (ADR 0015), pas à cette fonction.
    """
    cutoff = now - dt.timedelta(days=retention_days)
    # `AsyncSession.execute` is typed as the generic `Result`, but for DML
    # SQLAlchemy returns a `CursorResult` at runtime; cast so `.rowcount` types
    # correctly (gabarit `auth.service.refresh_tokens.revoke`).
    result = cast(
        "CursorResult[None]",
        await session.execute(delete(SyncRequestLog).where(SyncRequestLog.processed_at < cutoff)),
    )
    return result.rowcount
