"""ORM models for the accounts module.

Singleton design (ADR 0010): a single `household` row exists per
deployment, identified by a fixed UUID. A SQL CHECK constraint blocks
inserting any other row (including via raw SQL bypassing the ORM).

Cross-module callers reach `HOUSEHOLD_ID` and the `Household` accessor
via `accounts.public` — import-linter contract 2 forbids importing this
module from outside `accounts`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final, Literal

from sqlalchemy import UUID, CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.shared.models import Base

# Fixed singleton identifier (ADR 0010). Hard-coded everywhere — no DB
# lookup. Re-exported via `accounts.public.HOUSEHOLD_ID`.
HOUSEHOLD_SINGLETON_UUID: Final[uuid.UUID] = uuid.UUID("00000000-0000-0000-0000-000000000001")


class Household(Base):
    """The single household instance for this deployment.

    ADR 0010 pins the cardinality at exactly one row; the CHECK on `id`
    enforces it at the DB level so a raw INSERT bypassing the ORM is
    rejected just as the second `Household()` would be.

    `base_currency` is `Literal["EUR"]` in Python (ADR 0008 mono-currency
    V1) with no DB CHECK so the V1 → V2 multi-currency unlock is a code
    change, not a migration. Column ships as `String(3)` for ISO 4217.

    `initialized_at` is the bootstrap sentinel: NULL means the singleton
    row exists but `/setup` (S03.2) has not completed. `get_household()`
    treats NULL identically to a missing row.
    """

    __tablename__ = "household"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=HOUSEHOLD_SINGLETON_UUID,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_currency: Mapped[Literal["EUR"]] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    initialized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # `NAMING_CONVENTION` will prefix this to `ck_household_singleton`,
    # matching the `op.f("ck_household_singleton")` in migration 0004 —
    # without that alignment, `create_all` (tests) and `alembic upgrade`
    # (prod, snapshot tests) would produce divergent constraint names.
    __table_args__ = (
        CheckConstraint(
            f"id = '{HOUSEHOLD_SINGLETON_UUID}'::uuid",
            name="singleton",
        ),
    )
