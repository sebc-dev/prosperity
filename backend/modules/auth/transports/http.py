"""HTTP transport for the auth module (story S02.4).

Exposes `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`.
Internal to `modules.auth`: cross-module callers go through
`modules.auth.public` (no transport symbols are re-exported there).
"""

from __future__ import annotations

import logging
from functools import cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pwdlib import PasswordHash
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings, get_settings
from backend.modules.auth.models import User
from backend.modules.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenPair,
    sanitize_device_label,
)
from backend.modules.auth.service.jwt import issue_access_token
from backend.modules.auth.service.refresh_tokens import (
    InvalidRefreshTokenError,
    hash_refresh_token,
)
from backend.modules.auth.service.refresh_tokens import issue as issue_refresh
from backend.modules.auth.service.refresh_tokens import revoke as revoke_refresh
from backend.modules.auth.service.refresh_tokens import rotate as rotate_refresh
from backend.shared.db import get_db

logger = logging.getLogger(__name__)

# Applied on responses that carry tokens (`/auth/login`, `/auth/refresh`).
# Prevents intermediary proxies (CDN, ALB, corp-proxy) or
# `fetch({cache: 'force-cache'})` from caching the access/refresh pair
# (OWASP ASVS V8.3.4).
_NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@cache
def _password_hasher() -> PasswordHash:
    """Lazy PasswordHash factory.

    `PasswordHash.recommended()` instantiates Argon2id (50-200ms);
    initialising at import time would slow every test boot.
    """
    return PasswordHash.recommended()


@cache
def _dummy_hash() -> str:
    """Pre-computed Argon2id hash used to equalise verify timing.

    Calling `verify("dummy", _dummy_hash())` when the supplied email
    doesn't resolve to a user prevents timing-based account
    enumeration: an attacker can't distinguish "user unknown" from
    "user exists, password wrong" by measuring response latency.
    """
    return _password_hasher().hash("dummy")


@router.post("/login", response_model=TokenPair, status_code=status.HTTP_200_OK)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenPair:
    """Authenticate by email + password; return an access + refresh pair.

    Case-insensitive on the email lookup (uses the functional
    `lower(email)` index on `users`). 401 is returned uniformly for
    unknown user, wrong password, and disabled account so the client
    cannot enumerate which case applies.
    """
    # TODO(S02.5): rate-limit by client IP / email.
    response.headers.update(_NO_STORE_HEADERS)

    user = (
        await session.execute(select(User).where(func.lower(User.email) == body.email.lower()))
    ).scalar_one_or_none()
    password = body.password.get_secret_value()
    client_ip = request.client.host if request.client else None

    if user is None or user.disabled_at is not None:
        # Run verify() against the dummy hash so the disabled / unknown
        # case takes the same Argon2id wall-clock time as the wrong-
        # password case.
        _password_hasher().verify("dummy", _dummy_hash())
        logger.warning(
            "login_failed",
            extra={"reason": "user_unknown_or_disabled", "client_ip": client_ip},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not _password_hasher().verify(password, user.password_hash):
        logger.warning(
            "login_failed",
            extra={
                "reason": "bad_password",
                "user_id": str(user.id),
                "client_ip": client_ip,
            },
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    device_label = sanitize_device_label(request.headers.get("user-agent"))
    access = issue_access_token(user.id, settings=settings)
    refresh = await issue_refresh(session, user.id, settings=settings, device_label=device_label)
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenPair, status_code=status.HTTP_200_OK)
async def refresh(
    body: RefreshRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenPair:
    """Rotate a refresh token: revoke the presented one, issue a new pair.

    All refresh-token failure modes (unknown, expired, revoked) collapse
    to a single 401 with a generic body — the distinct exception types
    are preserved for server-side logs but never leak to the client.
    Replay of an already-revoked token triggers family-wide invalidation
    inside `rotate()` (see service docstring).
    """
    # TODO(S02.5): rate-limit by client IP / refresh-token hash prefix.
    response.headers.update(_NO_STORE_HEADERS)
    try:
        user_id, new_refresh = await rotate_refresh(session, body.refresh_token, settings=settings)
    except InvalidRefreshTokenError as exc:
        # Parent class catches Invalid + Expired + Revoked → uniform 401.
        logger.warning(
            "refresh_failed",
            extra={
                "reason": type(exc).__name__,
                "client_ip": request.client.host if request.client else None,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from exc

    access = issue_access_token(user_id, settings=settings)
    return TokenPair(access_token=access, refresh_token=new_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    """Revoke the refresh token. Idempotent: 204 regardless of state.

    Returning 204 even when the hash is unknown (already cleaned up,
    forged value, etc.) keeps the response shape uniform — no
    differential signal that would let a client probe for valid tokens.
    """
    # TODO(S02.5): rate-limit by client IP — currently anyone can spam
    # the route with guessed refresh tokens.
    token_hash = hash_refresh_token(body.refresh_token, settings=settings)
    await revoke_refresh(session, token_hash)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
