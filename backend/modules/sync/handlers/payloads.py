"""Schémas Pydantic de payload par-table — étape 3 d'ADR 0014 (validation), livrée
ici (S13.4 / D-L).

Chaque sous-handler valide `Mutation.payload` contre le schéma de SA table EN TÊTE
(`Model.model_validate(mutation.payload)`), AVANT toute coercition ou appel service.
`extra="forbid"` partout → un champ parasite (y compris un champ **server-derived**
comme `by_user_id`/`created_by`/`owner_id`/`user_id`, jamais lu du payload) est un
rejet bruyant, pas un drop silencieux ; un client conforme ne les envoie pas. Les
**listes** (`members`/`lines`/`contributor_ids`) sont bornées (anti-DoS, C-SEC-2).

Ces schémas ne portent AUCUNE logique métier : ils shapent + bornent. La validation
domaine (Σ ratios == 1, cycles de catégorie, équilibre d'une transaction, …) reste
dans les services métier (appelés via `*.public`). La transformation
`ValidationError → WriteResult.error=validation_error` et l'isolation par-mutation
sont S13.6 — ici un payload malformé **lève** (D-I, propagation).
"""

from __future__ import annotations

from datetime import date as _date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from backend.modules.accounts.public import AccountType, MemberShare
from backend.modules.budget.public import PeriodKind, Scope
from backend.modules.debts.public import SettlementLineInput, SettlementType
from backend.shared.currency import Currency
from backend.shared.text import clean_imposed_text, clean_optional_imposed_text

# Bornes alignées sur les schémas REST des modules métier (source unique de
# vérité côté boundary) : longueurs/cardinalités ET validateurs de valeur/format
# (plage `ratio`, montants positifs, whitelist anti-injection des textes imposés)
# — un payload sync n'a pas de raison d'être plus permissif que HTTP.
_NAME_MIN, _NAME_MAX = 1, 120
_ICON_MAX = 64
_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"
_DESC_MAX = 500
_NOTE_MAX = 500
_LABEL_MAX = 100
_TAG_MAX_LEN = 64
_MAX_TAGS = 32
_MAX_SHARED_MEMBERS = 20  # gabarit `accounts.schemas` (Σ == 1 reste règle service)
_MAX_CONTRIBUTORS = 50
_MAX_SETTLEMENT_LINES = 100
# Quote-part : miroir de la colonne `Numeric(5, 4)` (gabarit `accounts.schemas`).
_RATIO_MAX_DIGITS, _RATIO_DECIMALS = 5, 4

_Name = Annotated[str, StringConstraints(min_length=_NAME_MIN, max_length=_NAME_MAX)]
_Tag = Annotated[str, StringConstraints(max_length=_TAG_MAX_LEN)]


# ── transactions ──────────────────────────────────────────────────────────────
class TransactionInsertPayload(BaseModel):
    """`transactions/insert` → `create_draft`. `by_user_id` server-derived (absent)."""

    model_config = ConfigDict(extra="forbid")
    account_id: UUID
    date: _date | None = None


class TransactionUpdatePayload(BaseModel):
    """`transactions/update` → transition (`state` seul, D-K) XOR édition de champs.

    Le schéma VERROUILLE l'ambiguïté multi-colonnes (review archi Majeur) : `state`
    et un champ éditable ne peuvent PAS coexister (sinon perte silencieuse d'une
    édition co-présente, ou divergence d'ADR 0001). L'allowlist d'édition est
    FERMÉE (`category_id`/`description`/`tags`) — tout autre champ → `extra="forbid"`.
    """

    model_config = ConfigDict(extra="forbid")
    id: UUID
    state: Literal["planned", "confirmed", "void"] | None = None
    category_id: UUID | None = None
    description: str | None = Field(default=None, max_length=_DESC_MAX)
    tags: list[_Tag] | None = Field(default=None, max_length=_MAX_TAGS)

    _EDITABLE = ("category_id", "description", "tags")

    @model_validator(mode="after")
    def _state_xor_fields(self) -> TransactionUpdatePayload:
        if self.state is not None and self.model_fields_set & set(self._EDITABLE):
            msg = "`state` cannot be mutated together with editable fields"
            raise ValueError(msg)
        return self

    def editable_fields(self) -> dict[str, object]:
        """Champs éditables RÉELLEMENT fournis (partial, gabarit `exclude_unset`)."""
        return {k: getattr(self, k) for k in self._EDITABLE if k in self.model_fields_set}


class TransactionDeletePayload(BaseModel):
    """`transactions/delete` → `void(reason="client_delete")`."""

    model_config = ConfigDict(extra="forbid")
    id: UUID


# ── splits (co-localisés dans le handler transactions, D-C) ─────────────────────
class SplitInsertPayload(BaseModel):
    """`splits/insert` → `add_split`. Porte `transaction_id` (D-D) ; `leg_role` est
    dérivé context-sensitive de `category_id` par le service (l'appelant ne le passe pas)."""

    model_config = ConfigDict(extra="forbid")
    transaction_id: UUID
    account_id: UUID
    amount_cents: int
    currency: Currency
    category_id: UUID | None = None


class SplitDeletePayload(BaseModel):
    """`splits/delete` → `remove_split`. `transaction_id` (D-D) + `id` du split."""

    model_config = ConfigDict(extra="forbid")
    transaction_id: UUID
    id: UUID


# ── accounts ────────────────────────────────────────────────────────────────
class AccountInsertPersonalPayload(BaseModel):
    """`accounts/insert` personnel → `create_personal`. `owner_id` forcé `user.id` (absent)."""

    model_config = ConfigDict(extra="forbid")
    name: _Name
    type: AccountType
    currency: Currency


class MemberSharePayload(BaseModel):
    """Une quote-part de compte commun (wire). Mappée 1:1 sur `accounts.MemberShare`.

    `ratio` borné `0 < r < 1` + précision `Numeric(5, 4)` (gabarit
    `accounts.schemas.AccountMemberInput`) : la borne par-élément + précision est
    le boundary (Σ == 1 reste règle service) ; sans elle, un `Decimal` à précision
    excessive lèverait tard en DB plutôt qu'un rejet propre."""

    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    ratio: Decimal = Field(gt=0, lt=1, max_digits=_RATIO_MAX_DIGITS, decimal_places=_RATIO_DECIMALS)


class AccountInsertSharedPayload(BaseModel):
    """`accounts/insert` commun → `create_shared`. Discriminé par présence de `members`.

    Σ ratios == 1 + ≥ 2 membres restent des règles du service (`AccountValidator`) ;
    ici on borne seulement la cardinalité (anti-DoS)."""

    model_config = ConfigDict(extra="forbid")
    members: list[MemberSharePayload] = Field(min_length=1, max_length=_MAX_SHARED_MEMBERS)
    name: _Name
    type: AccountType
    currency: Currency

    def to_member_shares(self) -> list[MemberShare]:
        return [MemberShare(user_id=m.user_id, ratio=m.ratio) for m in self.members]


class AccountUpdatePayload(BaseModel):
    """`accounts/update` → `rename`. `currency`/`type` gelés à la création (absents)."""

    model_config = ConfigDict(extra="forbid")
    id: UUID
    name: _Name


class AccountDeletePayload(BaseModel):
    """`accounts/delete` → `archive`."""

    model_config = ConfigDict(extra="forbid")
    id: UUID


# ── categories (module budget, delta D5) ──────────────────────────────────────
class CategoryInsertPayload(BaseModel):
    """`categories/insert` → `create_category`."""

    model_config = ConfigDict(extra="forbid")
    name: _Name
    color: str | None = Field(default=None, pattern=_COLOR_PATTERN)
    icon: str | None = Field(default=None, max_length=_ICON_MAX)
    parent_id: UUID | None = None


class CategoryUpdatePayload(BaseModel):
    """`categories/update` → `move_category` (si `parent_id` fourni) sinon
    `update_category(fields allowlistés)`. L'allowlist `{name,color,icon}` est FERMÉE :
    aucun `parent_id`/`archived_at`/`household_id` ne peut atteindre un `setattr` aveugle."""

    model_config = ConfigDict(extra="forbid")
    id: UUID
    parent_id: UUID | None = None
    name: _Name | None = None
    color: str | None = Field(default=None, pattern=_COLOR_PATTERN)
    icon: str | None = Field(default=None, max_length=_ICON_MAX)

    _EDITABLE = ("name", "color", "icon")

    def has_parent_change(self) -> bool:
        """Vrai ssi le client a FOURNI `parent_id` (re-parentage, `None` = vers la racine)."""
        return "parent_id" in self.model_fields_set

    def editable_fields(self) -> dict[str, object]:
        return {k: getattr(self, k) for k in self._EDITABLE if k in self.model_fields_set}


class CategoryDeletePayload(BaseModel):
    """`categories/delete` → `archive_category`."""

    model_config = ConfigDict(extra="forbid")
    id: UUID


# ── budgets (module budget) ───────────────────────────────────────────────────
class BudgetInsertPayload(BaseModel):
    """`budgets/insert` → `create_budget`. `created_by` forcé `user.id` (absent) ;
    `currency` dérivée du foyer côté service (absente)."""

    model_config = ConfigDict(extra="forbid")
    category_id: UUID
    period_kind: PeriodKind
    period_start: _date
    amount_cents: int = Field(gt=0)
    scope: Scope
    carry_over_remainder: bool = False
    contributor_ids: list[UUID] = Field(min_length=1, max_length=_MAX_CONTRIBUTORS)


class BudgetUpdatePayload(BaseModel):
    """`budgets/update` → `update_budget`. Allowlist FERMÉE `{amount_cents,
    carry_over_remainder}` ; `user_id` forcé (absent). `contributor_ids` remplace le set."""

    model_config = ConfigDict(extra="forbid")
    id: UUID
    amount_cents: int | None = Field(default=None, gt=0)
    carry_over_remainder: bool | None = None
    contributor_ids: list[UUID] | None = Field(
        default=None, min_length=1, max_length=_MAX_CONTRIBUTORS
    )

    _EDITABLE = ("amount_cents", "carry_over_remainder")

    def editable_fields(self) -> dict[str, object]:
        return {k: getattr(self, k) for k in self._EDITABLE if k in self.model_fields_set}


class BudgetDeletePayload(BaseModel):
    """`budgets/delete` → `archive_budget`."""

    model_config = ConfigDict(extra="forbid")
    id: UUID


# ── settlements (debts, delta D6 — seuls writes debts autorisés) ────────────────
class SettlementLinePayload(BaseModel):
    """Une ligne d'apurement (wire). Montant POSITIF ; le sens est porté par
    l'orientation de la `Debt` (validateur service). Mappée sur `SettlementLineInput`."""

    model_config = ConfigDict(extra="forbid")
    debt_id: UUID
    amount_cents: int = Field(gt=0)  # le sens est porté par l'orientation de la Debt


class SettlementInsertPayload(BaseModel):
    """`settlements/insert` → `create_settlement`. `by_user_id` forcé (absent).

    ⚠️ `note` est du texte libre IMPOSÉ à l'autre partie : trim + rejet des
    caractères de contrôle via la whitelist partagée (`shared.text`, gabarit
    `debts.schemas.SettlementCreate._clean_note`) — single-line, anti-injection
    (stored-XSS en WebView, review #22). La frontière sync ne doit PAS être plus
    laxiste que HTTP."""

    model_config = ConfigDict(extra="forbid")
    settlement_type: SettlementType
    linked_transaction_id: UUID | None = None
    settled_at: _date
    note: str | None = Field(default=None, max_length=_NOTE_MAX)
    lines: list[SettlementLinePayload] = Field(min_length=1, max_length=_MAX_SETTLEMENT_LINES)

    @field_validator("note")
    @classmethod
    def _clean_note(cls, v: str | None) -> str | None:
        return clean_optional_imposed_text(v, field="note")

    def to_line_inputs(self) -> list[SettlementLineInput]:
        return [
            SettlementLineInput(debt_id=ln.debt_id, amount_cents=ln.amount_cents)
            for ln in self.lines
        ]


# ── share_requests (debts) ────────────────────────────────────────────────────
class ShareRequestInsertPayload(BaseModel):
    """`share_requests/insert` → `create_share_request`. `by_user_id` forcé (absent) ;
    `requested_from` est une CIBLE légitime au payload (validée « membre actif » par le service).

    `ratio` borné `0 < r ≤ 1` + précision `Numeric(5, 4)` (gabarit
    `debts.schemas.ShareRequestCreate` ; `RatioOutOfBoundsError` reste le fail-safe
    domaine). `short_label` est du texte libre IMPOSÉ au débiteur : trim + whitelist
    anti-contrôle (`shared.text`, single-line, anti-injection / stored-XSS, #22/#144)."""

    model_config = ConfigDict(extra="forbid")
    transaction_id: UUID
    requested_from: UUID
    ratio: Decimal = Field(gt=0, le=1, max_digits=_RATIO_MAX_DIGITS, decimal_places=_RATIO_DECIMALS)
    short_label: str = Field(min_length=1, max_length=_LABEL_MAX)

    @field_validator("short_label")
    @classmethod
    def _clean_short_label(cls, v: str) -> str:
        return clean_imposed_text(v, field="short_label")


class ShareRequestDeletePayload(BaseModel):
    """`share_requests/delete` → `revoke_share_request`."""

    model_config = ConfigDict(extra="forbid")
    id: UUID
