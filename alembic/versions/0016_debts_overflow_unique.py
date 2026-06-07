"""debts overflow idempotence partial unique index (E11 / S11.3 P11.3.1)

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-06

Materialises `backend.modules.debts.models.Debt`'s new
`Index("uq_debts_overflow_active", ...)` (S11.3, #166) : a **partial unique**
index on `(source_transaction_id, from_user_id, to_user_id, origin)
WHERE origin = 'shared_account_overflow'`. It backs the materializer's
`INSERT ... ON CONFLICT (...) DO UPDATE` (P11.3.2) so re-dispatching a
`TransactionConfirmedEvent` converges on the same overflow `Debt` set
(idempotence, AC opposable).

The partial predicate scopes the uniqueness to overflow rows ONLY → an upsert
of a `shared_account_overflow` debt can never collide with a co-present
`personal_share_request` debt sharing the same `(tx, from, to)` triple
(exclusivité d'origine). The pre-existing `ix_debts_source_transaction_id`
(standalone, 0014) is KEPT: this partial index does not serve lookups by
`source_transaction_id` for the other origins.

Kept self-contained (no import from `models.py`) so a future model rename
cannot break a replay of this revision (gabarit `0009`..`0015`). The literal
`'shared_account_overflow'` of the partial predicate is intentionally duplicated
here — it must match the model's `postgresql_where` byte-for-byte (parity pinned
by the schema snapshot).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Literal index name (not op.f) to match the model's `Index(...)` name
    # byte-for-byte — the create_all/Alembic parity the snapshot pins. Partial
    # unique index supporting `ON CONFLICT (...) DO UPDATE ... WHERE origin =
    # 'shared_account_overflow'`; `postgresql_where` must match the model
    # (same trap as `uq_share_requests_active`).
    op.create_index(
        "uq_debts_overflow_active",
        "debts",
        ["source_transaction_id", "from_user_id", "to_user_id", "origin"],
        unique=True,
        postgresql_where=sa.text("origin = 'shared_account_overflow'"),
    )


def downgrade() -> None:
    op.drop_index("uq_debts_overflow_active", table_name="debts")
