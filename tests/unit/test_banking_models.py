"""Structural tests for `banking.models` (S12.1, P12.1.1).

No DB: introspect the SQLAlchemy table metadata only. The persisted behaviour
(composite UNIQUE + RESTRICT → `IntegrityError`) lives in the integration tier
(`tests/integration/test_banking_models.py`); the level-1 snapshot pins
create_all/Alembic name parity. Gabarit `test_transactions_models.py`.
"""

from __future__ import annotations

from typing import cast

from sqlalchemy import (
    UUID,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    String,
    Table,
    UniqueConstraint,
)

from backend.modules.banking.models import BankAccountExternalRef


def test_tablename_is_bank_account_external_refs() -> None:
    assert BankAccountExternalRef.__tablename__ == "bank_account_external_refs"


def test_expected_columns_and_nullability() -> None:
    cols = cast(Table, BankAccountExternalRef.__table__).c
    assert cols["id"].primary_key is True
    # Every business column is NOT NULL (a link is meaningless half-filled).
    assert cols["external_ref"].nullable is False
    assert cols["internal_account_id"].nullable is False
    assert cols["provider"].nullable is False
    assert cols["created_at"].nullable is False


def test_uuid_columns_are_uuid_type() -> None:
    cols = cast(Table, BankAccountExternalRef.__table__).c
    for name in ("id", "internal_account_id"):
        assert isinstance(cols[name].type, UUID), name


def test_text_columns_are_string_type() -> None:
    # `external_ref` / `provider` are plain `String` (text) — a drift to a
    # length-capped type or ENUM would change the snapshot and break parity.
    cols = cast(Table, BankAccountExternalRef.__table__).c
    for name in ("external_ref", "provider"):
        assert isinstance(cols[name].type, String), name


def test_created_at_has_server_default() -> None:
    col = cast(Table, BankAccountExternalRef.__table__).c["created_at"]
    assert isinstance(col.type, DateTime)
    assert col.server_default is not None


def test_unique_constraint_is_composite_external_ref_provider() -> None:
    # AC #176: uniqueness is on the COUPLE `(external_ref, provider)` — never on
    # `external_ref` alone (the same ref under two providers must coexist).
    table = cast(Table, BankAccountExternalRef.__table__)
    uniques = [c for c in table.constraints if isinstance(c, UniqueConstraint)]
    assert len(uniques) == 1
    uq = uniques[0]
    assert uq.name == "uq_bank_account_external_refs_external_ref_provider"
    assert [col.name for col in uq.columns] == ["external_ref", "provider"]


def test_internal_account_fk_targets_accounts() -> None:
    # FK declared by string → `accounts.id`. The `ON DELETE RESTRICT` *behaviour*
    # is proven DB-side in the integration tier (gabarit `test_transactions_models`
    # reserves CASCADE/RESTRICT assertions for integration).
    table = cast(Table, BankAccountExternalRef.__table__)
    fks = [c for c in table.constraints if isinstance(c, ForeignKeyConstraint)]
    assert len(fks) == 1
    fk = fks[0]
    assert [col.name for col in fk.columns] == ["internal_account_id"]
    assert [el.target_fullname for el in fk.elements] == ["accounts.id"]


def test_no_check_constraint_on_provider() -> None:
    # `provider` is an OPEN, evolving set ('ofx' V1, 'enable_banking' later):
    # NO ENUM, NO CHECK (unlike the closed sets `leg_role`/`debt_generation_override`).
    # The value lock lives at the service boundary. Pins decision D1.
    table = cast(Table, BankAccountExternalRef.__table__)
    checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    assert checks == []
