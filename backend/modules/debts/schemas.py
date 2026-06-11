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
from typing import cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.modules.debts.domain import SettlementType
from backend.modules.debts.models import Settlement, SettlementLine, ShareRequest
from backend.modules.debts.service.dashboard import (
    CounterpartyNet,
    DebtWithContext,
)
from backend.shared.text import IMPOSED_TEXT_ALLOWED

# Whitelist for `short_label`/`note`: ASCII printable (0x20–0x7E) + printable
# Latin-1 (0xA1–0xFF), minus SHY (U+00AD, a `Cf` format char). SINGLE source of
# truth in `backend.shared.text` (S13.4) — the sync write boundary
# (`sync.handlers.payloads`) MUST share the exact same set, otherwise a sync
# client could persist control/format chars this REST boundary rejects. Blocks
# *by construction*: control/format chars (Cc/Cf — BiDi overrides U+202E…,
# zero-width joiners, NBSP & every non-space `Zs`) and any non-Latin script (so
# Cyrillic/Greek homoglyphs cannot spoof a label). V1 limitation (assumed,
# mono-foyer FR): ASCII + Latin-1 only; anything else is a 422.
_LABEL_ALLOWED = IMPOSED_TEXT_ALLOWED


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

    debt_id: UUID
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
    remaining_cents: int  # solde restant (S10.3) — visible des deux parties

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


# ---------------------------------------------------------------------------
# Settlement schemas (S10.4) — the boundary of `POST/GET /settlements`.
# ---------------------------------------------------------------------------


class SettlementLineCreate(BaseModel):
    """One line of the `POST /settlements` body (≠ `domain.SettlementLineInput`).

    `amount_cents > 0` mirrors `ck_settlement_lines_amount_positive` (S10.1); the
    netting direction is carried by the Debt's orientation, never a sign here.
    """

    model_config = ConfigDict(extra="forbid")

    debt_id: UUID
    amount_cents: int = Field(gt=0)


class SettlementCreate(BaseModel):
    """Body of `POST /settlements`.

    `by_user_id`/`created_by` are NEVER in the body (D7, `extra="forbid"`): the
    caller is derived from the token at the route. `linked_transaction_id` is
    present iff `type != virtual` (`_link_matches_type`, mirror of the
    biconditional CHECK `ck_settlements_virtual_no_link`, S10.1).

    ⚠️ `note` is free text IMPOSED on the other party — same guarantees as
    `short_label` (server trim + control-char rejection via `_LABEL_ALLOWED`,
    which excludes `\\n`/`\\t` ⇒ the note is single-line, an INTENTIONAL
    anti-injection choice, S-n1). The client rendering MUST stay HTML-escaped
    (stored-XSS risk in a Capacitor WebView, review #22).
    """

    model_config = ConfigDict(extra="forbid")

    type: SettlementType  # closed Literal set (S10.2)
    linked_transaction_id: UUID | None = None
    settled_at: dt.date
    note: str | None = Field(default=None, max_length=500)
    lines: list[SettlementLineCreate] = Field(min_length=1)

    @field_validator("note")
    @classmethod
    def _clean_note(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:  # blank after trim → None (optional field)
            return None
        if any(c not in _LABEL_ALLOWED for c in v):  # whitelist (gabarit short_label)
            raise ValueError("note contains a disallowed character")
        return v

    @model_validator(mode="after")
    def _link_matches_type(self) -> SettlementCreate:
        # mirror of the biconditional CHECK ck_settlements_virtual_no_link.
        if (self.type == "virtual") != (self.linked_transaction_id is None):
            raise ValueError("linked_transaction_id must be set iff type != virtual")
        return self


class SettlementResponse(BaseModel):
    """API view of a created/listed settlement (meta, without the lines)."""

    id: UUID
    type: SettlementType
    linked_transaction_id: UUID | None
    settled_at: dt.date
    note: str | None
    created_by: UUID
    created_at: dt.datetime

    @classmethod
    def from_model(cls, s: Settlement) -> SettlementResponse:
        """Single serialisation path Settlement model → API."""
        return cls(
            id=s.id,
            type=cast(SettlementType, s.type),
            linked_transaction_id=s.linked_transaction_id,
            settled_at=s.settled_at,
            note=s.note,
            created_by=s.created_by,
            created_at=s.created_at,
        )


class SettlementListResponse(BaseModel):
    items: list[SettlementResponse]


class SettlementLineResponse(BaseModel):
    """A line of a settlement detail (the netting amount on one debt)."""

    debt_id: UUID
    amount_cents: int
    currency: str


class SettledDebtResponse(BaseModel):
    """A referenced `Debt` enriched with `remaining_cents`, MASKING already applied.

    Mirror of `DebtWithContext` (the masked DTO from `_project_debt`, S09.4):
    `source_transaction_id`/`account_id` are `null` when the caller is the debtor;
    `materialization_trace` is absent by construction. Built from the masked DTO
    so the single S09.4 masking path is reused (no parallel read).
    """

    debt_id: UUID
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
    remaining_cents: int

    @classmethod
    def from_context(cls, d: DebtWithContext) -> SettledDebtResponse:
        return cls(**{f.name: getattr(d, f.name) for f in fields(d)})


class SettlementDetailResponse(BaseModel):
    """Detail of a settlement: meta + (visible) lines + (masked) referenced debts.

    `lines` and `debts` are BOTH restricted to the debts the caller is party to
    (S-M1): a third party's debt id / context never appears.
    """

    id: UUID
    type: SettlementType
    linked_transaction_id: UUID | None
    settled_at: dt.date
    note: str | None
    created_by: UUID
    created_at: dt.datetime
    lines: list[SettlementLineResponse]
    debts: list[SettledDebtResponse]

    @classmethod
    def build(
        cls,
        settlement: Settlement,
        lines: list[SettlementLine],
        debts: list[DebtWithContext],
    ) -> SettlementDetailResponse:
        meta = SettlementResponse.from_model(settlement)
        return cls(
            id=meta.id,
            type=meta.type,
            linked_transaction_id=meta.linked_transaction_id,
            settled_at=meta.settled_at,
            note=meta.note,
            created_by=meta.created_by,
            created_at=meta.created_at,
            lines=[
                SettlementLineResponse(
                    debt_id=ln.debt_id, amount_cents=ln.amount_cents, currency=ln.currency
                )
                for ln in lines
            ],
            debts=[SettledDebtResponse.from_context(d) for d in debts],
        )
