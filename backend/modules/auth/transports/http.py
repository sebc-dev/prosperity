"""HTTP transport for the auth module (story S02.4).

Exposes `POST /auth/login`. Internal to `modules.auth`: cross-module
callers go through `modules.auth.public` (no transport symbols are
re-exported there). `/auth/refresh` and `/auth/logout` land in P02.4.2.
"""

from __future__ import annotations

from functools import cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pwdlib import PasswordHash
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings, get_settings
from backend.modules.auth.models import User
from backend.modules.auth.schemas import (
    LoginRequest,
    TokenPair,
    sanitize_device_label,
)
from backend.modules.auth.service.jwt import issue_access_token
from backend.modules.auth.service.refresh_tokens import issue as issue_refresh
from backend.shared.db import get_db

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


@router.post("/login", response_model=TokenPair, status_code=200)
async def login(
    body: LoginRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenPair:
    """Authenticate by email + password; return an access + refresh pair.

    Case-insensitive on the email lookup (uses the functional
    `lower(email)` index on `users`). 401 is returned uniformly for
    unknown user, wrong password, and disabled account so the client
    cannot enumerate which case applies.
    """
    user = (
        await session.execute(
            select(User).where(func.lower(User.email) == body.email.lower())
        )
    ).scalar_one_or_none()

    if user is None or user.disabled_at is not None:
        # Run verify() against the dummy hash so the disabled / unknown
        # case takes the same Argon2id wall-clock time as the wrong-
        # password case.
        _password_hasher().verify("dummy", _dummy_hash())
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not _password_hasher().verify(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    device_label = sanitize_device_label(request.headers.get("user-agent"))
    access = issue_access_token(user.id, settings=settings)
    refresh = await issue_refresh(
        session, user.id, settings=settings, device_label=device_label
    )
    return TokenPair(access_token=access, refresh_token=refresh)
