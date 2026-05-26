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

from sqlalchemy import UUID, DateTime, Enum, Index, String, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, validates


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
