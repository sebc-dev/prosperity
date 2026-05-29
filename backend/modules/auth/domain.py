"""Pure domain values for the auth module (no SQLAlchemy dependency).

This module holds business-meaning types that are independent of the
persistence layer — the `UserRole` enum and the `AdminAction` audit
catalogue. Keeping them here (vs. `models.py`) means a consumer can
reason about roles or audit actions without importing the ORM stack, and
it gives RBAC primitives (`require_admin`, `require_member`) a
SQLAlchemy-free source of truth for the enum.

Internal to `modules.auth`: cross-module callers must reach `UserRole` /
`AdminAction` through `backend.modules.auth.public`. Import-linter
forbids reaching into `backend.modules.auth.domain` directly from peer
modules.
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


class AdminAction(enum.StrEnum):
    """Catalogue of auditable admin actions logged to `admin_audit_logs`.

    Unlike `UserRole` (backed by the Postgres `user_role` ENUM), the
    `admin_audit_logs.action` column is a plain `String`, not a PG enum.
    This asymmetry is deliberate: a new audit action is a frequent,
    low-risk event (E04 invitations, E05+ user lifecycle), so adding one
    must be a code change here — not an `ALTER TYPE` migration. This enum
    is the single source of truth; `log_admin_action` coerces its input
    through `AdminAction(...)` at runtime so an out-of-catalogue string is
    rejected at the call site rather than silently persisted.

    `TWOFA_RESET_VIA_DB` cannot be spelled as a leading-digit Python
    identifier, hence the explicit member name for the `"2fa_reset_via_db"`
    value (ADR 0013: TOTP reset is performed by manual SQL).
    """

    INVITE_SENT = "invite_sent"
    INVITE_REVOKED = "invite_revoked"
    INVITE_REGENERATED = "invite_regenerated"
    INVITE_ACCEPTED = "invite_accepted"
    USER_PROMOTED = "user_promoted"
    USER_DISABLED = "user_disabled"
    TWOFA_RESET_VIA_DB = "2fa_reset_via_db"
