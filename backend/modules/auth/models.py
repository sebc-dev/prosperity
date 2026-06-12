"""SQLAlchemy ORM models for the auth module.

These declarations are internal to `modules.auth`: cross-module callers
must go through `modules.auth.public`. Import-linter contract 2 enforces
that no other module imports from `modules.auth.models`.

`Base` is shared with every persisted module via `backend.shared.models`
(a single metadata makes `create_all()` and Alembic's `target_metadata`
trivially correct, and lets cross-module FKs declare without metadata
reconciliation). Cross-module model imports remain forbidden by contract 2.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DDL,
    UUID,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, validates

# Canonical home of `UserRole` is `domain.py` (SQLAlchemy-free). Re-imported
# here so `User.role` maps it and `auth.public` resolves it via `models`.
from backend.modules.auth.domain import UserRole  # noqa: F401
from backend.shared.models import Base


def _user_role_values(enum_cls: type[UserRole]) -> list[str]:
    # SQLAlchemy's `Enum.values_callable` defaults to enum member *names*
    # (`ADMIN`, `MEMBER`); the PG ENUM stores the lowercased *values*, so
    # we override to keep both representations aligned.
    return [member.value for member in enum_cls]


class User(Base):
    """A human (or service) account allowed to authenticate against the API.

    `password_hash` stores an Argon2id digest produced by `pwdlib`; the
    raw password never reaches the database. `role` is a Postgres enum
    so future values require a deliberate migration rather than a free
    string column.

    Email is normalised case-insensitively: the ORM lowercases on
    assignment (`_normalize_email`) and a functional unique index on
    `lower(email)` defends the column even against raw SQL inserts.
    Without this, "Alice@x.com" and "alice@x.com" would create two
    distinct accounts.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    # Functional unique index on `lower(email)` (see __table_args__) replaces
    # a plain UNIQUE so case-different duplicates are also rejected.
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            values_callable=_user_role_values,
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    disabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index(
            "uq_users_email_lower",
            text("lower(email)"),
            unique=True,
        ),
    )

    @validates("email")
    def _normalize_email(self, _key: str, value: str) -> str:
        # Lowercase + strip so the functional unique index on lower(email)
        # can never disagree with the actual column value.
        return value.strip().lower()


class RefreshToken(Base):
    """A persisted refresh token bound to a `User`.

    Only the HMAC-SHA256 hex digest of the random token is stored
    (`token_hash`, 64 chars), keyed by `JWT_SECRET` — the raw token is
    returned once on issuance and never re-derivable from the DB; the
    HMAC key adds a pepper so a DB-only leak cannot offline-confirm a
    candidate raw token. Same pattern as PATs will use in E10/V1; factor
    out when that lands.

    `revoked_at` is the revocation tombstone; we never delete rows so an
    audit trail (who/when) survives. `verify()` rejects any token that
    is either past `expires_at` or has a non-null `revoked_at`.

    `ondelete="CASCADE"` on the FK: removing a user drops their refresh
    tokens, which prevents orphaned rows from accumulating after account
    deletion (no rows to verify against anyway).

    `family_id` / `parent_id` materialise the OAuth-style rotation chain
    that S02.4 will implement: every `issue()` from a fresh login starts
    a new family (`family_id = uuid4()`, `parent_id = NULL`); every
    rotation reuses the parent's `family_id` and points `parent_id` back
    to the consumed token. The whole family can then be invalidated in
    one shot when replay is detected (a "ghost" verify on an already-
    revoked descendant). Adding the columns now avoids a follow-up
    migration during S02.4 even though the rotation logic itself ships
    there.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_refresh_tokens_user_id_users"),
        nullable=False,
    )
    # 64 hex chars = HMAC-SHA256 digest. Unique so `verify()` resolves a
    # token to at most one row even if two random tokens collided
    # (vanishingly unlikely with 256-bit entropy, but the constraint
    # costs nothing).
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # No `server_default`: the service layer sets `issued_at` in Python so
    # `expires_at = issued_at + ttl` stays consistent against a single clock.
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    device_label: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )
    # Self-FK uses `ondelete="SET NULL"` so a CASCADE on `users.id` (which
    # drops every row in the family at once) does not also try to cascade
    # along these self-edges and fight itself over delete order.
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "refresh_tokens.id",
            ondelete="SET NULL",
            name="fk_refresh_tokens_parent_id_refresh_tokens",
        ),
        nullable=True,
    )
    # Default to a fresh UUID so callers that construct a `RefreshToken`
    # directly (tests, raw ORM use) don't need to remember it. The
    # service's `issue()` overrides this with an explicit `uuid4()` for
    # clarity at the call site.
    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
        Index("ix_refresh_tokens_user_id", "user_id"),
        # S02.4 will need to revoke an entire family in one statement on
        # replay detection — index now so the migration is final.
        Index("ix_refresh_tokens_family_id", "family_id"),
    )


class AdminAuditLog(Base):
    """An append-only, server-only record of one privileged admin action.

    **Server-only.** This table is *never* replicated to clients via
    PowerSync — it carries no sync key and must stay absent from the sync
    rules manifest (ADR 0003 materialises the generic `audit_logs` of that
    ADR under this physical name `admin_audit_logs`; the E13 sync-rules
    guard targets this exact name). Nothing in the schema enforces this —
    it is a discipline upheld by the PowerSync configuration, which simply
    never references the table.

    **Append-only.** `log_admin_action` is the only write path, and it
    only ever INSERTs. A `BEFORE UPDATE OR DELETE` trigger (migration
    0005) raises so a compromised application account cannot rewrite or
    erase the trail. Revoking UPDATE/DELETE at the SQL-role level is
    deferred to infra (E13).

    **Identity survives account deletion.** The FKs to `users.id` use
    `ON DELETE SET NULL` so a log outlives the actor/target it references
    (a `CASCADE` would destroy the very evidence the audit exists to
    keep). But `SET NULL` alone would anonymise the trail — an admin who
    abuses privileges then deletes their account would blank every
    `actor_user_id`. To preserve non-repudiation we snapshot an immutable
    copy of the actor (`actor_email`, `actor_label`) — and optionally the
    target (`target_email`) — at log time; the FK remains only for join
    convenience.

    `metadata` is free-form JSONB so each caller stores its own context
    (`{"invitation_id": ...}`, `{"old_role": ..., "new_role": ...}`); see
    `log_admin_action`'s docstring for the never-log blacklist (no
    passwords/hashes, invitation tokens, TOTP secrets, JWT/refresh
    tokens). The Python attribute is `event_metadata` because `metadata`
    is reserved by SQLAlchemy's Declarative API; the column is still named
    `metadata` on disk.
    """

    __tablename__ = "admin_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    # Plain String, not a PG ENUM: see `AdminAction` in `domain.py` for why
    # the catalogue lives in Python only. `log_admin_action` validates the
    # value against `AdminAction` before insert.
    action: Mapped[str] = mapped_column(String, nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_admin_audit_logs_actor_user_id_users",
        ),
        nullable=True,
    )
    # Immutable actor snapshot — preserves non-repudiation even after the
    # FK is nulled by an account deletion (see class docstring).
    actor_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    actor_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_admin_audit_logs_target_user_id_users",
        ),
        nullable=True,
    )
    target_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    # `metadata` is reserved by Declarative; map the Python attribute
    # `event_metadata` onto the literal `metadata` column.
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # Audit queries filter by actor and order by time ("what did this
        # admin do, latest first"); a composite beats an `action`-only
        # index (cardinality 7, poorly selective).
        Index("ix_admin_audit_logs_actor_user_id_created_at", "actor_user_id", "created_at"),
        # `target_user_id` is an unindexed FK otherwise: Postgres seq-scans
        # this ever-growing table on every `users` delete to apply
        # `ON DELETE SET NULL` (and takes a wider lock). The index also
        # serves the symmetric query "what happened *to* this user".
        Index("ix_admin_audit_logs_target_user_id", "target_user_id"),
    )


# Append-only guard. Two triggers share one raising function so a
# compromised application account cannot rewrite or erase the trail:
#
# - `BEFORE DELETE` rejects every row delete.
# - `BEFORE UPDATE OF <content columns>` rejects any update that touches
#   the immutable content (`action`, the identity snapshot, `metadata`,
#   `created_at`, `id`). It deliberately omits `actor_user_id` /
#   `target_user_id`: the `ON DELETE SET NULL` referential action nulls
#   those columns when an account is deleted, and that internal UPDATE
#   must be allowed for the "log survives deletion" guarantee. The FK is
#   only join convenience — the snapshot is the real evidence — so
#   leaving the id columns mutable does not weaken non-repudiation.
#
# DROP TABLE / TRUNCATE are DDL/statement-level and do not fire row
# triggers, so the downgrade drop and test cleanup still work.
# `CREATE OR REPLACE` keeps every statement idempotent under the repeated
# `create_all` of the per-test transactional fixture.
#
# Declared here (DDL events on the table) so `Base.metadata.create_all`
# in the test schema installs the same guard the migration installs in
# prod — the create_all/Alembic parity the FK-naming convention also
# protects. Migration 0005 re-issues identical SQL via `op.execute`.
_APPEND_ONLY_FUNCTION_DDL = DDL(
    "CREATE OR REPLACE FUNCTION admin_audit_logs_reject_mutation() "
    "RETURNS trigger LANGUAGE plpgsql AS $$ "
    "BEGIN "
    # `%%` escapes the SQLAlchemy `DDL` `%`-expansion so plpgsql receives a
    # single `%` for its `format`-style `RAISE` placeholder. The migration
    # uses the raw single-`%` form via `op.execute` (no expansion there).
    "RAISE EXCEPTION 'admin_audit_logs is append-only; %% is rejected', TG_OP "
    "USING ERRCODE = 'restrict_violation'; "
    "END; $$"
)
_REJECT_DELETE_TRIGGER_DDL = DDL(
    "CREATE OR REPLACE TRIGGER trg_admin_audit_logs_no_delete "
    "BEFORE DELETE ON admin_audit_logs "
    "FOR EACH ROW EXECUTE FUNCTION admin_audit_logs_reject_mutation()"
)
_REJECT_CONTENT_UPDATE_TRIGGER_DDL = DDL(
    "CREATE OR REPLACE TRIGGER trg_admin_audit_logs_no_content_update "
    "BEFORE UPDATE OF id, action, actor_email, actor_label, target_email, metadata, created_at "
    "ON admin_audit_logs "
    "FOR EACH ROW EXECUTE FUNCTION admin_audit_logs_reject_mutation()"
)
event.listen(AdminAuditLog.__table__, "after_create", _APPEND_ONLY_FUNCTION_DDL)
event.listen(AdminAuditLog.__table__, "after_create", _REJECT_DELETE_TRIGGER_DDL)
event.listen(AdminAuditLog.__table__, "after_create", _REJECT_CONTENT_UPDATE_TRIGGER_DDL)


class Invitation(Base):
    """A pending, pre-addressed invitation to join the household (ADR 0010).

    **Server-only.** Never replicated to clients via PowerSync — it must
    stay absent from the sync rules manifest (re-checked in E13). Read and
    mutated only through the admin API (S04.4) and `service.invitations`.

    The raw token is returned **once** by `service.invitations.create` /
    `regenerate`; only its sha256 hex digest (`token_hash`, 64 chars) is
    stored — the raw value is never derivable from the DB. sha256 (not the
    HMAC `refresh_tokens` uses) is deliberate: the token carries 256 bits of
    entropy, so an offline pre-image is infeasible and the keyed pepper buys
    little here. The glossary (CONTEXT.md) and the S04.3 acceptance criteria
    pin sha256; see `service.invitations._hash_invitation_token`.

    Email is normalised lowercase (`@validates`), and the partial unique
    index `uq_invitations_pending_email` over `lower(email)` WHERE the row is
    still pending (`accepted_at IS NULL AND revoked_at IS NULL`) guarantees
    **at most one pending invitation per email** — even against a raw-SQL
    insert that bypasses the validator (same defence as `uq_users_email_lower`).
    An accepted/revoked row no longer participates in the index, so
    re-inviting after revocation or acceptance is allowed.

    `invited_by` is NOT NULL with `ON DELETE RESTRICT`: a pending grant of
    access must always name a real issuer. Unlike `AdminAuditLog` (which
    snapshots identity and uses `SET NULL` because it is *evidence* that must
    outlive accounts), an invitation is *operational state* — a dangling
    issuer would be a smell, and `RESTRICT` forces E05+ account deletion to
    deal with in-flight invitations explicitly. The audit evidence for an
    invitation lives in `admin_audit_logs`, not here.
    """

    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    invited_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_invitations_invited_by_users"),
        nullable=False,
    )
    # Set in Python (single clock) so `expires_at = invited_at + TTL` is
    # exact — mirrors `refresh_tokens.issue`; no `server_default`.
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        # Partial unique index (PostgreSQL-specific): at most one *pending*
        # invitation per email. `lower(email)` is functional (defends raw
        # inserts); the WHERE clause excludes accepted/revoked rows so they
        # never block a re-invite. The model DDL and migration 0006 must emit
        # an identical expression for create_all/Alembic parity.
        Index(
            "uq_invitations_pending_email",
            text("lower(email)"),
            unique=True,
            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
        # `/accept-invite` (S04.5) resolves `WHERE token_hash = ?` and must
        # match at most one row; also guards the (negligible) collision.
        UniqueConstraint("token_hash", name="uq_invitations_token_hash"),
        # Index the FK: without it Postgres seq-scans this table on every
        # `users` delete to enforce `ON DELETE RESTRICT`.
        Index("ix_invitations_invited_by", "invited_by"),
    )

    @validates("email")
    def _normalize_email(self, _key: str, value: str) -> str:
        # Lowercase + strip so the functional `lower(email)` partial index
        # can never disagree with the stored column value (gabarit `User`).
        return value.strip().lower()


class UsersPublic(Base):
    """Non-PII identity projection of `users`, synced household-wide (ADR 0003).

    The sync channel must let every member resolve a `from_user_id` /
    `requested_by` to a human name + role, but must NEVER carry `email` or
    `password_hash`. Rather than mask those columns per-query in the sync rules
    (fragile — a new PII column on `users` would silently leak until someone
    remembers to exclude it), we project a deliberately tiny read-model:
    `{user_id, display_name, role}`. Adding any column here is a conscious act,
    so PII cannot drift in.

    **Maintained by a Postgres trigger** (D-UP, gabarit `admin_audit_logs`):
    `sync_users_public()` upserts the projection on every INSERT/UPDATE of
    `users.display_name` / `users.role`. A trigger (not a service write) makes
    the projection robust to EVERY write path — even a raw SQL UPDATE — and adds
    zero coupling to the auth service / zero import-linter arc (it is DB-level).
    ADR 0015 (commit-in-service) does not apply: this is a read-model
    denormalisation, not a security-effect commit. The migration backfills it.

    `role` reuses the existing `user_role` PG enum (`create_type=False` — the
    `users` table owns its lifecycle); `user_id` is the PK and an
    `ON DELETE CASCADE` FK to `users.id` (the projection has no meaning without
    its user). `avatar_url` is deferred until a profile epic adds it to `users`.
    """

    __tablename__ = "users_public"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_users_public_user_id_users",
        ),
        primary_key=True,
    )
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            values_callable=_user_role_values,
            create_type=False,
        ),
        nullable=False,
    )


# Trigger that keeps `users_public` in lock-step with `users` (D-UP). The
# function upserts the 3 projected columns; the trigger fires AFTER INSERT and
# AFTER UPDATE OF the projected source columns only (a password rotation does not
# touch the projection, so it does not fire). `CREATE OR REPLACE` keeps both
# statements idempotent under the per-test transactional fixture's repeated
# `create_all`.
#
# Declared here (DDL events on the table) so `Base.metadata.create_all` in the
# test schema installs the SAME trigger migration 0020 installs in prod — the
# create_all/Alembic parity (A-B1). Without it `users_public` would stay empty in
# the integration tier and the visibility tests would be false-green. The events
# are listened on `UsersPublic.__table__` (created AFTER `users` via the FK
# dependency), so `users_public` exists when the trigger function runs.
_SYNC_USERS_PUBLIC_FUNCTION_DDL = DDL(
    "CREATE OR REPLACE FUNCTION sync_users_public() "
    "RETURNS trigger LANGUAGE plpgsql AS $$ "
    "BEGIN "
    "INSERT INTO users_public (user_id, display_name, role) "
    "VALUES (NEW.id, NEW.display_name, NEW.role) "
    "ON CONFLICT (user_id) DO UPDATE "
    "SET display_name = EXCLUDED.display_name, role = EXCLUDED.role; "
    "RETURN NEW; END; $$"
)
_SYNC_USERS_PUBLIC_TRIGGER_DDL = DDL(
    "CREATE OR REPLACE TRIGGER trg_sync_users_public "
    "AFTER INSERT OR UPDATE OF display_name, role ON users "
    "FOR EACH ROW EXECUTE FUNCTION sync_users_public()"
)
event.listen(UsersPublic.__table__, "after_create", _SYNC_USERS_PUBLIC_FUNCTION_DDL)
event.listen(UsersPublic.__table__, "after_create", _SYNC_USERS_PUBLIC_TRIGGER_DDL)
