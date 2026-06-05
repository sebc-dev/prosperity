"""settlements + settlement_lines tables (E10 socle)

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-05

Materialises `backend.modules.debts.models.{Settlement,SettlementLine}` (S10.1,
#152). Aucun état ajouté sur `debts` (ADR 0002/0011) : le solde restant se
calcule par différence (S10.3).

**Ordre explicite** (les FK dictent l'ordre) :
  (1) `settlements` — FK `household_id → household.id` (NO ACTION, singleton),
      `created_by → users.id` `RESTRICT`, `linked_transaction_id →
      transactions.id` `RESTRICT` **nullable**, CHECK relationnel virtual/link ;
  (2) `settlement_lines` — FK `settlement_id → settlements.id` `CASCADE`,
      `debt_id → debts.id` `CASCADE`, CHECK `amount_cents > 0`.

Aucune FK circulaire (contrairement à 0014) → pas d'`ALTER` séparé.
`downgrade()` : ordre inverse, table-fille (`settlement_lines`) d'abord.

`type` (settlements) est un `VARCHAR` SANS CHECK énumérant le set fermé
(`internal_transfer`/`external_transfer`/`virtual`) — verrouillé au boundary
Pydantic (S10.2/S10.4, gabarit `debts.origin`/`transactions.state`). Le seul
CHECK porte le **biconditionnel** « lien NULL ⟺ type == 'virtual' » : le
littéral `'virtual'` y est dupliqué (assumé, un seul littéral relationnel).

`amount_cents` (settlement_lines) est strictement positif (CHECK, décision
D-SIGN affinant l'ADR 0011) : le nettage bidirectionnel est porté par
l'orientation de chaque `Debt`, pas par un signe sur la ligne.

Kept self-contained (no import from `models.py`) so a future model rename
cannot break a replay of this revision (gabarit `0009`..`0014`).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # (1) settlements — le règlement multi-debt. FK linked_transaction_id ->
    # transactions (RESTRICT, nullable), household_id -> household (NO ACTION),
    # created_by -> users (RESTRICT), CHECK relationnel virtual/link.
    op.create_table(
        "settlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("settled_at", sa.Date(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("linked_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_settlements")),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_settlements_household_id_household"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_settlements_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["linked_transaction_id"],
            ["transactions.id"],
            name=op.f("fk_settlements_linked_transaction_id_transactions"),
            ondelete="RESTRICT",
        ),
        # Biconditionnel : lien NULL ⟺ type == 'virtual'. Le littéral 'virtual'
        # est ici une contrainte relationnelle type↔lien, PAS une énumération du
        # set de `type` (qui reste verrouillé au boundary Pydantic).
        sa.CheckConstraint(
            "(type = 'virtual') = (linked_transaction_id IS NULL)",
            name=op.f("ck_settlements_virtual_no_link"),
        ),
    )
    # Literal index names (not op.f) to match the model's `Index(...)` names
    # exactly — the create_all/Alembic parity the snapshot pins. Both back a FK
    # RESTRICT (tx + creator); `household_id` is left unindexed (singleton).
    op.create_index(
        "ix_settlements_linked_transaction_id",
        "settlements",
        ["linked_transaction_id"],
        unique=False,
    )
    op.create_index("ix_settlements_created_by", "settlements", ["created_by"], unique=False)

    # (2) settlement_lines — distribue l'apurement par dette. FK settlement_id
    # (CASCADE, agrégat ligne-fille) + debt_id (CASCADE, projection régénérable),
    # CHECK amount > 0 (D-SIGN).
    op.create_table(
        "settlement_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("settlement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("debt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_settlement_lines")),
        sa.ForeignKeyConstraint(
            ["settlement_id"],
            ["settlements.id"],
            name=op.f("fk_settlement_lines_settlement_id_settlements"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["debt_id"],
            ["debts.id"],
            name=op.f("fk_settlement_lines_debt_id_debts"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "amount_cents > 0",
            name=op.f("ck_settlement_lines_amount_positive"),
        ),
    )
    op.create_index("ix_settlement_lines_debt_id", "settlement_lines", ["debt_id"], unique=False)
    op.create_index(
        "ix_settlement_lines_settlement_id", "settlement_lines", ["settlement_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_settlement_lines_settlement_id", table_name="settlement_lines")
    op.drop_index("ix_settlement_lines_debt_id", table_name="settlement_lines")
    op.drop_table("settlement_lines")  # drops its FKs + CHECK with it
    op.drop_index("ix_settlements_created_by", table_name="settlements")
    op.drop_index("ix_settlements_linked_transaction_id", table_name="settlements")
    op.drop_table("settlements")  # drops its FKs + CHECK with it
