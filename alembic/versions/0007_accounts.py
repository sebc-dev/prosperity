"""accounts + account_members tables (F02)

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-31

Materialises `backend.modules.accounts.models.Account` / `AccountMember`
and the `account_type` PG ENUM (S05.1, #92).

The ENUM is created explicitly (`create_type=False` + `.create()`/`.drop()`)
so `downgrade base` leaves no orphan type — gabarit `0002_users.py`
(`user_role`). FK/index names are emitted to match the model's
`NAMING_CONVENTION` output (create_all/Alembic parity the snapshot pins).

`owner_id` and `account_members.user_id` are `ON DELETE RESTRICT` (operational
state — a user is disabled, never deleted, decision F02); `account_members
→ accounts` is `ON DELETE CASCADE`. `accounts.owner_id` and
`account_members.user_id` are indexed so the RESTRICT does not seq-scan on a
`users` delete; the unique `(account_id, user_id)` covers `account_id`.

Kept self-contained (no import from `models.py`) so a future model rename
cannot break a replay of this revision.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


account_type = postgresql.ENUM(
    "courant",
    "livret",
    "epargne",
    "especes",
    "credit",
    name="account_type",
    create_type=False,
)


def upgrade() -> None:
    account_type.create(op.get_bind(), checkfirst=False)
    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("type", account_type, nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounts")),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["household.id"],
            name=op.f("fk_accounts_household_id_household"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_accounts_owner_id_users"),
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_accounts_owner_id", "accounts", ["owner_id"], unique=False)
    op.create_table(
        "account_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "default_share_ratio", sa.Numeric(precision=5, scale=4), nullable=False
        ),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_members")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_account_members_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_account_members_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "account_id",
            "user_id",
            name=op.f("uq_account_members_account_id_user_id"),
        ),
    )
    op.create_index(
        "ix_account_members_user_id", "account_members", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_account_members_user_id", table_name="account_members")
    op.drop_table("account_members")  # drops its FKs + unique index
    op.drop_index("ix_accounts_owner_id", table_name="accounts")
    op.drop_table("accounts")
    account_type.drop(op.get_bind(), checkfirst=False)
