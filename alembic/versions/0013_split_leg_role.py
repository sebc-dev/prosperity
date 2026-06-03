"""splits.leg_role + back-fill déterministe + CHECK (ADR 0017 option 1)

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-03

Materialises `backend.modules.transactions.models.Split.leg_role` (S08.5.1, #136).

Marqueur structurel du rôle de jambe (ADR 0017) : `funding` (mouvement de
compte, exempté de catégorie) vs `classification` (jambe de dépense). En
DEUX TEMPS pour rester rejouable sur des données existantes :
  (1) ajout de la colonne NULLABLE,
  (2) back-fill déterministe `category_id IS NULL ⇒ 'funding'`, sinon
      'classification' (forme canonique B),
  (3) `SET NOT NULL` une fois toutes les lignes peuplées,
  (4) CHECK defense-in-depth `ck_splits_leg_role` (set fermé 2-valeurs ;
      gabarit `ck_transactions_debt_generation_override`, migration 0010).

Kept self-contained (no import from `models.py`/`domain.py`) so a future model
rename cannot break a replay of this revision (gabarit 0009/0010/0012). Les
valeurs 'funding'/'classification' sont donc dupliquées littéralement, à dessein.

Pas de règles de sync PowerSync à éditer (aucun artefact ; client = E14,
ADR 0003). La colonne est server-authoritative et sync-safe.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # (1) colonne nullable
    op.add_column("splits", sa.Column("leg_role", sa.String(), nullable=True))
    # (2) back-fill déterministe (forme canonique B)
    op.execute(
        "UPDATE splits SET leg_role = "
        "CASE WHEN category_id IS NULL THEN 'funding' ELSE 'classification' END"
    )
    # (3) verrou NOT NULL une fois toutes les lignes peuplées
    op.alter_column("splits", "leg_role", existing_type=sa.String(), nullable=False)
    # (4) CHECK defense-in-depth (gabarit 0010)
    op.create_check_constraint(
        op.f("ck_splits_leg_role"),
        "splits",
        "leg_role IN ('funding', 'classification')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_splits_leg_role"), "splits", type_="check")
    op.drop_column("splits", "leg_role")
