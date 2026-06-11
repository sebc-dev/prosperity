"""ORM du module sync — journal d'idempotence du write upload handler (ADR 0014).

`SyncRequestLog` : une ligne par mutation effectivement commitée (étape 9 de la
séquence ADR 0014). PK COMPOSITE `(user_id, client_request_id)` : l'idempotence
est SCOPÉE PAR USER. Le `client_request_id` (UUID, généré client — v7 recommandé
pour l'ordonnancement, mais le serveur accepte tout UUID bien formé, D7) n'est
unique QUE par user. C'est la **contrainte d'unicité composite** — pas un simple
index — qui ferme la pré-emption / l'oracle cross-user (review Sécu F1) : avec
une PK sur `client_request_id` seul, un user A pourrait pré-insérer un id que le
client de B va émettre et faire ack-sans-écrire (perte silencieuse) ou collisionner
la mutation légitime de B. Scopée user, l'idempotence reste correcte et isolée.

Un replay après timeout réseau trouve la ligne `(me, id)` et le serveur ack sans
réécrire (lookup `WHERE user_id=:me AND client_request_id=:id`, servi par la PK
composite en préfixe — S13.3). SERVER-ONLY : jamais dans la PUBLICATION PowerSync
(ADR 0003 ; verrou de test `test_sync_request_log_server_only`). Rétention 30j
via purge nightly (`service.retention`, S13.2 / D2).

NB mapping (pour S13.3) : `Mutation.table` (schema wire) → `table_name` (cette
colonne). SQLA pur : aucune validation métier ici (la `table` non mappée est
rejetée par le dispatcher S13.3, jamais persistée — gabarit `banking.models`).
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    UUID,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.shared.models import Base


class SyncRequestLog(Base):
    """Journal d'idempotence (server-only) du write upload handler (ADR 0014).

    PK composite `(user_id, client_request_id)` ⇒ idempotence per-user. La FK
    `user_id → users` est déclarée **par chaîne** (`sync` au sommet du graphe,
    aucun import Python de `User`) en `ON DELETE RESTRICT` (un user n'est jamais
    hard-deleted). `table_name` `String(63)` (limite d'identifiant Postgres, set
    ouvert borné anti-DoS — gabarit `banking.provider`, pas d'ENUM).
    """

    __tablename__ = "sync_request_log"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_sync_request_log_user_id_users",
        ),
        primary_key=True,  # colonne de tête de la PK composite
    )
    client_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,  # fourni par le client, pas de server_default
    )
    table_name: Mapped[str] = mapped_column(String(63), nullable=False)
    processed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # La PK composite `(user_id, client_request_id)` dessert DÉJÀ le lookup
        # d'idempotence scopé user (S13.3) ET la FK RESTRICT en préfixe : pas
        # d'index `user_id` séparé (il serait redondant — review Sécu F1 / D10).
        # L'index `processed_at` dessert le `DELETE WHERE processed_at < cutoff`
        # de la purge nightly (`service.retention`).
        Index("ix_sync_request_log_processed_at", "processed_at"),
    )
