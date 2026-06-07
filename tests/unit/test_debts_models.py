"""Structural tests for `debts.models` (S09.1 `Debt` / `ShareRequest`).

Same doctrine as `test_budget_models.py`: `__tablename__` and FK `ondelete`
are NOT re-tested here — they live byte-for-byte in the level-1 snapshot
(migration-authoritative) and fire in the integration behaviour tests
(RESTRICT/CASCADE). The unit tier pins decisions invisible to the snapshot or
uncovered elsewhere: the column set (incl. the *absence* of an `account_id`
index and of a CHECK on `origin`), the two defensive CHECKs, the partial unique
index, and the `share_ratio` default.
"""

from __future__ import annotations

from decimal import Decimal
from typing import cast

from sqlalchemy import CheckConstraint, Numeric, String, Table

from backend.modules.debts.models import Debt, ShareRequest

# ---------------------------------------------------------------------------
# Debt (P09.1.1)
# ---------------------------------------------------------------------------


def test_debt_tablename() -> None:
    assert Debt.__tablename__ == "debts"


def test_debt_columns_present() -> None:
    assert set(cast(Table, Debt.__table__).c.keys()) == {
        "id",
        "from_user_id",
        "to_user_id",
        "amount_cents",
        "currency",
        "account_id",
        "source_transaction_id",
        "origin",
        "share_ratio",
        "created_at",
        "materialization_trace",
    }


def test_debt_nullability() -> None:
    cols = cast(Table, Debt.__table__).c
    assert cols["id"].primary_key is True
    # `materialization_trace` is the only nullable column (server-only forensic
    # marker, may be absent in MVP's synchronous one-shot insert).
    assert cols["materialization_trace"].nullable is True
    for name in (
        "from_user_id",
        "to_user_id",
        "amount_cents",
        "currency",
        "account_id",
        "source_transaction_id",
        "origin",
        "share_ratio",
        "created_at",
    ):
        assert cols[name].nullable is False, name


def test_origin_has_no_check() -> None:
    # The closed set (`shared_account_overflow`/`personal_share_request`) is
    # locked at the Pydantic boundary (S09.3), NOT in SQL — kept evolvable
    # (overflow F10, E11) without a migration. The only CHECKs are the two
    # defensive ones below, never one enumerating `origin`.
    table = cast(Table, Debt.__table__)
    checks = {c.name for c in table.constraints if isinstance(c, CheckConstraint)}
    assert checks == {"ck_debts_no_self_debt", "ck_debts_amount_positive"}


def test_origin_is_plain_string() -> None:
    col_type = cast(Table, Debt.__table__).c["origin"].type
    assert isinstance(col_type, String)
    # Open-ended `String` (no length bound) — the value set, not the length, is
    # the constraint, and it lives at the boundary.
    assert col_type.length is None


def test_share_ratio_is_numeric_5_4_default_one() -> None:
    col = cast(Table, Debt.__table__).c["share_ratio"]
    assert isinstance(col.type, Numeric)
    assert (col.type.precision, col.type.scale) == (5, 4)
    # Python-side default (not server_default) → 1.0 when unspecified, while
    # keeping the create_all/Alembic snapshot parity (the migration column has
    # no server_default).
    assert col.default is not None
    assert col.default.arg == Decimal("1.0")  # type: ignore[union-attr]


def test_debt_indexes_are_the_fk_paths_plus_overflow_unique() -> None:
    # `account_id` deliberately has NO standalone index (no read path filters
    # it; the bucket key is derived at the service). Exact set doubles as the
    # anti-surnumerary guard. Literal names pin the create_all/Alembic parity.
    # `uq_debts_overflow_active` (S11.3) is the partial unique backing the
    # overflow `ON CONFLICT DO UPDATE`; the FK-path `ix_debts_source_transaction_id`
    # standalone is KEPT (the partial index only covers overflow rows, D2).
    names = {ix.name for ix in cast(Table, Debt.__table__).indexes}
    assert names == {
        "ix_debts_from_user_id",
        "ix_debts_to_user_id",
        "ix_debts_source_transaction_id",
        "uq_debts_overflow_active",
    }


def test_overflow_unique_index_is_partial_on_four_columns() -> None:
    # The overflow idempotence index (S11.3 P11.3.1): UNIQUE, partial (predicate
    # on the overflow origin) and over the four columns in declaration order.
    table = cast(Table, Debt.__table__)
    overflow = next(ix for ix in table.indexes if ix.name == "uq_debts_overflow_active")
    assert overflow.unique is True
    assert list(overflow.columns.keys()) == [
        "source_transaction_id",
        "from_user_id",
        "to_user_id",
        "origin",
    ]
    # Pin the FULL predicate: it must bind the overflow literal to the `origin`
    # column specifically (not merely "some WHERE that mentions the literal") —
    # that binding is what guarantees exclusivité d'origine.
    predicate = str(overflow.dialect_options["postgresql"]["where"])
    assert predicate == "origin = 'shared_account_overflow'"


def test_debt_has_no_account_id_index() -> None:
    table = cast(Table, Debt.__table__)
    assert all(list(idx.columns.keys()) != ["account_id"] for idx in table.indexes)


# ---------------------------------------------------------------------------
# ShareRequest (P09.1.2)
# ---------------------------------------------------------------------------


def test_share_request_tablename() -> None:
    assert ShareRequest.__tablename__ == "share_requests"


def test_share_request_columns_present() -> None:
    assert set(cast(Table, ShareRequest.__table__).c.keys()) == {
        "id",
        "source_transaction_id",
        "requested_by",
        "requested_from",
        "ratio",
        "short_label",
        "created_at",
        "revoked_at",
    }


def test_share_request_nullability() -> None:
    cols = cast(Table, ShareRequest.__table__).c
    assert cols["id"].primary_key is True
    assert cols["revoked_at"].nullable is True  # active SR until revoked
    for name in (
        "source_transaction_id",
        "requested_by",
        "requested_from",
        "ratio",
        "short_label",
        "created_at",
    ):
        assert cols[name].nullable is False, name


def test_short_label_is_string_100() -> None:
    col_type = cast(Table, ShareRequest.__table__).c["short_label"].type
    assert isinstance(col_type, String)
    assert col_type.length == 100


def test_ratio_is_numeric_5_4() -> None:
    col_type = cast(Table, ShareRequest.__table__).c["ratio"].type
    assert isinstance(col_type, Numeric)
    assert (col_type.precision, col_type.scale) == (5, 4)


def test_share_request_only_check_is_no_self() -> None:
    table = cast(Table, ShareRequest.__table__)
    checks = {c.name for c in table.constraints if isinstance(c, CheckConstraint)}
    assert checks == {"ck_share_requests_no_self"}


def test_active_unique_index_is_partial() -> None:
    # The unique is PARTIAL (`WHERE revoked_at IS NULL`): a revoked SR frees the
    # (tx, débiteur) slot. The partial nature is invisible to a bare index-name
    # list — assert the exact predicate (must match the migration byte-for-byte,
    # create_all/Alembic parity, same trap as `uq_invitations_pending_email`).
    table = cast(Table, ShareRequest.__table__)
    active = next(ix for ix in table.indexes if ix.name == "uq_share_requests_active")
    assert active.unique is True
    assert list(active.columns.keys()) == ["source_transaction_id", "requested_from"]
    where = active.dialect_options["postgresql"]["where"]
    assert str(where) == "revoked_at IS NULL"


def test_share_request_index_set() -> None:
    # No standalone `source_transaction_id` index (the partial unique leads with
    # it). Exact set is the anti-surnumerary guard + parity pin.
    names = {ix.name for ix in cast(Table, ShareRequest.__table__).indexes}
    assert names == {
        "uq_share_requests_active",
        "ix_share_requests_requested_from",
        "ix_share_requests_requested_by",
    }
