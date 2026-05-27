"""household singleton table

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-27

Materialises `backend.modules.accounts.models.Household` (ADR 0010
singleton + ADR 0008 mono-currency V1).

A CHECK constraint on `id` blocks any insert that doesn't carry the
singleton UUID — defense-in-depth against raw SQL that bypasses the
ORM default. PK violation alone would only catch a second insert with
the **same** UUID; the CHECK catches every deviation.

`base_currency` ships as a plain VARCHAR(3) with no CHECK: ADR 0008
locks V1 to EUR at the Python type level only, so opening the V2
multi-currency story is a code change, not a migration on legacy data.

`_SINGLETON_UUID_LITERAL` is duplicated here (not imported from
`accounts.models`) so historical migrations stay self-contained — a
future refactor that renames the model constant must not break replays
of old migrations.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SINGLETON_UUID_LITERAL = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        "household",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("initialized_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_household")),
        sa.CheckConstraint(
            f"id = '{_SINGLETON_UUID_LITERAL}'::uuid",
            name=op.f("ck_household_singleton"),
        ),
    )


def downgrade() -> None:
    op.drop_table("household")
