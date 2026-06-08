"""bank_account_external_refs table (E12 / S12.1 P12.1.1)

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-08

Materialises `backend.modules.banking.models.BankAccountExternalRef` (#176) :
mapping persistant « compte externe (réf OFX) → compte interne », unique
`(external_ref, provider)`, FK `internal_account_id → accounts` ON DELETE
RESTRICT (un compte n'est jamais hard-deleted, F02).

Kept self-contained (no import from `models.py`) so a future model rename
cannot break a replay of this revision (gabarit `0007`..`0016`). FK/index/unique
names are emitted via `op.f(...)` to match the model's `NAMING_CONVENTION`
output (create_all/Alembic parity the snapshot pins).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bank_account_external_refs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_ref", sa.String(), nullable=False),
        sa.Column("internal_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bank_account_external_refs")),
        sa.ForeignKeyConstraint(
            ["internal_account_id"],
            ["accounts.id"],
            name=op.f("fk_bank_account_external_refs_internal_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "external_ref",
            "provider",
            name=op.f("uq_bank_account_external_refs_external_ref_provider"),
        ),
    )
    op.create_index(
        "ix_bank_account_external_refs_internal_account_id",
        "bank_account_external_refs",
        ["internal_account_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_bank_account_external_refs_internal_account_id",
        table_name="bank_account_external_refs",
    )
    op.drop_table("bank_account_external_refs")  # drops its FK + unique index
