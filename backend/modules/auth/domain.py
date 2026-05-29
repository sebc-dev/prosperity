"""Pure domain values for the auth module (no SQLAlchemy dependency).

This module holds business-meaning types that are independent of the
persistence layer — currently the `UserRole` enum. Keeping it here (vs.
`models.py`) means a consumer can reason about roles without importing
the ORM stack, and it gives RBAC primitives (`require_admin`,
`require_member`) a SQLAlchemy-free source of truth for the enum.

Internal to `modules.auth`: cross-module callers must reach `UserRole`
through `backend.modules.auth.public`. Import-linter forbids reaching
into `backend.modules.auth.domain` directly from peer modules.
"""

from __future__ import annotations

import enum


class UserRole(enum.StrEnum):
    """Roles authorised to authenticate against the API.

    Mirrored by the Postgres `user_role` ENUM (Alembic 0002). Adding a
    value requires a migration that ALTERs that type. Subclassing
    `enum.StrEnum` gives runtime enforcement on assignment plus a single
    source of truth for the Pydantic transports landing in S02.4.

    The SQLAlchemy mapping lives in `models.py`
    (`mapped_column(Enum(UserRole, name="user_role",
    values_callable=_user_role_values))`); the `values_callable` there
    keeps the stored values (`"admin"`/`"member"`) aligned with the PG
    ENUM rather than the member *names*. A round-trip integration test
    pins that the mapping survives this enum living outside `models.py`.
    """

    ADMIN = "admin"
    MEMBER = "member"
