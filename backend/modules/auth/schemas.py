"""Pydantic request/response schemas for the auth HTTP transport (S02.4)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr

DEVICE_LABEL_MAX = 120

# Whitelist: ASCII printable only (0x20–0x7E). Blocks BiDi controls
# (e.g. U+202E LEFT-TO-RIGHT OVERRIDE), zero-width joiners, Cyrillic
# homoglyphs, etc. Stored as `RefreshToken.device_label` and never
# rendered to a client without HTML-escaping (the future "devices"
# screen will be admin-only and HTML-escape on render).
_DEVICE_LABEL_ALLOWED = frozenset(chr(c) for c in range(0x20, 0x7F))


def sanitize_device_label(raw: str | None) -> str | None:
    """Sanitize the User-Agent header for storage as `device_label`.

    Drops every character outside ASCII printable, trims surrounding
    whitespace, and caps to `DEVICE_LABEL_MAX` chars. Returns `None`
    when the input is empty or wholly stripped.

    Callers must NEVER render the result back to clients without
    HTML-escaping. This function blocks log-injection / homoglyph
    vectors only, not XSS.
    """
    if not raw:
        return None
    cleaned = "".join(c for c in raw if c in _DEVICE_LABEL_ALLOWED).strip()
    return cleaned[:DEVICE_LABEL_MAX] or None


class LoginRequest(BaseModel):
    # `EmailStr` accepts the 422-on-malformed vs 401-on-unknown channel,
    # bounded by the login rate-limit (S02.5). Pydantic v2 forces
    # `check_deliverability=False` on every call to `email_validator`, so no
    # DNS timing oracle leaks domain existence — pinned in `test_auth_schemas`.
    email: EmailStr
    # `SecretStr` keeps the password out of `repr()` (debug, Sentry tags,
    # validator traces, structlog bindings). `max_length=128` matches
    # OWASP ASVS V2.1.3 and caps the Argon2id verify CPU cost per request.
    password: SecretStr = Field(min_length=1, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"


class InvitationCreateRequest(BaseModel):
    # `EmailStr` mirrors `LoginRequest` / `SetupRequest`; the service
    # re-normalises (strip + lower) inside `create()`, so the stored row
    # and the audit/response email always agree regardless of input casing.
    email: EmailStr


class InvitationResponse(BaseModel):
    # Admin view of a pending invitation. `token_hash` is deliberately
    # **not** a field: the omission is structural, so FastAPI filters it
    # out even when the whole ORM row is returned from `GET /invitations`
    # (acceptance criterion — never expose a token hash).
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    invited_at: datetime
    expires_at: datetime
    invited_by: uuid.UUID


class InvitationCreatedResponse(BaseModel):
    # Create / regenerate response: carries the raw token **once** plus a
    # ready-to-transmit accept link. Built explicitly from the service's
    # return value (not the ORM row), so `token_hash` can never leak here.
    id: uuid.UUID
    email: str
    expires_at: datetime
    token: str
    accept_url: str


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=512)
