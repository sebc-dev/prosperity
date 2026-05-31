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
from decimal import Decimal
from typing import Final, Literal

from sqlalchemy import (
    UUID,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

# Canonical home of `AccountType` is `domain.py` (SQLAlchemy-free). Re-imported
# here so `Account.type` maps it — gabarit `auth.models` ↔ `auth.domain`.
from backend.modules.accounts.domain import AccountType
from backend.shared.models import Base


def _account_type_values(enum_cls: type[AccountType]) -> list[str]:
    # SQLAlchemy's `Enum.values_callable` defaults to enum member *names*
    # (`COURANT`); the PG ENUM stores the lowercased *values* (`courant`),
    # so we override to keep both representations aligned (gabarit
    # `_user_role_values`).
    return [member.value for member in enum_cls]


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


class Account(Base):
    """A financial account: personal (single `owner_id`) or shared (≥2 members).

    Personal vs shared is **not** a SQL constraint here — the invariant
    `(owner_id IS NOT NULL) XOR (len(members) ≥ 2)` is enforced by the
    service (S05.2), because a cross-row CHECK on `account_members` would
    need a PostgreSQL trigger (overkill). S05.1 ships only the persisted
    socle.

    `owner_id` is `ON DELETE RESTRICT`: a user who owns an account can never
    be hard-deleted (decision F02 — users are *disabled*, never deleted), so
    the account is never orphaned nor silently reassigned. It is `nullable`
    because only a personal account carries one (a shared account leaves it
    NULL and lists its members via `account_members`).

    `currency` ships as plain `String(3)` (ISO 4217) with no CHECK: the V1
    EUR lock lives in `household.base_currency` + the S05.2 service
    validation, not in this column — the `Money`/account model stays
    multi-currency-ready (ADR 0008).

    `name` is a display label (gabarit `Household.name`), not a business
    identifier: two accounts may legitimately share a name, so there is
    deliberately no `(household_id, name)` uniqueness — an account's identity
    is its `id` UUID.

    `archived_at` backs the soft-delete of S05.3 (`DELETE /accounts` =
    archive, not hard delete); posted now to avoid a one-column migration.
    """

    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("household.id", name="fk_accounts_household_id_household"),
        nullable=False,
        default=HOUSEHOLD_SINGLETON_UUID,  # always the singleton (ADR 0010)
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[AccountType] = mapped_column(
        Enum(
            AccountType,
            name="account_type",
            values_callable=_account_type_values,
        ),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_accounts_owner_id_users"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        # Index the RESTRICT FK: without it Postgres seq-scans `accounts` on
        # every `users` delete to enforce the constraint (gabarit
        # `ix_invitations_invited_by`). `household_id` is deliberately NOT
        # indexed: the singleton is never deleted (ADR 0010) and the column
        # is mono-valued, so an index would never be chosen by the planner
        # and only cost on writes.
        Index("ix_accounts_owner_id", "owner_id"),
    )


class AccountMember(Base):
    """A user's membership of a *shared* account, with their ownership ratio.

    `default_share_ratio` is the member's quote-part (CONTEXT.md §Quote-part):
    the default `share_ratio` for debts this shared account generates. Stored
    as `Numeric(5, 4)` → `Decimal` (never float) so the service can validate
    `Σ ratios == Decimal("1.0000")` exactly (S05.2), with no float tolerance.

    `account_id` is `ON DELETE CASCADE` (the membership has no meaning without
    its account); `user_id` is `ON DELETE RESTRICT` (a member user is disabled,
    never deleted — decision F02, gabarit `accounts.owner_id`).

    The unique `(account_id, user_id)` forbids a duplicate membership and, as
    a composite index, already serves the `account_id`-leading lookup of the
    CASCADE — so only `user_id` needs a standalone index (for the RESTRICT
    seq-scan avoidance on `users` delete).
    """

    __tablename__ = "account_members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "accounts.id",
            ondelete="CASCADE",
            name="fk_account_members_account_id_accounts",
        ),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_account_members_user_id_users",
        ),
        nullable=False,
    )
    default_share_ratio: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # At most one membership per (account, user). The composite also
        # indexes `account_id` as its leading column → serves the CASCADE
        # lookup, so no standalone `account_id` index is declared.
        UniqueConstraint(
            "account_id",
            "user_id",
            name="uq_account_members_account_id_user_id",
        ),
        # `user_id` is not the leading column above → its own index is needed
        # for the `ON DELETE RESTRICT` seq-scan avoidance on `users` delete.
        Index("ix_account_members_user_id", "user_id"),
    )
