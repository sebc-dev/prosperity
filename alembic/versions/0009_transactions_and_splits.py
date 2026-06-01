"""transactions + splits tables (F05 socle persisté)

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-01

Materialises `backend.modules.transactions.models.Transaction` / `Split`
(S07.2, #113).

`transactions` puis `splits` (ordre des FK). `splits.transaction_id` est
`ON DELETE CASCADE` ; `transactions.{account_id,category_id}`,
`splits.{account_id,category_id}` et `transactions.created_by` sont
`ON DELETE RESTRICT`. PAS de colonne `amount` ni `bank_transaction_id`.
`state`/`debt_generation_override` sont des `VARCHAR` SANS CHECK (verrou
au boundary domain S07.3). `splits.savings_goal_id` est une colonne UUID
nullable SANS FK (table `savings_goals` absente — option (a)).

Toutes les FK sont indexées (`ix_*`) — sans index, un delete RESTRICT/CASCADE
du parent seq-scan la table enfant (gabarit `ix_accounts_owner_id`).

Kept self-contained (no import from `models.py`) so a future model rename
cannot break a replay of this revision (gabarit `0008_categories.py`).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("payee", sa.String(length=255), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("debt_generation_override", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transactions")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_transactions_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_transactions_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_transactions_created_by_users"),
            ondelete="RESTRICT",
        ),
    )
    # Literal index names (not op.f) to match the model's `Index(...)` names
    # exactly — the create_all/Alembic parity the snapshot pins.
    op.create_index("ix_transactions_account_id", "transactions", ["account_id"], unique=False)
    op.create_index("ix_transactions_category_id", "transactions", ["category_id"], unique=False)
    op.create_index("ix_transactions_created_by", "transactions", ["created_by"], unique=False)

    op.create_table(
        "splits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("savings_goal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_splits")),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            name=op.f("fk_splits_transaction_id_transactions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_splits_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_splits_category_id_categories"),
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_splits_transaction_id", "splits", ["transaction_id"], unique=False)
    op.create_index("ix_splits_account_id", "splits", ["account_id"], unique=False)
    op.create_index("ix_splits_category_id", "splits", ["category_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_splits_category_id", table_name="splits")
    op.drop_index("ix_splits_account_id", table_name="splits")
    op.drop_index("ix_splits_transaction_id", table_name="splits")
    op.drop_table("splits")  # drops its FKs with it
    op.drop_index("ix_transactions_created_by", table_name="transactions")
    op.drop_index("ix_transactions_category_id", table_name="transactions")
    op.drop_index("ix_transactions_account_id", table_name="transactions")
    op.drop_table("transactions")
