"""refresh_tokens table

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-26

Materialises `backend.modules.auth.models.RefreshToken`. Only the
HMAC-SHA256 digest of the raw token is stored (column `token_hash`, 64
hex chars, UNIQUE) — see model docstring.

The FK to `users.id` is `ON DELETE CASCADE` so account deletion
naturally garbage-collects the user's refresh tokens. The explicit
`ix_refresh_tokens_user_id` index supports future per-user revoke-all
queries (S02.4 logout-everywhere) — Postgres does not auto-index FK
columns.

`family_id` / `parent_id` materialise the OAuth-style rotation chain
that S02.4 will implement. The columns ship in this baseline migration
to avoid a follow-up migration for what is fundamentally a schema
decision; the rotation logic itself lives in the service layer in S02.4.
`parent_id` uses `ON DELETE SET NULL` (not CASCADE) so the user-level
CASCADE that wipes a family in one shot is not preempted by self-FK
cascades trying to delete in chain order.
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
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("device_label", sa.String(length=120), nullable=True),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["refresh_tokens.id"],
            name=op.f("fk_refresh_tokens_parent_id_refresh_tokens"),
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index(
        op.f("ix_refresh_tokens_user_id"),
        "refresh_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_refresh_tokens_family_id"),
        "refresh_tokens",
        ["family_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_refresh_tokens_family_id"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
