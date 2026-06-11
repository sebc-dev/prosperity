"""Dispatcher du write upload handler PowerSync (ADR 0014).

`process_batch` parcourt `batch.mutations` DANS L'ORDRE DU TABLEAU (ordering
préservé, ADR 0014 ; pas de parallélisation) et matérialise la séquence par
mutation. S13.3 pose les étapes 0-2 : routage (sous-handler de `table` ou
`unknown_table`) → étape 1 auth/RBAC (P13.3.2) → étape 2 idempotence (P13.3.3).
Les étapes 3-10 (validation, write, matérialisation, events, commit, append log,
ack) vivent dans les sous-handlers (S13.4) et la frontière transactionnelle
(S13.6) ; ici les handlers sont une COUTURE injectable (mockés en test).

Registres CENTRAUX (ADR 0014 : auditables d'un seul endroit) :
- HANDLERS    : `table -> Handler` (vide en S13.3, peuplé par S13.4).
- PERMISSION_CHECKS : `(table, op) -> PermissionCheck` (étape 1, P13.3.2).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.public import User
from backend.modules.sync.schemas import (
    BatchUpload,
    Mutation,
    WriteError,
    WriteResult,
)


class Handler(Protocol):
    """Sous-handler par table (S13.4). Reçoit la session (UoW de l'appelant),
    l'utilisateur authentifié et la mutation ; renvoie le `WriteResult` (ack)."""

    async def __call__(
        self, session: AsyncSession, user: User, mutation: Mutation
    ) -> WriteResult: ...


# Registre CENTRAL de routage : `table -> Handler`. VIDE en S13.3 — la machine
# existe, les vrais handlers sont enregistrés en S13.4. Clé absente ⇒
# `unknown_table` (la suite du batch continue). Les tests INJECTENT un registre
# mocké via le paramètre `handlers` de `process_batch` (couture explicite ≻
# monkeypatch) pour prouver le routage sans dépendre des handlers réels.
HANDLERS: dict[str, Handler] = {}  # peuplé en S13.4

_UNKNOWN_TABLE = "unknown_table"  # vocabulaire ADR 0014 (resserré Literal en S13.6/D8)


async def process_batch(
    session: AsyncSession,
    user: User,
    batch: BatchUpload,
    *,
    handlers: Mapping[str, Handler] = HANDLERS,
) -> list[WriteResult]:
    """Route chaque mutation vers le sous-handler de sa `table`, dans l'ordre du
    tableau (séquentiel, pas de parallélisation — ADR 0014). Table inconnue →
    `WriteResult(error="unknown_table")` et la suite du batch continue. La session
    (UoW de l'appelant, ADR 0015) est threadée au handler ; AUCUN `commit()` ici
    (la frontière par-mutation est S13.6). `handlers` injectable = couture de test
    + point d'enregistrement S13.4 (défaut = registre module).
    """
    results: list[WriteResult] = []
    for mutation in batch.mutations:  # ordre préservé, séquentiel
        handler = handlers.get(mutation.table)
        if handler is None:
            results.append(
                WriteResult(
                    client_request_id=mutation.client_request_id,
                    success=False,
                    error=WriteError(code=_UNKNOWN_TABLE, message="Unknown table."),
                )
            )
            continue  # la suite du batch continue (ADR 0014)
        results.append(await handler(session, user, mutation))
    return results
