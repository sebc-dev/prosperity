"""Pydantic I/O schemas for the budget HTTP transport (S06.3 categories, S08.4 budgets).

Drive the `/categories` and `/budgets` CRUD. `extra="forbid"` on every request
body turns a client surprise into a loud 422 rather than a silent no-op:

* `CategoryCreate` rejects a client-supplied `id` (the id is strictly
  server-side, closing the S06.2 vacuous-guard finding #104) and any unknown
  field;
* `CategoryUpdate` rejects a `parent_id` — re-parenting has its own route
  (`PATCH /{id}/parent`), so a `parent_id` in the edit body is a contract
  error, not a move;
* `BudgetCreate` rejects a client `id` / `created_by` (server-derived from the
  token, D5) and `currency` (derived from the household, D6); `BudgetUpdate`
  rejects `scope` / `category_id` / `period_*` (frozen after creation, D7).

`color` is validated `^#[0-9A-Fa-f]{6}$` at the boundary (gabarit the accounts
`currency` rule) — the `categories.color` column carries no CHECK, keeping the
palette evolvable without a migration. `CategoryResponse` exposes `archived_at`
(unlike `AccountResponse`) so the `include_archived=true` listing can reveal
which rows are tombstoned. `period_kind` / `scope` are domain `Literal`s
(`PeriodKind` / `Scope`), so an out-of-set value is a 422 at the boundary (the
`budgets.period_kind` / `budgets.scope` columns carry no CHECK, S08.1).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.modules.budget.domain import PeriodKind, Scope

# `name` mirrors `Category.name` = `String(120)`; min 1 forbids the empty label.
_NAME_MIN, _NAME_MAX = 1, 120
# Hex `#RRGGBB`. The column is `String(7)`; the format lives here, not in a
# CHECK (gabarit `currency`), so the palette evolves without a migration.
_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"
# `icon` is an unbounded label DB-side; bound it here as an anti-DoS measure at
# the boundary (a UI icon name is short).
_ICON_MAX = 64


class CategoryCreate(BaseModel):
    """`POST /categories`. `extra="forbid"` ⇒ a client-supplied `id` → 422.

    The id is generated server-side (closing finding #104); `parent_id` is
    optional (omit / null = a root). `color`/`icon` are optional and
    UI-defaulted.
    """

    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=_NAME_MIN, max_length=_NAME_MAX)
    color: str | None = Field(default=None, pattern=_COLOR_PATTERN)
    icon: str | None = Field(default=None, max_length=_ICON_MAX)
    parent_id: UUID | None = None


class CategoryUpdate(BaseModel):
    """`PATCH /categories/{id}` (edit). `name`/`color`/`icon` only.

    `extra="forbid"` ⇒ a `parent_id` in the body → 422: re-parenting is a
    distinct route. Every field is optional for a partial update; the route
    applies only the keys actually sent (`exclude_unset`).
    """

    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=_NAME_MIN, max_length=_NAME_MAX)
    color: str | None = Field(default=None, pattern=_COLOR_PATTERN)
    icon: str | None = Field(default=None, max_length=_ICON_MAX)


class CategoryMove(BaseModel):
    """`PATCH /categories/{id}/parent`. `parent_id` required, nullable (null = root)."""

    model_config = ConfigDict(extra="forbid")
    parent_id: UUID | None


class CategoryResponse(BaseModel):
    """Flat category view. `archived_at` exposed (nullable) — unlike accounts.

    `from_attributes=True` serialises the ORM `Category` directly; every field
    is a scalar loaded at flush (no relationship), so no async lazy-load fires
    at serialisation time. `archived_at` is non-null only in the
    `include_archived=true` listing.
    """

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    color: str | None
    icon: str | None
    parent_id: UUID | None
    created_at: datetime
    archived_at: datetime | None


# --- Budgets (S08.4) -------------------------------------------------------


class BudgetCreate(BaseModel):
    """`POST /budgets`. `extra="forbid"` ⇒ a client `id`/`created_by`/`currency` → 422.

    `created_by` is server-derived from the token (D5); `currency` is derived
    from the household base currency (D6, mono-currency V1) — neither is
    accepted in the body. `period_kind`/`scope` are domain `Literal`s (closed
    sets validated here, the columns carry no CHECK). `amount_cents > 0` mirrors
    the `consumption_from_totals` guard. `contributor_ids` is non-empty; the
    `personal ⇒ {owner}` / `shared ⇒ ≥ 2` invariant is enforced at the service.
    """

    model_config = ConfigDict(extra="forbid")
    category_id: UUID
    period_kind: PeriodKind
    period_start: date
    amount_cents: int = Field(gt=0)
    scope: Scope
    carry_over_remainder: bool = False
    contributor_ids: list[UUID] = Field(min_length=1)


class BudgetUpdate(BaseModel):
    """`PATCH /budgets/{id}`. Only `amount_cents`/`carry_over_remainder`/`contributor_ids`.

    `extra="forbid"` ⇒ a `scope`/`category_id`/`period_*`/`currency` in the body
    → 422 (frozen after creation, D7/D8). Every field optional for a partial
    PATCH; the route uses `exclude_unset`, so a `{}` body is a no-op (not a
    wipe-to-None). `contributor_ids`, when present, **replaces** the whole set.
    """

    model_config = ConfigDict(extra="forbid")
    amount_cents: int | None = Field(default=None, gt=0)
    carry_over_remainder: bool | None = None
    contributor_ids: list[UUID] | None = Field(default=None, min_length=1)


class BudgetConsumptionResponse(BaseModel):
    """API view of `BudgetConsumption` (S08.2). `percent` is the raw ratio
    (`0.80` = 80 %); the `×100`/`%` formatting is a UI decision."""

    model_config = ConfigDict(from_attributes=True)
    consumed_cents: int
    remaining_cents: int
    percent: Decimal
    splits_count: int


class BudgetResponse(BaseModel):
    """Flat view of a budget + its contributor ids (built via `_to_response`).

    Not `from_attributes` driven directly off the ORM: `contributor_ids` is a
    separate query (no relationship is loaded), so the transport assembles the
    field list explicitly. `currency`/`created_by` are server-derived (D5/D6).
    """

    id: UUID
    category_id: UUID
    period_kind: PeriodKind
    period_start: date
    amount_cents: int
    currency: str
    scope: Scope
    created_by: UUID
    carry_over_remainder: bool
    contributor_ids: list[UUID]
    created_at: datetime
    archived_at: datetime | None


class BudgetWithConsumptionResponse(BaseModel):
    """One listing item: a budget paired with its consumption at `as_of`."""

    budget: BudgetResponse
    consumption: BudgetConsumptionResponse


class BudgetListResponse(BaseModel):
    """`GET /budgets` — the budgets concerning the caller, each with consumption.

    Unpaginated in V1 (few budgets per household, §7); the contributor load is
    batched into one query (D14) so the listing is not N+1 on contributors.
    """

    items: list[BudgetWithConsumptionResponse]


class ContributingSplitResponse(BaseModel):
    """One split in the drill-down (S08.4.3). Amounts raw (`amount_cents`+`currency`).

    `category_id` is non-NULL by construction (the `IN subtree` filter excludes
    the canonical account leg, E15). `from_attributes` serialises the
    `ContributingSplit` dataclass the service returns.
    """

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    transaction_id: UUID
    account_id: UUID
    category_id: UUID
    amount_cents: int
    currency: str
    date: date


class ContributingSplitsListResponse(BaseModel):
    """A page of contributing splits + the opaque cursor of the next page (None if last)."""

    items: list[ContributingSplitResponse]
    next_cursor: str | None
