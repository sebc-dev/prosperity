"""users table

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-25

Materialises `backend.modules.auth.models.User`. The `user_role` PG enum
is created explicitly so `downgrade()` can drop it cleanly; relying on
SQLAlchemy's auto-creation leaves the type behind on a teardown round
trip and breaks the level-1 schema test.

A functional unique index on `lower(email)` replaces a plain
`UNIQUE(email)` so case-different duplicates ("Alice@x.com" vs
"alice@x.com") are rejected at the database level — defends against any
raw-SQL insert that would bypass the ORM's `@validates("email")`
normalisation.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


user_role = postgresql.ENUM("admin", "member", name="user_role", create_type=False)


def upgrade() -> None:
    user_role.create(op.get_bind(), checkfirst=False)
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_table("users")
    user_role.drop(op.get_bind(), checkfirst=False)
