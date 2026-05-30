"""invitations table (server-only, token-based)

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-30

Materialises `backend.modules.auth.models.Invitation`, the token-based
invitation flow of ADR 0010 (S04.3, #76).

**Server-only.** Like `admin_audit_logs`, this table is never replicated
to clients via PowerSync — it must stay absent from the sync rules
manifest (the E13 sync-rules guard targets these names). Server-only is a
discipline of the PowerSync config (which never references the table), not
a DB mechanism.

**Partial unique index (PostgreSQL-specific).** `uq_invitations_pending_email`
is a *partial* unique index over `lower(email)` `WHERE accepted_at IS NULL
AND revoked_at IS NULL`: it enforces "at most one *pending* invitation per
email" while letting accepted/revoked rows drop out so a re-invite is
allowed. `lower(email)` is functional so the constraint also defends
against a raw-SQL insert that bypasses the ORM's `@validates`. The model's
`Index(..., postgresql_where=...)` and this `op.create_index(...,
postgresql_where=...)` must emit identical DDL (`create_all`/Alembic
parity — the same class of trap the FK-naming convention protects).

`token_hash` is unique (`/accept-invite` in S04.5 resolves a single row by
hash); `invited_by` is indexed so the `ON DELETE RESTRICT` FK does not
seq-scan this table on every `users` delete.

Kept self-contained (no import from `models.py`) so a future model rename
cannot break a replay of this revision.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("invited_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitations")),
        sa.ForeignKeyConstraint(
            ["invited_by"],
            ["users.id"],
            name=op.f("fk_invitations_invited_by_users"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("token_hash", name=op.f("uq_invitations_token_hash")),
    )
    # Literal index names (not op.f) to match the model's `Index(...)` names
    # exactly — the create_all/Alembic parity the snapshot test pins.
    op.create_index(
        "ix_invitations_invited_by",
        "invitations",
        ["invited_by"],
        unique=False,
    )
    op.create_index(
        "uq_invitations_pending_email",
        "invitations",
        [sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_invitations_pending_email", table_name="invitations")
    op.drop_index("ix_invitations_invited_by", table_name="invitations")
    # Dropping the table drops the UNIQUE(token_hash) index and the FK with it.
    op.drop_table("invitations")
