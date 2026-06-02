"""budgets + budget_contributors tables (E08 socle persisté)

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-02

Materialises `backend.modules.budget.models.{Budget,BudgetContributor}`
(S08.1, #125).

`budgets` puis `budget_contributors` (ordre des FK). `budget_contributors.
budget_id` est `ON DELETE CASCADE` ; `budgets.{category_id,created_by}` et
`budget_contributors.user_id` sont `ON DELETE RESTRICT`. `period_kind`/`scope`
sont des `VARCHAR` SANS CHECK (verrou au boundary Pydantic S08.4 ; gabarit
`transactions.state`). `carry_over_remainder` `BOOLEAN` server_default false
(flag dormant E08, lu à partir d'E11+). Toutes les FK sont indexées ; index
partiel actif `ix_budgets_active` `WHERE archived_at IS NULL` (gabarit
`ix_categories_active`).

Kept self-contained (no import from `models.py`) so a future model rename
cannot break a replay of this revision (gabarit `0008`/`0009`).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "budgets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_kind", sa.String(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "carry_over_remainder",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_budgets")),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_budgets_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_budgets_created_by_users"),
            ondelete="RESTRICT",
        ),
    )
    # Literal index names (not op.f) to match the model's `Index(...)` names
    # exactly — the create_all/Alembic parity the snapshot pins.
    op.create_index("ix_budgets_category_id", "budgets", ["category_id"], unique=False)
    op.create_index("ix_budgets_created_by", "budgets", ["created_by"], unique=False)
    op.create_index(
        "ix_budgets_active",
        "budgets",
        ["category_id"],
        unique=False,
        postgresql_where=sa.text("archived_at IS NULL"),
    )

    op.create_table(
        "budget_contributors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("budget_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_budget_contributors")),
        sa.ForeignKeyConstraint(
            ["budget_id"],
            ["budgets.id"],
            name=op.f("fk_budget_contributors_budget_id_budgets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_budget_contributors_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "budget_id",
            "user_id",
            name=op.f("uq_budget_contributors_budget_id_user_id"),
        ),
    )
    op.create_index(
        "ix_budget_contributors_user_id", "budget_contributors", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_budget_contributors_user_id", table_name="budget_contributors")
    op.drop_table("budget_contributors")  # drops its FKs + unique with it
    op.drop_index("ix_budgets_active", table_name="budgets")
    op.drop_index("ix_budgets_created_by", table_name="budgets")
    op.drop_index("ix_budgets_category_id", table_name="budgets")
    op.drop_table("budgets")  # drops its FKs with it
