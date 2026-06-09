"""imported_transactions table (E12 / S12.3 P12.3.1)

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-09

Materialises `backend.modules.banking.models.ImportedTransaction` (#178) : le
journal de dedup des lignes importées. `import_hash` (sha256 composite
`(account_id, date, amount_cents, libellé_normalisé)`, FITID jamais utilisé)
est **UNIQUE** — colonne d'idempotence du commit S12.4.3. FK `account_id →
accounts` ON DELETE RESTRICT (un compte n'est jamais hard-deleted, F02). En
S12.3 la table est lue seule (`analyze_import`), jamais écrite.

Kept self-contained (no import from `models.py`) so a future model rename
cannot break a replay of this revision (gabarit `0007`..`0017`). FK/index/unique
names are emitted via `op.f(...)` to match the model's `NAMING_CONVENTION`
output (create_all/Alembic parity the snapshot pins).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "imported_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_hash", sa.String(), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_imported_transactions")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_imported_transactions_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "import_hash",
            name=op.f("uq_imported_transactions_import_hash"),
        ),
    )
    op.create_index(
        "ix_imported_transactions_account_id",
        "imported_transactions",
        ["account_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_imported_transactions_account_id",
        table_name="imported_transactions",
    )
    op.drop_table("imported_transactions")  # drops its FK + unique index
