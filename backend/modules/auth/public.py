"""Public surface of the auth module — re-exports for cross-module use.

This module is the only one in `backend.modules.auth` that other modules
may import from. The import-linter contract "Only public surface
importable cross-module" forbids any cross-module import that reaches
into `backend.modules.auth.service`, `.models`, `.transports`, etc.

The current consumers cross-module are:
- `accounts.service.setup` — needs `create_user`, `create_user_with_hash`,
  `any_user_exists`, `UserRole` for the `/setup` bootstrap flow (S03.2)
  and the env-var startup hook (S03.3).
- `accounts.transports.http` — needs `issue_access_token`,
  `issue_refresh_token`, `TokenPair`, `sanitize_device_label` for
  auto-login at the end of `/setup` (S03.2).
- generic FastAPI dependencies in any module — `get_current_user`,
  which itself returns `User`, plus the RBAC guards `require_admin` /
  `require_member` (S04.1) layered on top of it. They live in
  `transports.dependencies` (not `shared/`) because they `Depends`
  on `get_current_user`, and re-export here keeps the cross-module
  surface uniform.
- admin-action callers (E04 invitations/promotions, E05+ user
  lifecycle) — `log_admin_action` writes the server-only audit trail and
  `AdminAction` is its action catalogue (S04.2), plus the errors it can
  raise at the call site (`UnknownAuditUserError`,
  `ForbiddenAuditMetadataError`). The `AdminAuditLog` model stays
  intra-auth: the audit row is only ever written through the helper,
  never constructed by peers.

`RefreshToken` and the shared `password_hasher` factory deliberately
stay intra-auth: hashing is encapsulated by `create_user` and
refresh-token row construction by `issue_refresh_token`.
"""

from __future__ import annotations

from backend.modules.auth.domain import AdminAction
from backend.modules.auth.models import User, UserRole
from backend.modules.auth.schemas import TokenPair, sanitize_device_label
from backend.modules.auth.service.audit import (
    ForbiddenAuditMetadataError,
    UnknownAuditUserError,
    log_admin_action,
)
from backend.modules.auth.service.jwt import (
    ExpiredTokenError,
    InvalidTokenError,
    issue_access_token,
    verify_access_token,
)
from backend.modules.auth.service.refresh_tokens import issue as issue_refresh_token
from backend.modules.auth.service.users import (
    any_user_exists,
    create_user,
    create_user_with_hash,
)
from backend.modules.auth.transports.dependencies import (
    get_current_user,
    require_admin,
    require_member,
)

__all__ = [
    "AdminAction",
    "ExpiredTokenError",
    "ForbiddenAuditMetadataError",
    "InvalidTokenError",
    "TokenPair",
    "UnknownAuditUserError",
    "User",
    "UserRole",
    "any_user_exists",
    "create_user",
    "create_user_with_hash",
    "get_current_user",
    "issue_access_token",
    "issue_refresh_token",
    "log_admin_action",
    "require_admin",
    "require_member",
    "sanitize_device_label",
    "verify_access_token",
]
