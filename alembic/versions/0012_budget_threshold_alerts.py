"""budget_threshold_alerts table (E08 idempotence des alertes de seuil)

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-02

Materialises `backend.modules.budget.models.BudgetThresholdAlert` (S08.3, #127).

Table d'idempotence **server-only** (hors règles de sync PowerSync) : une ligne
par `(budget_id, period_start, threshold_pct)` atteste qu'un `BudgetThresholdEvent`
a déjà été publié pour ce triplet (robuste au restart serveur et au rejeu E13).
`budget_id` est `ON DELETE CASCADE` (l'alerte n'a aucun sens hors de son budget).
`threshold_pct` est un `SMALLINT` SANS CHECK (set {80,100,120} verrouillé au
domaine). L'unique `uq_budget_threshold_alerts_dedup` (nom LITTÉRAL, pas `op.f`)
est la cible de l'`ON CONFLICT ON CONSTRAINT` de l'INSERT idempotent — son nom
doit matcher byte-for-byte le modèle (parité create_all/Alembic).

Kept self-contained (no import from `models.py`) so a future model rename
cannot break a replay of this revision (gabarit `0008`/`0009`/`0011`).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "budget_threshold_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("budget_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("threshold_pct", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_budget_threshold_alerts")),
        sa.ForeignKeyConstraint(
            ["budget_id"],
            ["budgets.id"],
            name=op.f("fk_budget_threshold_alerts_budget_id_budgets"),
            ondelete="CASCADE",
        ),
        # Literal name (NOT op.f) — it is the stable target of `ON CONFLICT ON
        # CONSTRAINT` and must match the model's `UniqueConstraint(...)` name
        # byte-for-byte (create_all/Alembic parity).
        sa.UniqueConstraint(
            "budget_id",
            "period_start",
            "threshold_pct",
            name="uq_budget_threshold_alerts_dedup",
        ),
    )


def downgrade() -> None:
    op.drop_table("budget_threshold_alerts")  # drops its FK + unique with it
