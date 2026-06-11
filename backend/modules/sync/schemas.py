"""Schemas Pydantic du format batch PowerSync — le contrat *wire* du write upload
handler (ADR 0014).

Distincts des modèles domaine/ORM : l'enveloppe ne porte AUCUNE logique métier
(D8). La validation par-table vit dans les sous-handlers (S13.4) qui valident
`Mutation.payload` contre le schema de leur table ; ici on ne shape que le format
de transport. `extra="forbid"` sur les quatre schemas → un champ parasite est un
422 (rejet bruyant), pas un drop silencieux.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# Anti-DoS (C-SEC-2) : bornes sur l'enveloppe avant tout traitement. PUBLIQUES
# (pas de préfixe `_`) car elles sont la source unique de vérité, consommée aussi
# par les tests (gabarit `MAX_OFX_BYTES` de `banking.providers.ofx`).
MAX_MUTATIONS = 1000  # borne haute de la boucle séquentielle (ADR 0014)
MAX_TABLE_NAME = 63  # limite d'identifiant Postgres

MutationOp = Literal["insert", "update", "delete"]

# Identifiant de table : non vide et borné (gabarit `Tag` de
# `transactions/schemas.py`). Le `min_length=1` ferme la `table=""` au niveau wire
# — le dispatcher (S13.3) la rejetterait de toute façon faute de sous-handler.
TableName = Annotated[str, StringConstraints(min_length=1, max_length=MAX_TABLE_NAME)]


class Mutation(BaseModel):
    """Une mutation du batch montant.

    `client_request_id` : UUID client porteur de l'idempotence (scopée user en
    base, cf. `models.SyncRequestLog`). Toute version d'UUID est acceptée
    côté serveur (D7 — la v7 reste la recommandation client pour l'ordonnancement,
    mais contraindre la version couplerait le serveur à l'implémentation client) ;
    un UUID mal formé → 422. `op` hors enum → 422. `table` non vide et bornée
    (anti-DoS) ; le dispatcher (S13.3) REJETTE une `table` non mappée plutôt que
    de la persister. `payload` opaque : validé par le sous-handler de `table`
    (S13.4), qui en bornera aussi la taille/profondeur (déférée, cf. Hors-scope).
    """

    model_config = ConfigDict(extra="forbid")
    client_request_id: UUID
    table: TableName
    op: MutationOp
    payload: dict[str, Any]


class BatchUpload(BaseModel):
    """Le batch montant. L'ORDRE du tableau est PRÉSERVÉ (ADR 0014 — « création
    compte puis transaction » en un seul batch atomique). Vide = no-op valide
    (D9 — le dispatcher retourne `[]`) ; borné en cardinalité (anti-DoS)."""

    model_config = ConfigDict(extra="forbid")
    mutations: list[Mutation] = Field(max_length=MAX_MUTATIONS)


class WriteError(BaseModel):
    """Erreur d'une mutation — forme wire FIGÉE en S13.2 (`CONTEXT.md` §WriteResult :
    `{success, error?: {code, message}}` ; ADR 0014 « WriteResult.error typé »).

    `code` : chaîne libre en S13.2, resserrée en `Literal[...]` (vocabulaire fermé
    `validation_error` / `immutable_field_violation` / `auth_denied` / …) en
    S13.6 / P13.6.3 (D6). Figer la FORME maintenant (et ne différer que le
    VOCABULAIRE) évite au client un changement de contrat wire en S13.6.
    `message` : texte humain — NE DOIT JAMAIS porter de détail interne
    (`str(exc)`, SQL, chemin, PII du payload) ; le mapping discipliné vit en
    S13.4 / S13.6 (review Sécu F2). La séparation `code` (sûr) / `message` borne
    la surface de fuite.
    """

    model_config = ConfigDict(extra="forbid")
    code: str
    message: str


class WriteResult(BaseModel):
    """Résultat par mutation (ack étape 10, ADR 0014).

    `error` : objet typé `WriteError | None` (D6). `server_values` : valeurs
    générées serveur que le client adopte (l'`id` d'un `insert`, un `created_at`
    serveur, …) — un `dict` plutôt qu'un scalaire pour ne pas migrer le schema
    en S13.6 (D5). Optionnels `None` par défaut : S13.2 les DÉCLARE, S13.6 les
    PEUPLE. Aucune logique métier ici.
    """

    model_config = ConfigDict(extra="forbid")
    client_request_id: UUID
    success: bool
    error: WriteError | None = None
    server_values: dict[str, Any] | None = None
