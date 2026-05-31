"""Smoke tests for `accounts.models` invariants."""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from typing import cast

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    Table,
    UniqueConstraint,
)

from backend.modules.accounts.models import (
    HOUSEHOLD_SINGLETON_UUID,
    Account,
    AccountMember,
    Household,
)


def test_singleton_uuid_is_pinned() -> None:
    assert HOUSEHOLD_SINGLETON_UUID == uuid.UUID("00000000-0000-0000-0000-000000000001")


def test_household_tablename_is_singular() -> None:
    # ADR 0010: "un déploiement = un foyer" — the singular tablename
    # mirrors the invariant. Drift from this would break the CHECK
    # constraint's naming-convention prefix (`ck_household_singleton`).
    assert Household.__tablename__ == "household"


def test_household_check_constraint_uses_singleton_uuid() -> None:
    # Guards against a refactor that drifts the constant away from the
    # CHECK body — the test_baseline_migration_round_trip schema check
    # would catch a missing CHECK after a downgrade, but not a CHECK
    # with the wrong literal.
    table = cast(Table, Household.__table__)
    ck = next(c for c in table.constraints if c.name == "ck_household_singleton")
    assert str(HOUSEHOLD_SINGLETON_UUID) in str(ck.sqltext)  # type: ignore[attr-defined]


def test_migration_literal_matches_orm_constant() -> None:
    # Alembic doctrine forbids historical migrations from importing live
    # constants (they must replay deterministically after a future rename).
    # The price is a duplicated UUID in migration 0004 — this test fails
    # fast if either side drifts.
    migration_path = (
        Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0004_household_singleton.py"
    )
    spec = importlib.util.spec_from_file_location("_mig_0004", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._SINGLETON_UUID_LITERAL == str(HOUSEHOLD_SINGLETON_UUID)


# ---------------------------------------------------------------------------
# Account (P05.1.1)
# ---------------------------------------------------------------------------
#
# `__tablename__` is not re-tested in the unit tier: the table name is
# already captured by the level-1 schema snapshot (`table accounts` /
# `table account_members`), so a `test_*_tablename` would be tautological.
# FK `ondelete` likewise lives in the snapshot now (migration-authoritative)
# and in the integration behaviour tests (RESTRICT/CASCADE actually fire), so
# it is not re-introspected off the ORM here. These tests only pin decisions
# left uncovered: absence of a CHECK, absence of a standalone index, the
# `Numeric(5,4)` type, and column presence.


def _fk_to(table: Table, referred_table: str) -> ForeignKey:
    # Match on the unresolved `target_fullname` string ("users.id") rather
    # than `fk.column`: the unit tier imports only `accounts.models`, so the
    # `users` table is absent from the metadata and column resolution raises.
    return next(
        fk
        for fk in table.foreign_keys
        if fk.target_fullname.split(".")[0] == referred_table
    )


def test_account_columns_present() -> None:
    table = cast(Table, Account.__table__)
    assert set(table.c.keys()) == {
        "id",
        "household_id",
        "name",
        "type",
        "currency",
        "owner_id",
        "created_at",
        "archived_at",
    }
    # `bank_link_id` is deferred to E12 (FK to a table that does not exist yet).
    assert "bank_link_id" not in table.c


def test_account_owner_id_is_nullable() -> None:
    # A personal account carries an owner; a shared account leaves it NULL.
    assert cast(Table, Account.__table__).c.owner_id.nullable is True


def test_account_household_fk_present_and_unindexed() -> None:
    table = cast(Table, Account.__table__)
    assert _fk_to(table, "household") is not None
    # `household_id` is deliberately not indexed (singleton, mono-valued).
    assert all(list(idx.columns.keys()) != ["household_id"] for idx in table.indexes)


def test_account_owner_id_is_indexed() -> None:
    # The RESTRICT FK must be indexed to avoid a seq-scan on `users` delete.
    table = cast(Table, Account.__table__)
    assert any(list(idx.columns.keys()) == ["owner_id"] for idx in table.indexes)


def test_account_has_no_check_constraint() -> None:
    # No SQL "owner XOR members" — that invariant is enforced at the service
    # (S05.2); a cross-row CHECK would need a PostgreSQL trigger.
    table = cast(Table, Account.__table__)
    assert not [c for c in table.constraints if isinstance(c, CheckConstraint)]


# ---------------------------------------------------------------------------
# AccountMember (P05.1.2)
# ---------------------------------------------------------------------------


def test_account_member_columns_present() -> None:
    assert set(cast(Table, AccountMember.__table__).c.keys()) == {
        "id",
        "account_id",
        "user_id",
        "default_share_ratio",
        "joined_at",
    }


def test_default_share_ratio_is_numeric_5_4() -> None:
    # Decimal (never float): the service validates Σ ratios == 1.0000 exactly.
    col_type = cast(Table, AccountMember.__table__).c.default_share_ratio.type
    assert isinstance(col_type, Numeric)
    assert col_type.precision == 5
    assert col_type.scale == 4


def test_account_member_unique_constraint() -> None:
    table = cast(Table, AccountMember.__table__)
    uc = next(
        c
        for c in table.constraints
        if isinstance(c, UniqueConstraint)
        and c.name == "uq_account_members_account_id_user_id"
    )
    assert list(uc.columns.keys()) == ["account_id", "user_id"]


def test_account_member_user_id_indexed() -> None:
    table = cast(Table, AccountMember.__table__)
    assert any(
        isinstance(idx, Index) and idx.name == "ix_account_members_user_id"
        for idx in table.indexes
    )


def test_account_member_account_id_has_no_standalone_index() -> None:
    # The composite unique already indexes `account_id` as its leading
    # column → no standalone `[account_id]` index is declared (would be
    # redundant write cost). Pins the delta vs the roadmap wording.
    table = cast(Table, AccountMember.__table__)
    assert all(list(idx.columns.keys()) != ["account_id"] for idx in table.indexes)
