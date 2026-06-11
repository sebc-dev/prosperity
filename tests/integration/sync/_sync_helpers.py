"""Helpers partagés des tests d'intégration du write upload handler (S13.x).

`mut`/`run_one` étaient copiés verbatim dans chaque suite `tests/integration/sync/`
(`test_handlers_transactions.py`, `test_handlers_debts.py`, `test_materialization_overflow.py`).
Factorisés ici (review S13.5) : un seul corps à maintenir. Module NON collecté
(pas de préfixe `test_`, précédent `_debts_helpers.py`), hors `root_package`
import-linter.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.models import User
from backend.modules.sync.public import BatchUpload, Mutation, WriteResult
from backend.modules.sync.service.dispatcher import process_batch


def mut(table: str, op: str, payload: Mapping[str, object]) -> Mutation:
    """Build a single `Mutation` (fresh `client_request_id`)."""
    return Mutation(client_request_id=uuid.uuid4(), table=table, op=op, payload=dict(payload))  # type: ignore[arg-type]


async def run_one(session: AsyncSession, user: User, mutation: Mutation) -> WriteResult:
    """Run one mutation through `process_batch` and return its single result."""
    [result] = await process_batch(session, user, BatchUpload(mutations=[mutation]))
    return result
