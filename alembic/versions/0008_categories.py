"""categories table (F08 part 1, hierarchical self-ref tree)

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-01

Materialises `backend.modules.budget.models.Category` (S06.1, #102).

Self-referencing FK `parent_id → categories.id ON DELETE RESTRICT`:
deleting a category that still has children is refused at the DB
(defense-in-depth doubling the S06.3 service rule; CONTEXT.md "pas de
cascade"). No SQL cycle constraint — acyclicity is a service concern
(S06.2 CycleDetector).

Two indexes, distinct roles (not redundant):
- `ix_categories_parent_id` (plain): the RESTRICT referential check and
  the S06.2 ancestor walk-up must see ALL rows (archived included), so
  the index covers every row.
- `ix_categories_active` (partial, `WHERE archived_at IS NULL`): serves
  the S06.3 active-listing path on live rows only. The
  `postgresql_where` mirrors the model's `Index(..., postgresql_where=)`
  byte-for-byte (create_all/Alembic parity — same trap as
  `uq_invitations_pending_email`).

`color` ships as `VARCHAR(7)` with no CHECK: the `#RRGGBB` format is
validated at the Pydantic boundary in S06.3, not in the column (gabarit
`currency`).

Kept self-contained (no import from `models.py`) so a future model
rename cannot break a replay of this revision.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=True),
        sa.Column("icon", sa.String(), nullable=True),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["categories.id"],
            name=op.f("fk_categories_parent_id_categories"),
            ondelete="RESTRICT",
        ),
    )
    # Literal index names (not op.f) to match the model's `Index(...)`
    # names exactly — the create_all/Alembic parity the snapshot pins.
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"], unique=False)
    op.create_index(
        "ix_categories_active",
        "categories",
        ["parent_id"],
        unique=False,
        postgresql_where=sa.text("archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_categories_active", table_name="categories")
    op.drop_index("ix_categories_parent_id", table_name="categories")
    op.drop_table("categories")  # drops the self-FK with it
