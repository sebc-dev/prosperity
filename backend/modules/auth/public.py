"""Public surface of the auth module — re-exports for cross-module use.

This module is the only one in `backend.modules.auth` that other modules may
import from. The import-linter contract "Only public surface importable
cross-module" forbids any cross-module import that reaches into
`backend.modules.auth.service`, `.models`, `.domain`, etc.
"""

from __future__ import annotations

from backend.modules.auth.service.jwt import (
    ExpiredTokenError,
    InvalidTokenError,
    issue_access_token,
    verify_access_token,
)

__all__ = [
    "ExpiredTokenError",
    "InvalidTokenError",
    "issue_access_token",
    "verify_access_token",
]
