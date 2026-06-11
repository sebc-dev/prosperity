"""Entrypoint cron de la purge nightly du journal d'idempotence (S13.2 / D2).

`python -m backend.scripts.purge_sync_request_log` — déclenché par le job
`purge-sync-request-log` de `.github/workflows/nightly.yml` (gabarit
`powersync-smoke` : Postgres + `DATABASE_URL`). C'est le SEUL appelant de prod de
`service.retention.purge_expired_sync_request_log` ; il porte donc le commit
(ADR 0015 — la fonction de purge est pure) et le cycle de vie de l'engine.

SÉCURITÉ (review Sécu F3) : on logge UNIQUEMENT le nombre de lignes supprimées,
JAMAIS le DSN / l'URL de connexion. Le masquage `sed` du gabarit nightly couvre
toute sortie résiduelle ; cet entrypoint ne l'expose pas en premier lieu.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.config import get_settings
from backend.modules.sync.service.retention import purge_expired_sync_request_log
from backend.shared.db import build_engine

logger = logging.getLogger(__name__)


async def main() -> None:
    """Purge les lignes expirées et commit. Engine construit depuis les settings
    (`DATABASE_URL`), disposé en fin de run. Ne logge que le compte."""
    engine = build_engine(get_settings())
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            deleted = await purge_expired_sync_request_log(session, now=datetime.now(tz=UTC))
            await session.commit()
        logger.info("purged %d expired sync_request_log row(s)", deleted)
    finally:
        await engine.dispose()


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
