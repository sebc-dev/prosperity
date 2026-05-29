"""admin_audit_logs table (server-only, append-only)

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-30

Materialises `backend.modules.auth.models.AdminAuditLog`, the socle of
the admin audit trail (S04.2, #75).

**Server-only.** This table is never replicated to clients via PowerSync
— it must stay absent from the sync rules manifest. ADR 0003 names the
generic `audit_logs` of that ADR but materialises it under this physical
name `admin_audit_logs`; the E13 sync-rules guard targets this exact
name. Server-only is a discipline of the PowerSync config (which never
references the table), not a DB mechanism.

**Append-only.** Two triggers share one raising function so a
compromised application account cannot rewrite or erase the trail: a
`BEFORE DELETE` that rejects every delete, and a `BEFORE UPDATE OF`
the content columns that rejects any tampering with `action`, the
identity snapshot, `metadata`, `created_at`, or `id`. It deliberately
omits `actor_user_id` / `target_user_id` so the `ON DELETE SET NULL`
referential action below can still null them when an account is deleted
(the log must survive). Only `log_admin_action`'s INSERT path writes new
rows. (DROP TABLE / TRUNCATE are DDL/statement-level and do not fire row
triggers, so this `downgrade` and test cleanup still work.) SQL-role-level
revocation of UPDATE/DELETE is deferred to infra (E13). The same function
+ triggers are declared as `after_create` DDL events on the model so
`create_all` (tests) installs an identical guard — the create_all/Alembic
parity the FK-naming convention also protects.

The FKs to `users.id` use `ON DELETE SET NULL` (not CASCADE): a log must
outlive the actor/target it references — destroying it would erase the
evidence the audit exists to keep. To keep `SET NULL` from anonymising
the trail, the model snapshots an immutable copy of the actor
(`actor_email`, `actor_label`) and target (`target_email`) at log time.

`action` is a plain VARCHAR, not a PG ENUM: a new audit action must be a
code change (`AdminAction` in `domain.py`), never an `ALTER TYPE`
migration — validation lives in `log_admin_action`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Kept inline (not imported from `models.py`) so this historical migration
# stays self-contained — a future rename of the triggers must not break
# replays of this revision. `op.execute` sends the SQL raw, so the `%` in
# the `RAISE` stays a single `%` (no SQLAlchemy `DDL` `%`-expansion here).
_REJECT_MUTATION_FUNCTION = (
    "CREATE OR REPLACE FUNCTION admin_audit_logs_reject_mutation() "
    "RETURNS trigger LANGUAGE plpgsql AS $$ "
    "BEGIN "
    "RAISE EXCEPTION 'admin_audit_logs is append-only; % is rejected', TG_OP "
    "USING ERRCODE = 'restrict_violation'; "
    "END; $$"
)
_REJECT_DELETE_TRIGGER = (
    "CREATE OR REPLACE TRIGGER trg_admin_audit_logs_no_delete "
    "BEFORE DELETE ON admin_audit_logs "
    "FOR EACH ROW EXECUTE FUNCTION admin_audit_logs_reject_mutation()"
)
_REJECT_CONTENT_UPDATE_TRIGGER = (
    "CREATE OR REPLACE TRIGGER trg_admin_audit_logs_no_content_update "
    "BEFORE UPDATE OF id, action, actor_email, actor_label, target_email, metadata, created_at "
    "ON admin_audit_logs "
    "FOR EACH ROW EXECUTE FUNCTION admin_audit_logs_reject_mutation()"
)


def upgrade() -> None:
    op.create_table(
        "admin_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_email", sa.String(length=254), nullable=True),
        sa.Column("actor_label", sa.String(length=255), nullable=True),
        sa.Column("target_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_email", sa.String(length=254), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_audit_logs")),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_admin_audit_logs_actor_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"],
            ["users.id"],
            name=op.f("fk_admin_audit_logs_target_user_id_users"),
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        op.f("ix_admin_audit_logs_actor_user_id_created_at"),
        "admin_audit_logs",
        ["actor_user_id", "created_at"],
        unique=False,
    )
    op.execute(_REJECT_MUTATION_FUNCTION)
    op.execute(_REJECT_DELETE_TRIGGER)
    op.execute(_REJECT_CONTENT_UPDATE_TRIGGER)


def downgrade() -> None:
    # Dropping the table drops its trigger; the standalone function must
    # go explicitly.
    op.drop_index(
        op.f("ix_admin_audit_logs_actor_user_id_created_at"),
        table_name="admin_audit_logs",
    )
    op.drop_table("admin_audit_logs")
    op.execute("DROP FUNCTION IF EXISTS admin_audit_logs_reject_mutation()")
