"""HTTP transport du write upload handler PowerSync (S13.8, ADR 0014).

UNIQUE chemin d'écriture des clients : le flow UPLOAD passe par notre backend
FastAPI — PAS par PowerSync Service, qui ne fait que le DOWNLOAD (S13.7/ADR 0014).
Boundary PUR : authentifie (`get_current_user`), désérialise `BatchUpload`,
délègue à `process_batch`, renvoie `list[WriteResult]`.

AUCUNE logique métier, AUCUN mapping d'exception (le dispatcher a déjà curé chaque
rejet récupérable en `WriteResult.error` typé, P13.6.3 ; une exception NON mappée
propage → 500, retry PowerSync), AUCUN `commit()` (le dispatcher committe PAR
MUTATION, S13.6/ADR 0015 ; `get_db` ne fait que fournir la session).

Interne au module `sync` ; les pairs passent par `backend.modules.sync.public`.
Imports descendants légitimes (contrat `2-sync`, second-hops déjà ignorés en S13.3) :
`auth.public` (`get_current_user`/`User`) et `sync.public` (intra-module).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.public import User, get_current_user
from backend.modules.sync.public import BatchUpload, WriteResult, process_batch
from backend.shared.db import get_db

sync_router = APIRouter(prefix="/sync", tags=["sync"])

CurrentUser = Annotated[User, Depends(get_current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_db)]


@sync_router.post("/upload")
async def upload(batch: BatchUpload, user: CurrentUser, session: SessionDep) -> list[WriteResult]:
    """`POST /sync/upload` — un `WriteResult` par mutation, dans l'ordre du batch.

    Le statut est 200 même si toutes les mutations échouent : chaque erreur est un
    ack typé `WriteResult.error`, pas un statut HTTP. 401 = token absent/invalide
    (`get_current_user`) ; 422 = enveloppe malformée / `> MAX_MUTATIONS` (Pydantic).
    Aucun `commit()` ici : `process_batch` committe par mutation (S13.6/ADR 0015).
    """
    return await process_batch(session, user, batch)
