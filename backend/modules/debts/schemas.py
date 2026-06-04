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
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.modules.debts.models import ShareRequest

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
