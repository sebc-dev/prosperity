"""baseline empty

Revision ID: 0001
Revises:
Create Date: 2026-05-24

Intentionally a no-op: validates that the Alembic plumbing (env.py, DSN,
async engine) executes end-to-end before any real schema lands. The only
side effect is the `alembic_version` row that Alembic itself manages.
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
