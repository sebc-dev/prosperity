"""Pydantic I/O schemas for the budget HTTP transport (S06.3).

Drive the `/categories` CRUD. `extra="forbid"` on every request body turns a
client surprise into a loud 422 rather than a silent no-op:

* `CategoryCreate` rejects a client-supplied `id` (the id is strictly
  server-side, closing the S06.2 vacuous-guard finding #104) and any unknown
  field;
* `CategoryUpdate` rejects a `parent_id` — re-parenting has its own route
  (`PATCH /{id}/parent`), so a `parent_id` in the edit body is a contract
  error, not a move.

`color` is validated `^#[0-9A-Fa-f]{6}$` at the boundary (gabarit the accounts
`currency` rule) — the `categories.color` column carries no CHECK, keeping the
palette evolvable without a migration. `CategoryResponse` exposes `archived_at`
(unlike `AccountResponse`) so the `include_archived=true` listing can reveal
which rows are tombstoned.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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
