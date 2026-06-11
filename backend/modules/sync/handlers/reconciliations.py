"""Sous-handler `reconciliations` — placeholder V1 (S13.4 / P13.4.5).

Le module `reconciliation` est un stub : aucune logique métier en V1. Le handler
passe l'étape 1 (gate « membre actif », D-H) puis renvoie un échec EXPLICITE
`not_implemented_yet` (préparation V1), quelle que soit l'`op`. 0 arc import-linter
(aucun `public.py` métier consommé). La forme du `WriteError` est figée (S13.2) ;
le vocabulaire de code reste resserré en `Literal` en S13.6.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.public import User
from backend.modules.sync.schemas import Mutation, WriteError, WriteResult

_NOT_IMPLEMENTED = "not_implemented_yet"


async def handle_reconciliation(
    session: AsyncSession, user: User, mutation: Mutation
) -> WriteResult:
    """Toute op de `reconciliations` → échec `not_implemented_yet` (V1)."""
    return WriteResult(
        client_request_id=mutation.client_request_id,
        success=False,
        error=WriteError(code=_NOT_IMPLEMENTED, message="Reconciliation is not available in V1."),
    )
