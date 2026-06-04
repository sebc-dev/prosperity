"""Pydantic request/response schemas for the debts HTTP transport (S09.3).

`ShareRequestCreate` is the body of `POST /transactions/{tx_id}/share-requests`.
It carries ONLY `requested_from`, `ratio`, and `short_label` — `by_user_id` is
derived from the token at the route (D7), never the body (anti-usurpation;
`extra="forbid"` makes any `by_user_id`/`requested_by` smuggled in the body a
422).

`ratio` is validated at the boundary (`gt=0, le=1` → vérif vi as a 422); the
`DebtCalculator` (`debts.domain`) stays the ultimate fail-safe. `short_label` is
trimmed + bounded (≤ 100) + run through a **whitelist** (vérif vii) — see below.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import fields
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.modules.debts.models import ShareRequest
from backend.modules.debts.service.dashboard import (
    CounterpartyNet,
    DebtWithContext,
)

# Whitelist for `short_label`: ASCII printable (0x20–0x7E) + printable Latin-1
# (0xA1–0xFF), minus SHY (U+00AD, a `Cf` format char). Pattern adapted from
# `auth.schemas._DEVICE_LABEL_ALLOWED` (cited by the issue), EXTENDED to Latin-1
# so French accents pass. Blocks *by construction*: control/format chars (Cc/Cf
# — BiDi overrides U+202E…, zero-width joiners, NBSP & every non-space `Zs`) and
# any non-Latin script (so Cyrillic/Greek homoglyphs cannot spoof a label). V1
# limitation (assumed, mono-foyer FR): a label is ASCII + Latin-1 only; anything
# else is a 422 (NOT the silent drop of `sanitize_device_label`).
_LABEL_ALLOWED = frozenset(chr(c) for c in (*range(0x20, 0x7F), *range(0xA1, 0x100))) - {
    chr(0xAD)  # SHY (soft hyphen, a Cf format char)
}


class ShareRequestCreate(BaseModel):
    """Body of `POST /transactions/{tx_id}/share-requests`.

    `by_user_id` is NEVER in the body (D7): it is derived from the token at the
    route. ⚠️ `short_label` is free creditor text IMPOSED on the debtor — the
    client rendering MUST stay HTML-escaped (stored-XSS risk in a Capacitor
    WebView, review #22). The whitelist below blocks injection/spoofing vectors
    server-side but cannot guarantee a stored string's innocuousness on render.
    """

    model_config = ConfigDict(extra="forbid")

    requested_from: UUID
    ratio: Decimal = Field(gt=0, le=1)  # vérif (vi) → 422 at the boundary
    short_label: str = Field(min_length=1, max_length=100)

    @field_validator("short_label")
    @classmethod
    def _clean_label(cls, v: str) -> str:
        v = v.strip()
        if not v:  # blank after trim → 422
            raise ValueError("short_label must not be blank")
        if any(c not in _LABEL_ALLOWED for c in v):  # whitelist (review #144)
            raise ValueError("short_label contains a disallowed character")
        return v


class ShareRequestResponse(BaseModel):
    """Creditor's view of the created SR (NOT the `Debt` — debtor masking is S09.4).

    The creator (creditor) owns the source account, so echoing
    `source_transaction_id` here is fine — debtor-side masking is a *read*
    concern (S09.4), not this creation echo. `materialization_trace` and the
    `Debt` are deliberately absent (server-only / debtor-masked).
    """

    id: UUID
    source_transaction_id: UUID
    requested_from: UUID
    ratio: Decimal
    short_label: str
    created_at: dt.datetime

    @classmethod
    def from_model(cls, sr: ShareRequest) -> ShareRequestResponse:
        """Single serialisation path SR model → API."""
        return cls(
            id=sr.id,
            source_transaction_id=sr.source_transaction_id,
            requested_from=sr.requested_from,
            ratio=sr.ratio,
            short_label=sr.short_label,
            created_at=sr.created_at,
        )


# ---------------------------------------------------------------------------
# Dashboard read schemas (S09.4) — the allowlist at the HTTP boundary.
# ---------------------------------------------------------------------------


class DebtResponse(BaseModel):
    """Vue API d'une dette (miroir 1:1 de `DebtWithContext` — D7).

    `source_transaction_id`/`account_id` nullables : `null` quand masqués au
    débiteur. `materialization_trace` ABSENT (allowlist par construction). Le
    test de parité (`test_debts_schemas`) verrouille l'égalité des champs avec
    `DebtWithContext` : tout champ ajouté d'un seul côté casse le build.
    """

    from_user_id: UUID
    to_user_id: UUID
    amount_cents: int
    currency: str
    origin: str
    requested_by: UUID
    short_label: str | None
    category_id: UUID | None
    date: dt.date | None
    created_at: dt.datetime
    source_transaction_id: UUID | None
    account_id: UUID | None

    @classmethod
    def from_context(cls, d: DebtWithContext) -> DebtResponse:
        """Single serialisation path DTO → API, field-for-field (parité D7)."""
        return cls(**{f.name: getattr(d, f.name) for f in fields(d)})


class DebtListResponse(BaseModel):
    items: list[DebtResponse]


class CounterpartyNetResponse(BaseModel):
    """Net orienté par contrepartie pour le dashboard « mes dettes par contrepartie ».

    `net_amount` (centimes signés, libellé de l'issue #145) : positif = la
    contrepartie me doit net ; négatif = je lui dois net. Aucun champ source
    (l'agrégat en est structurellement dépourvu — non-fuite par construction).
    """

    user_id: UUID
    net_amount: int
    currency: str
    debts_count: int

    @classmethod
    def from_net(cls, n: CounterpartyNet) -> CounterpartyNetResponse:
        return cls(
            user_id=n.user_id,
            net_amount=n.net_amount_cents,
            currency=n.currency,
            debts_count=n.debts_count,
        )


class CounterpartyListResponse(BaseModel):
    items: list[CounterpartyNetResponse]
