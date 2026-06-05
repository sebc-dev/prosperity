"""Structural tests for `debts.models` (S10.1 `Settlement` / `SettlementLine`).

Same doctrine as `test_debts_models.py`: `__tablename__` (minimal) is pinned
here but FK `ondelete` is NOT — it lives byte-for-byte in the level-1 snapshot
(migration-authoritative) and fires in the integration behaviour tests
(CASCADE/RESTRICT). The unit tier pins decisions invisible to the snapshot or
uncovered elsewhere: the column sets, nullability, the `settled_at` Date type,
the `type` plain-`String`-without-CHECK (closed set at the Pydantic boundary),
the strictly-positive line CHECK, the index sets (incl. the *absence* of a
`household_id` index), and the `String(3)` currency.
"""

from __future__ import annotations

from typing import cast

from sqlalchemy import CheckConstraint, Date, DateTime, String, Table

from backend.modules.debts.models import Settlement, SettlementLine

# ---------------------------------------------------------------------------
# Settlement (P10.1.1)
# ---------------------------------------------------------------------------


def test_settlement_tablename() -> None:
    assert Settlement.__tablename__ == "settlements"


def test_settlement_columns_present() -> None:
    assert set(cast(Table, Settlement.__table__).c.keys()) == {
        "id",
        "household_id",
        "created_by",
        "created_at",
        "settled_at",
        "type",
        "linked_transaction_id",
        "note",
    }


def test_settlement_nullability() -> None:
    cols = cast(Table, Settlement.__table__).c
    assert cols["id"].primary_key is True
    # `linked_transaction_id` (NULL ssi `virtual`) and `note` are the only
    # nullable columns.
    assert cols["linked_transaction_id"].nullable is True
    assert cols["note"].nullable is True
    for name in (
        "household_id",
        "created_by",
        "created_at",
        "settled_at",
        "type",
    ):
        assert cols[name].nullable is False, name


def test_settled_at_is_date_created_at_is_timestamp() -> None:
    cols = cast(Table, Settlement.__table__).c
    # `settled_at` is the business date of the settlement, distinct from the
    # technical `created_at` timestamp.
    assert isinstance(cols["settled_at"].type, Date)
    assert not isinstance(cols["settled_at"].type, DateTime)
    created_at = cols["created_at"]
    assert isinstance(created_at.type, DateTime)
    assert created_at.type.timezone is True
    assert created_at.server_default is not None


def test_type_is_plain_string_no_check_enumerating_set() -> None:
    # `type` is an open-ended `String` (no length) — the closed set
    # (`internal_transfer`/`external_transfer`/`virtual`) lives at the Pydantic
    # boundary (S10.2/S10.4), NOT in SQL, kept evolvable without a migration.
    # The ONLY CHECK is the relational virtual/link biconditional below; none
    # enumerates the `type` set.
    table = cast(Table, Settlement.__table__)
    col_type = table.c["type"].type
    assert isinstance(col_type, String)
    assert col_type.length is None
    checks = {c.name for c in table.constraints if isinstance(c, CheckConstraint)}
    assert checks == {"ck_settlements_virtual_no_link"}


def test_settlement_indexes() -> None:
    # Exact set doubles as the anti-surnumerary guard + create_all/Alembic parity
    # pin. Both indexed columns back a FK RESTRICT (tx + creator); `household_id`
    # has NO index (singleton never deleted).
    names = {ix.name for ix in cast(Table, Settlement.__table__).indexes}
    assert names == {
        "ix_settlements_linked_transaction_id",
        "ix_settlements_created_by",
    }


def test_settlement_has_no_household_id_index() -> None:
    table = cast(Table, Settlement.__table__)
    assert all(list(idx.columns.keys()) != ["household_id"] for idx in table.indexes)


# ---------------------------------------------------------------------------
# SettlementLine (P10.1.1)
# ---------------------------------------------------------------------------


def test_settlement_line_tablename() -> None:
    assert SettlementLine.__tablename__ == "settlement_lines"


def test_settlement_line_columns_present() -> None:
    assert set(cast(Table, SettlementLine.__table__).c.keys()) == {
        "id",
        "settlement_id",
        "debt_id",
        "amount_cents",
        "currency",
    }


def test_settlement_line_nullability() -> None:
    cols = cast(Table, SettlementLine.__table__).c
    assert cols["id"].primary_key is True
    for name in ("settlement_id", "debt_id", "amount_cents", "currency"):
        assert cols[name].nullable is False, name


def test_settlement_line_currency_is_string_3() -> None:
    col_type = cast(Table, SettlementLine.__table__).c["currency"].type
    assert isinstance(col_type, String)
    assert col_type.length == 3


def test_settlement_line_only_check_is_amount_positive() -> None:
    # D-SIGN: `amount_cents > 0`. The bidirectional netting is carried by each
    # `Debt`'s orientation, not by a sign on the line — so the only CHECK is the
    # strictly-positive one.
    table = cast(Table, SettlementLine.__table__)
    checks = {c.name for c in table.constraints if isinstance(c, CheckConstraint)}
    assert checks == {"ck_settlement_lines_amount_positive"}


def test_settlement_line_indexes() -> None:
    # `debt_id` index is the key of the `remaining` computation (S10.3) and the
    # CASCADE; `settlement_id` index reads a settlement's lines. Exact set is the
    # anti-surnumerary guard + parity pin.
    names = {ix.name for ix in cast(Table, SettlementLine.__table__).indexes}
    assert names == {
        "ix_settlement_lines_debt_id",
        "ix_settlement_lines_settlement_id",
    }
