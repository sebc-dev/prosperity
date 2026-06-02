"""Pydantic API schemas for the transactions HTTP transport (S07.5).

Deliberately **distinct** from the domain/ORM models (D7): the wire contract is
not the aggregate. `TransactionResponse.from_domain` is the SINGLE serialisation
path (mutation routes AND list), driven off `domain.Transaction` — what the
service hands back — so there is never a divergent ORM-vs-domain mapper. Amounts
are exposed RAW (`amount_cents: int` + `currency: str`); French formatting is a
UI responsibility (issue §Notes).

Server-derived identity is never in a request body: `created_by` comes from the
token (D6) and the route `account_id` is a path param (D5), so neither appears
on `TransactionCreate`. `extra="forbid"` turns a stray `created_by`/`account_id`
(or any frozen field on PATCH) into a 422 — a loud rejection, not a silent
no-op. `payee` / `share_request_id` are not settable via the V1 API (D9, §HS).

Length bounds (`_MAX_SPLITS`, `_MAX_TAGS`, item/`description` lengths) are
anti-DoS guards on persisted ARRAY/TEXT columns (C-SEC-2), mirrored on create
and PATCH.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from backend.modules.transactions.domain import (
    DebtGenerationOverride,
    TransactionState,
)
from backend.modules.transactions.domain import (
    Transaction as _DomainTx,
)

_CURRENCY_LEN = 3
# Anti-DoS bounds on persisted collections / text (C-SEC-2): a transaction body
# beyond these is a bug or abuse, rejected at the schema edge before any write.
_MAX_SPLITS = 100
_MAX_TAGS = 32
_MAX_TAG_LEN = 64
_MAX_DESC_LEN = 500

# Each `tags` item is length-bounded (the item, not just the cardinality).
Tag = Annotated[str, StringConstraints(max_length=_MAX_TAG_LEN)]


class SplitInput(BaseModel):
    """One leg of a create payload. `account_id` is household-validated at the
    route boundary (D5), not here — the schema only shapes the wire format."""

    model_config = ConfigDict(extra="forbid")
    account_id: UUID
    amount_cents: int
    currency: str = Field(min_length=_CURRENCY_LEN, max_length=_CURRENCY_LEN)
    category_id: UUID | None = None


class TransactionCreate(BaseModel):
    """`POST /accounts/{account_id}/transactions`.

    The route `account_id` (D5) and `created_by` (token, D6) are NOT in the body;
    `extra="forbid"` rejects either if slipped in (422, not a silent drop).
    `payee` is not settable in V1 (no service writer — §HS). `debt_generation_override`
    is a domain `Literal`, so an out-of-enum value is a 422 before the service.
    """

    model_config = ConfigDict(extra="forbid")
    date: dt.date | None = None
    splits: list[SplitInput] = Field(min_length=1, max_length=_MAX_SPLITS)
    category_id: UUID | None = None
    description: str | None = Field(default=None, max_length=_MAX_DESC_LEN)
    tags: list[Tag] = Field(default_factory=list, max_length=_MAX_TAGS)
    debt_generation_override: DebtGenerationOverride = "default"


class SplitResponse(BaseModel):
    """One split in `TransactionResponse`. Amounts raw (`amount_cents`+`currency`)."""

    account_id: UUID
    category_id: UUID | None
    amount_cents: int
    currency: str


class TransactionResponse(BaseModel):
    """Client view of a transaction. Never the domain aggregate directly (D7).

    `from_domain` is the single mapper from `domain.Transaction`. Does not expose
    `split.id` nor timestamps in V1 (absent from `domain.Transaction` — D8), nor
    `payee`/`share_request_id` (no V1 writer / lives in E09 — D9).
    """

    id: UUID
    account_id: UUID
    date: dt.date
    state: TransactionState
    created_by: UUID
    category_id: UUID | None
    description: str | None
    tags: list[str]
    debt_generation_override: DebtGenerationOverride
    splits: list[SplitResponse]

    @classmethod
    def from_domain(cls, tx: _DomainTx) -> TransactionResponse:
        """Single serialisation path domain → API (D7). Amounts exposed raw."""
        return cls(
            id=tx.id,
            account_id=tx.account_id,
            date=tx.date,
            state=tx.state,
            created_by=tx.created_by,
            category_id=tx.category_id,
            description=tx.description,
            tags=list(tx.tags),
            debt_generation_override=tx.debt_generation_override,
            splits=[
                SplitResponse(
                    account_id=s.account_id,
                    category_id=s.category_id,
                    amount_cents=s.amount.amount_cents,
                    currency=s.amount.currency,
                )
                for s in tx.splits
            ],
        )
