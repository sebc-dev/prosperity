"""Pydantic request schemas for the accounts HTTP transport (S03.2, S05.3).

`SetupRequest` is the four-field bootstrap form posted to `POST /setup`
on a fresh deployment. The response uses `TokenPair` from
`auth.schemas` (re-exported via `auth.public`) — the new admin is
auto-logged-in inside the same DB transaction that creates the row.

The account I/O schemas (S05.3) drive the `/accounts` CRUD: two distinct
create bodies (`AccountCreatePersonal` / `AccountCreateShared`, no Pydantic
polymorphism — D1), a `name`-only `AccountUpdate` (currency/type frozen — D6),
and a flat `AccountResponse` (members exposed in S05.4 — D9).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr

from backend.modules.accounts.domain import AccountType

# Stricter than `LoginRequest.password` (min_length=1) by design: the
# first admin is the root of trust for the whole deployment, so we
# refuse trivially-brute-forceable values up front (OWASP ASVS V2.1.1
# admin floor). `LoginRequest` keeps min_length=1 to authenticate
# legacy / `INITIAL_ADMIN_*`-seeded accounts (S03.3) that may predate
# the floor; `/setup` runs on an empty DB and can afford strict input.
_PASSWORD_MIN_LENGTH = 12
_PASSWORD_MAX_LENGTH = 128

# Matches the `String(254)` column on `User.email` so an oversized body
# is rejected at the schema boundary, before Argon2id runs on the
# password — closes a CPU-DoS vector during the unauth `/setup` window.
_EMAIL_MAX_LENGTH = 254


class SetupRequest(BaseModel):
    """Bootstrap form posted once per deployment to `POST /setup`.

    `display_name` and `household_name` are explicit (rather than
    derived from `email.split("@")[0]` and a default) because they are
    used everywhere downstream — audit logs, RBAC UI, settings page —
    and the cost of asking is nil (single-use form on an empty DB).
    """

    email: EmailStr = Field(max_length=_EMAIL_MAX_LENGTH)
    password: SecretStr = Field(
        min_length=_PASSWORD_MIN_LENGTH,
        max_length=_PASSWORD_MAX_LENGTH,
    )
    display_name: str = Field(min_length=1, max_length=120)
    household_name: str = Field(min_length=1, max_length=120)


# --- Account I/O schemas (S05.3) --------------------------------------------

# `name` length mirrors `Account.name` = `String(120)`; min 1 forbids the
# empty label. `currency` is fixed-length ISO 4217 — the "== household base"
# rule itself lives in the domain `AccountValidator`, not in the schema, so
# the column stays multi-currency-ready (ADR 0008).
_NAME_MIN, _NAME_MAX = 1, 120
_CURRENCY_LEN = 3
# Mirror of the `Numeric(5, 4)` column on `AccountMember.default_share_ratio`.
_RATIO_MAX_DIGITS, _RATIO_DECIMALS = 5, 4
# Upper bound on a shared account's members (fail-fast before any INSERT —
# C-SEC-2): a household is small, so a body beyond this is a bug or abuse.
_SHARED_MEMBERS_MIN, _SHARED_MEMBERS_MAX = 2, 20


class AccountCreatePersonal(BaseModel):
    """`POST /accounts/personal`. No `owner_id` — derived from `get_current_user`.

    The owner is always the authenticated caller (D3); a stray `owner_id` in
    the body is silently dropped (Pydantic's default `extra="ignore"`), so the
    schema cannot be used to create an account on someone else's behalf.
    """

    name: str = Field(min_length=_NAME_MIN, max_length=_NAME_MAX)
    type: AccountType
    currency: str = Field(min_length=_CURRENCY_LEN, max_length=_CURRENCY_LEN)


class AccountMemberInput(BaseModel):
    """A prospective member of a shared account: a user + their quote-part.

    `default_share_ratio` is bounded `0 < r < 1` at the schema edge; the
    pure `AccountValidator` (Σ == 1, strictly positive, no duplicate) is the
    authoritative backstop (D8), so these bounds are belt-and-braces.
    """

    user_id: UUID
    default_share_ratio: Decimal = Field(
        gt=0, lt=1, max_digits=_RATIO_MAX_DIGITS, decimal_places=_RATIO_DECIMALS
    )


class AccountCreateShared(BaseModel):
    """`POST /accounts/shared`. ≥ 2 members (≤ 20, C-SEC-2 anti-DoS bound).

    The cardinality floor is also enforced by `TooFewMembersError` in the
    domain; the schema bound just rejects an obviously-malformed body before
    it reaches the service.
    """

    name: str = Field(min_length=_NAME_MIN, max_length=_NAME_MAX)
    type: AccountType
    currency: str = Field(min_length=_CURRENCY_LEN, max_length=_CURRENCY_LEN)
    members: list[AccountMemberInput] = Field(
        min_length=_SHARED_MEMBERS_MIN, max_length=_SHARED_MEMBERS_MAX
    )


class AccountResponse(BaseModel):
    """Flat account view (D9). The members list is exposed in S05.4.

    `from_attributes=True` lets FastAPI serialise the ORM `Account` directly;
    every field is a scalar loaded at flush, so no async lazy-load fires at
    serialisation time (`Account` maps no relationship). `archived_at` is
    omitted: an accessible account is never archived.
    """

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    type: AccountType
    currency: str
    owner_id: UUID | None
    created_at: datetime
