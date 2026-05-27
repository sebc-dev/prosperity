"""Pydantic request/response schemas for the auth HTTP transport (S02.4)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field, SecretStr

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
    email: EmailStr
    # `SecretStr` keeps the password out of `repr()` (debug, Sentry tags,
    # validator traces, structlog bindings). `max_length=128` matches
    # OWASP ASVS V2.1.3 and caps the Argon2id verify CPU cost per request.
    password: SecretStr = Field(min_length=1, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=512)
