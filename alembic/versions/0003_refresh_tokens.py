"""refresh_tokens table

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-26

Materialises `backend.modules.auth.models.RefreshToken`. Only the
sha256 digest of the raw token is stored (column `token_hash`, 64 hex
chars, UNIQUE) — see model docstring.

The FK to `users.id` is `ON DELETE CASCADE` so account deletion
naturally garbage-collects the user's refresh tokens. The explicit
`ix_refresh_tokens_user_id` index supports future per-user revoke-all
queries (S02.4 logout-everywhere) — Postgres does not auto-index FK
columns.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("device_label", sa.String(length=120), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_refresh_tokens_user_id_users",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "uq_refresh_tokens_token_hash",
        "refresh_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_refresh_tokens_user_id",
        "refresh_tokens",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_index("uq_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
