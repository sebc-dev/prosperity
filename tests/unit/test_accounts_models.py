"""Smoke tests for `accounts.models` invariants."""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from typing import cast

from sqlalchemy import Table

from backend.modules.accounts.models import HOUSEHOLD_SINGLETON_UUID, Household


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
