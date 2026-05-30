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


class AcceptInvitePreviewResponse(BaseModel):
    # `GET /accept-invite` — pre-fills the acceptance form. `expires_at`
    # lets the UI show "expires in N days". No token echo, no `id`
    # (server-only). The acceptance criterion bounds this body to
    # {email, expires_at}.
    email: str
    expires_at: datetime


class AcceptInviteRequest(BaseModel):
    # `POST /accept-invite`. `extra="ignore"` (the Pydantic default, pinned
    # here on purpose): a body carrying `role` or `email` is silently
    # dropped — the role is hardcoded `member` server-side and the email
    # comes from the invitation (anti-poisoning, ADR 0010). A 422 on
    # `role: admin` (which `extra="forbid"` would give) would itself tell an
    # attacker the field is inspected; `ignore` leaks no such signal.
    # Validation mirrors `SetupRequest` (S03.2).
    model_config = ConfigDict(extra="ignore")

    # Bounded like the GET query param: the real token is 43 chars
    # (`token_urlsafe(32)`); anything longer just fails the lookup → 410.
    token: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)
    # `SecretStr` keeps the password out of `repr()`; 12-128 matches
    # `SetupRequest` / OWASP ASVS V2.1.* and caps Argon2id verify CPU.
    password: SecretStr = Field(min_length=12, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=512)
