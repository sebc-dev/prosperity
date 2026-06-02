"""transactions.share_request_id (dormant) + debt_generation_override CHECK

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-02

Two S07.4 (#115) deltas on `transactions`:

- `share_request_id` : nullable UUID column WITHOUT a `ForeignKey` (the
  `share_requests` table lives in `debts`/E09 and does not exist yet — same
  dormant pattern as `splits.savings_goal_id`). The acceptance criterion of
  `update_editable_fields` requires it to be persistable; E09 will add the FK
  + the `ShareRequest` entity in its own migration, so this is never replayed.
- `ck_transactions_debt_generation_override` : defense-in-depth CHECK on the
  closed 3-value set (D14). `update_editable_fields` mutates the field through
  `model_copy`, which bypasses the Pydantic `Literal` — the DB CHECK is the
  fail-closed backstop for that path. The Pydantic schema at the route boundary
  (S07.5) stays the primary guard (422).

Kept self-contained (no import from `models.py`) so a future model rename
cannot break a replay of this revision (gabarit `0009_transactions_and_splits.py`).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("share_request_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_transactions_debt_generation_override"),
        "transactions",
        "debt_generation_override IN ('default', 'force_full_debt', 'force_no_debt')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_transactions_debt_generation_override"), "transactions", type_="check"
    )
    op.drop_column("transactions", "share_request_id")
