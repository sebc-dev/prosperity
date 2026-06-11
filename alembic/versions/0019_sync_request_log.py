"""sync_request_log table (E13 / S13.2 P13.2.2)

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-11

Materialises `backend.modules.sync.models.SyncRequestLog` (#187) : le journal
d'idempotence du write upload handler (ADR 0014, étape 9). PK COMPOSITE
`(user_id, client_request_id)` ⇒ idempotence SCOPÉE PAR USER (ferme la
pré-emption / l'oracle cross-user, review Sécu F1). `client_request_id` est
fourni par le client (UUID, pas de `server_default`). SERVER-ONLY : jamais dans
la PUBLICATION PowerSync (ADR 0003 ; la table est listée comme exclue permanente
dans `compose/initdb/10_powersync_publication.sql`). FK `user_id → users` en
`ON DELETE RESTRICT` (un user n'est jamais hard-deleted). Index `processed_at` →
dessert le `DELETE` de la purge nightly (rétention 30j, `service.retention`).

Kept self-contained (no import from `models.py`) so a future model rename cannot
break a replay of this revision (gabarit `0007`..`0018`). PK/FK/index names are
emitted via `op.f(...)` to match the model's `NAMING_CONVENTION` output
(create_all/Alembic parity the snapshot pins).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sync_request_log",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("table_name", sa.String(length=63), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "user_id",
            "client_request_id",
            name=op.f("pk_sync_request_log"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_sync_request_log_user_id_users"),
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_sync_request_log_processed_at",
        "sync_request_log",
        ["processed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sync_request_log_processed_at",
        table_name="sync_request_log",
    )
    op.drop_table("sync_request_log")  # drops its composite PK + the FK with it
