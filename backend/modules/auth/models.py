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

import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import UUID, DateTime, Enum, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

UserRole = Literal["admin", "member"]


class Base(DeclarativeBase):
    """Declarative base for auth-module ORM models."""


class User(Base):
    """A human (or service) account allowed to authenticate against the API.

    `password_hash` stores an Argon2id digest produced by `pwdlib`; the
    raw password never reaches the database. `role` is a Postgres enum
    so future values require a deliberate migration rather than a free
    string column.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum("admin", "member", name="user_role"),
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
