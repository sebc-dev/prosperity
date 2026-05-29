"""FastAPI dependency exposing the authenticated `User` (S02.4 / P02.4.3).

`get_current_user` is the canonical seam through which other modules
require authentication — re-exported via `backend.modules.auth.public`.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings, get_settings
from backend.modules.auth.domain import UserRole
from backend.modules.auth.models import User
from backend.modules.auth.service.jwt import (
    ExpiredTokenError,
    InvalidTokenError,
    verify_access_token,
)
from backend.shared.db import get_db
from backend.shared.http import client_ip_for

logger = logging.getLogger(__name__)

# `auto_error=False` so we can raise our own 401 with a consistent body
# (Starlette's default would 403 the missing-header case).
_bearer = HTTPBearer(auto_error=False)

# All authentication failures collapse to the exact same response: same
# status, same body, same headers. The distinct internal causes are
# preserved in server-side logs (with `reason=...`) but never surface to
# the client — otherwise a successfully forged JWT could be used to
# probe whether a user is merely disabled versus the token itself being
# invalid.
_UNAUTH_DETAIL = "Not authenticated"
_UNAUTH_HEADERS = {"WWW-Authenticate": "Bearer"}


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_UNAUTH_DETAIL,
        headers=_UNAUTH_HEADERS,
    )


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """Resolve the bearer access token to a live, non-disabled `User`.

    Raises `HTTPException(401)` with a uniform body for every rejection
    cause (missing/wrong scheme, malformed/expired token, unknown user,
    disabled user). Server-side logs carry a symbolic `reason` to
    distinguish them for ops without leaking to the client.
    """
    client_ip = client_ip_for(request, settings)

    if credentials is None or credentials.scheme.lower() != "bearer":
        logger.warning(
            "auth_rejected",
            extra={"reason": "missing_or_invalid_scheme", "client_ip": client_ip},
        )
        raise _unauthorized()
    try:
        user_id = verify_access_token(credentials.credentials, settings=settings)
    except ExpiredTokenError as exc:
        logger.info(
            "auth_rejected",
            extra={"reason": "expired_token", "client_ip": client_ip},
        )
        raise _unauthorized() from exc
    except InvalidTokenError as exc:
        logger.warning(
            "auth_rejected",
            extra={
                "reason": "invalid_token",
                "cause": type(exc).__name__,
                "client_ip": client_ip,
            },
        )
        raise _unauthorized() from exc
    user = await session.get(User, user_id)
    if user is None or user.disabled_at is not None:
        logger.warning(
            "auth_rejected",
            extra={
                "reason": "user_unknown_or_disabled",
                "user_id": str(user_id),
                "client_ip": client_ip,
            },
        )
        raise _unauthorized()
    return user


# Authorisation (RBAC) sits *above* authentication: by the time these
# run, `get_current_user` has already collapsed every anonymous/invalid/
# disabled case into a uniform 401. A 403 therefore means "you are a
# known, live user, but your role is not enough" — a distinct, safe
# signal (the caller already proved identity). The body is a constant
# `"Forbidden"`: it never names the required role, so an authenticated
# member cannot enumerate which endpoints are admin-gated by reading the
# error text. The symbolic `reason` is server-side only.
_FORBIDDEN_DETAIL = "Forbidden"

# Both guards are explicit allow-lists, not deny-by-negation: a role
# outside the set is rejected fail-closed (403), so adding a third role
# to the enum never silently grants access without a deliberate decision
# here.
_ADMIN_ROLES = frozenset({UserRole.ADMIN})
_MEMBER_ROLES = frozenset({UserRole.ADMIN, UserRole.MEMBER})


def _forbidden() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN_DETAIL)


def _require_role(
    user: User,
    request: Request,
    settings: Settings,
    allowed: frozenset[UserRole],
    reason: str,
) -> User:
    """Return `user` if its role is in `allowed`, else raise 403.

    The single home for the rejection shape so every guard stays
    consistent: the same constant `"Forbidden"` body, and an
    `rbac_rejected` log that carries `user_id` + `client_ip` but
    **never** the email nor the required role (anti-enumeration —
    mirroring the 401 path). `client_ip_for` is only computed on the
    rejection branch.
    """
    if user.role not in allowed:
        logger.warning(
            "rbac_rejected",
            extra={
                "reason": reason,
                "user_id": str(user.id),
                "client_ip": client_ip_for(request, settings),
            },
        )
        raise _forbidden()
    return user


async def require_admin(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """Authenticated `User` whose role is `ADMIN`, else `HTTPException(403)`.

    Anonymous / invalid-token / disabled-user cases never reach here —
    `get_current_user` raised 401 first. The only failure mode left is
    an authenticated non-admin, which is a 403.
    """
    return _require_role(user, request, settings, _ADMIN_ROLES, "role_not_admin")


async def require_member(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """Authenticated `User` whose role grants member-level access.

    `ADMIN` and `MEMBER` both pass — admins are a superset of members.
    """
    return _require_role(user, request, settings, _MEMBER_ROLES, "role_not_member")
