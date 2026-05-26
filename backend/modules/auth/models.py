"""SQLAlchemy ORM models for the auth module.

These declarations are internal to `modules.auth`: cross-module callers
must go through `modules.auth.public`. Import-linter contract 2 enforces
that no other module imports from `modules.auth.models`.

`Base` lives here because auth is the first module to ship persisted
models. When future modules add their own tables they can either reuse
this `Base` (via Alembic's `target_metadata` aggregator) or declare a
sibling `Base`; cross-module model imports remain forbidden either way.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    UUID,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    MetaData,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, validates

# Explicit naming convention so constraints created via `create_all` (used in
# tests) match the names Alembic produces via `op.f(...)`. Without this, a
# future `alembic revision --autogenerate` would diff every constraint and
# generate noisy renames.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class UserRole(enum.StrEnum):
    """Roles authorised to authenticate against the API.

    Mirrored by the Postgres `user_role` ENUM (Alembic 0002). Adding a
    value requires a migration that ALTERs that type. Subclassing
    `enum.StrEnum` gives runtime enforcement on assignment plus a single
    source of truth for the Pydantic transports landing in S02.4.
    """

    ADMIN = "admin"
    MEMBER = "member"


def _user_role_values(enum_cls: type[UserRole]) -> list[str]:
    # SQLAlchemy's `Enum.values_callable` defaults to enum member *names*
    # (`ADMIN`, `MEMBER`); the PG ENUM stores the lowercased *values*, so
    # we override to keep both representations aligned.
    return [member.value for member in enum_cls]


class Base(DeclarativeBase):
    """Declarative base for auth-module ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


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
