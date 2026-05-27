"""FastAPI dependency exposing the authenticated `User` (S02.4 / P02.4.3).

`get_current_user` is the canonical seam through which other modules
require authentication — re-exported via `backend.modules.auth.public`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings, get_settings
from backend.modules.auth.models import User
from backend.modules.auth.service.jwt import InvalidTokenError, verify_access_token
from backend.shared.db import get_db

# `auto_error=False` so we can raise our own 401 with a consistent body
# (Starlette's default would 403 the missing-header case).
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """Resolve the bearer access token to a live, non-disabled `User`.

    Raises `HTTPException(401)` for: missing/wrong scheme, malformed or
    expired token, unknown user, or user with `disabled_at` set. The
    distinct internal causes are not surfaced to the client.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401, detail="Missing or invalid Authorization header"
        )
    try:
        user_id = verify_access_token(credentials.credentials, settings=settings)
    except InvalidTokenError as exc:
        # InvalidTokenError catches ExpiredTokenError (subclass) too.
        raise HTTPException(
            status_code=401, detail="Invalid or expired access token"
        ) from exc
    user = await session.get(User, user_id)
    if user is None or user.disabled_at is not None:
        raise HTTPException(
            status_code=401, detail="User no longer exists or is disabled"
        )
    return user
