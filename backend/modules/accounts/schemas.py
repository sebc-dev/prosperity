"""Pydantic request schemas for the accounts HTTP transport (S03.2).

`SetupRequest` is the four-field bootstrap form posted to `POST /setup`
on a fresh deployment. The response uses `TokenPair` from
`auth.schemas` (re-exported via `auth.public`) — the new admin is
auto-logged-in inside the same DB transaction that creates the row.
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, SecretStr

# Stricter than `LoginRequest.password` (min_length=1) by design: the
# first admin is the root of trust for the whole deployment, so we
# refuse trivially-brute-forceable values up front (OWASP ASVS V2.1.1
# admin floor). `LoginRequest` keeps min_length=1 to authenticate
# legacy / `INITIAL_ADMIN_*`-seeded accounts (S03.3) that may predate
# the floor; `/setup` runs on an empty DB and can afford strict input.
_PASSWORD_MIN_LENGTH = 12
_PASSWORD_MAX_LENGTH = 128


class SetupRequest(BaseModel):
    """Bootstrap form posted once per deployment to `POST /setup`.

    `display_name` and `household_name` are explicit (rather than
    derived from `email.split("@")[0]` and a default) because they are
    used everywhere downstream — audit logs, RBAC UI, settings page —
    and the cost of asking is nil (single-use form on an empty DB).
    """

    email: EmailStr
    password: SecretStr = Field(
        min_length=_PASSWORD_MIN_LENGTH,
        max_length=_PASSWORD_MAX_LENGTH,
    )
    display_name: str = Field(min_length=1, max_length=120)
    household_name: str = Field(min_length=1, max_length=120)
