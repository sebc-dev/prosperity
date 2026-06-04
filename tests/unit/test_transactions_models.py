"""Structural tests for `transactions.models` (S07.2, P07.2.1 + P07.2.2).

No DB: introspect the SQLAlchemy table metadata only. The persisted
behaviour (CASCADE/RESTRICT, round-trip) lives in the integration tier; the
level-1 snapshot pins create_all/Alembic name parity.
"""

from __future__ import annotations

import subprocess
import sys
from typing import cast

from sqlalchemy import (
    ARRAY,
    UUID,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    String,
    Table,
)

from backend.modules.transactions.models import Split, Transaction

# --------------------------------------------------------------------------
# Transaction
# --------------------------------------------------------------------------


def test_tablename_is_transactions() -> None:
    assert Transaction.__tablename__ == "transactions"


def test_expected_columns_and_nullability() -> None:
    cols = cast(Table, Transaction.__table__).c
    assert cols["id"].primary_key is True
    # NOT NULL
    assert cols["account_id"].nullable is False
    assert cols["date"].nullable is False
    assert cols["state"].nullable is False
    assert cols["created_by"].nullable is False
    assert cols["created_at"].nullable is False
    assert cols["tags"].nullable is False
    assert cols["debt_generation_override"].nullable is False
    # NULL
    assert cols["payee"].nullable is True
    assert cols["description"].nullable is True
    assert cols["category_id"].nullable is True
    assert cols["confirmed_at"].nullable is True
    assert cols["voided_at"].nullable is True
    assert cols["share_request_id"].nullable is True  # dormant column (S07.4/D1)


def test_created_at_has_server_default() -> None:
    # `created_at` is the ONE column with a SQL `server_default` (now());
    # `tags`/`debt_generation_override` use ORM Python-side defaults (their
    # tests assert `server_default is None`). Pin the asymmetry so a switch to
    # an ORM-side default — which would silently break create_all/Alembic
    # snapshot parity — turns this test red.
    col = cast(Table, Transaction.__table__).c["created_at"]
    assert col.server_default is not None


def test_uuid_columns_are_uuid_type() -> None:
    # Every id / FK column is a UUID (a drift to `String` would still pass the
    # nullability/FK tests). `savings_goal_id` is listed too: the dormant
    # column must stay a UUID so the future FK activation matches.
    tx_cols = cast(Table, Transaction.__table__).c
    # `share_request_id` is the dormant column (S07.4/D1): like `savings_goal_id`
    # it must stay a UUID so the future FK activation (E09) matches.
    for name in ("id", "account_id", "category_id", "created_by", "share_request_id"):
        assert isinstance(tx_cols[name].type, UUID), name
    split_cols = cast(Table, Split.__table__).c
    for name in ("id", "transaction_id", "account_id", "category_id", "savings_goal_id"):
        assert isinstance(split_cols[name].type, UUID), name


def test_no_amount_or_bank_transaction_id_column() -> None:
    # The amount is derived `sum(splits.amount_cents)` (note 🔑); the bank
    # link lives in `Reconciliation` (ADR 0006). Both columns are forbidden.
    cols = cast(Table, Transaction.__table__).c
    assert "amount" not in cols
    assert "amount_cents" not in cols
    assert "bank_transaction_id" not in cols


def test_state_is_plain_string_without_check() -> None:
    table = cast(Table, Transaction.__table__)
    state_type = table.c["state"].type
    assert isinstance(state_type, String)
    assert not isinstance(state_type, Enum)  # not a PG ENUM
    # `state` is an OPEN set kept CHECK-free for V2 evolution: no CHECK references
    # it. The only CHECK on the table is the closed-set guard on
    # `debt_generation_override` (D14, S07.4), asserted separately below.
    checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    assert all("state" not in str(c.sqltext) for c in checks)


def test_debt_generation_override_has_closed_set_check() -> None:
    # D14: a defense-in-depth CHECK on the closed 3-value set, the fail-closed
    # backstop for `update_editable_fields`' `model_copy` path (which bypasses
    # the Pydantic Literal). Mirrors the domain `DebtGenerationOverride`.
    table = cast(Table, Transaction.__table__)
    checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    debt_checks = [c for c in checks if "debt_generation_override" in str(c.sqltext)]
    assert len(debt_checks) == 1
    body = str(debt_checks[0].sqltext)
    for value in ("default", "force_full_debt", "force_no_debt"):
        assert value in body


def test_debt_generation_override_default_is_default() -> None:
    col = cast(Table, Transaction.__table__).c["debt_generation_override"]
    assert col.default is not None
    assert col.default.arg == "default"  # type: ignore[union-attr]
    assert col.server_default is None  # ORM-side only, not server_default


def test_tags_is_array_of_string_with_list_default() -> None:
    col = cast(Table, Transaction.__table__).c["tags"]
    assert isinstance(col.type, ARRAY)
    assert isinstance(col.type.item_type, String)
    # ORM Python-side callable default (SQLAlchemy wraps `list` to accept an
    # optional execution context), NOT a `server_default` — so `create_all`
    # and the migration stay at parity (the snapshot ignores ORM defaults).
    assert col.default is not None
    assert col.default.is_callable is True  # type: ignore[union-attr]
    assert col.server_default is None


def test_date_is_date_not_datetime() -> None:
    date_type = cast(Table, Transaction.__table__).c["date"].type
    assert isinstance(date_type, Date)
    assert not isinstance(date_type, DateTime)


def test_payee_is_string_255() -> None:
    payee_type = cast(Table, Transaction.__table__).c["payee"].type
    assert isinstance(payee_type, String)
    assert payee_type.length == 255


def test_transaction_fk_ondelete_actions_and_names() -> None:
    table = cast(Table, Transaction.__table__)
    fks = {c.name: c for c in table.constraints if isinstance(c, ForeignKeyConstraint)}
    assert fks["fk_transactions_account_id_accounts"].ondelete == "RESTRICT"
    assert fks["fk_transactions_account_id_accounts"].elements[0].column.table.name == "accounts"
    assert fks["fk_transactions_category_id_categories"].ondelete == "RESTRICT"
    assert (
        fks["fk_transactions_category_id_categories"].elements[0].column.table.name == "categories"
    )
    assert fks["fk_transactions_created_by_users"].ondelete == "RESTRICT"
    assert fks["fk_transactions_created_by_users"].elements[0].column.table.name == "users"


def test_share_request_id_fk_activated_set_null() -> None:
    # S09.1 activated the formerly-dormant FK (S07.4/D1): the column now carries
    # an active FK `→ share_requests.id` `ON DELETE SET NULL`, declared BY STRING
    # (no Python import of `ShareRequest`, no relationship — the import-linter
    # graph stays directional). `use_alter=True` breaks the nullable cycle with
    # `share_requests.source_transaction_id` at create_all time.
    col = cast(Table, Transaction.__table__).c["share_request_id"]
    assert col.nullable is True
    assert len(col.foreign_keys) == 1
    fk = next(iter(col.foreign_keys))
    # `target_fullname` reads the string spec without resolving the referenced
    # `Table` (debts.models need not be imported in this unit process).
    assert fk.target_fullname == "share_requests.id"
    assert fk.ondelete == "SET NULL"
    assert fk.use_alter is True


def test_fk_to_categories_is_by_string_no_budget_import() -> None:
    # `transactions ⟂ budget` (contrat 1): the model must not import the
    # `Category` model. The FK is a string reference resolved at runtime, so
    # importing `transactions.models` must NOT pull in `budget.models`.
    #
    # Run in a fresh interpreter: in a full pytest run other test modules
    # (e.g. `test_budget_models.py`) already populated `sys.modules`, so an
    # in-process `sys.modules` check would be meaningless. The subprocess
    # imports `transactions.models` alone and proves `budget.models` stays
    # absent.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import backend.modules.transactions.models; "
            "assert 'backend.modules.budget.models' not in sys.modules, "
            "sorted(m for m in sys.modules if 'budget' in m)",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_transaction_index_names() -> None:
    names = {ix.name for ix in cast(Table, Transaction.__table__).indexes}
    assert names == {
        "ix_transactions_account_id",
        "ix_transactions_category_id",
        "ix_transactions_created_by",
    }


# --------------------------------------------------------------------------
# Split
# --------------------------------------------------------------------------


def test_split_tablename_is_splits() -> None:
    assert Split.__tablename__ == "splits"


def test_split_columns_and_nullability() -> None:
    cols = cast(Table, Split.__table__).c
    assert cols["id"].primary_key is True
    assert cols["transaction_id"].nullable is False
    assert cols["account_id"].nullable is False
    assert cols["amount_cents"].nullable is False
    assert cols["currency"].nullable is False
    assert cols["category_id"].nullable is True
    assert cols["savings_goal_id"].nullable is True


def test_amount_cents_is_bigint() -> None:
    assert isinstance(cast(Table, Split.__table__).c["amount_cents"].type, BigInteger)


def test_currency_is_string_3() -> None:
    currency_type = cast(Table, Split.__table__).c["currency"].type
    assert isinstance(currency_type, String)
    assert currency_type.length == 3


def test_split_transaction_fk_is_cascade() -> None:
    table = cast(Table, Split.__table__)
    fks = {c.name: c for c in table.constraints if isinstance(c, ForeignKeyConstraint)}
    fk = fks["fk_splits_transaction_id_transactions"]
    assert fk.ondelete == "CASCADE"
    assert fk.elements[0].column.table.name == "transactions"


def test_split_account_and_category_fk_are_restrict() -> None:
    table = cast(Table, Split.__table__)
    fks = {c.name: c for c in table.constraints if isinstance(c, ForeignKeyConstraint)}
    assert fks["fk_splits_account_id_accounts"].ondelete == "RESTRICT"
    assert fks["fk_splits_account_id_accounts"].elements[0].column.table.name == "accounts"
    assert fks["fk_splits_category_id_categories"].ondelete == "RESTRICT"
    assert fks["fk_splits_category_id_categories"].elements[0].column.table.name == "categories"


def test_savings_goal_id_has_no_foreign_key() -> None:
    # Dormant column (option a): nullable UUID without an active FK, so the
    # `savings_goals` table can be created later without replaying this
    # migration.
    col = cast(Table, Split.__table__).c["savings_goal_id"]
    assert not col.foreign_keys
    assert col.nullable is True


def test_split_index_names() -> None:
    names = {ix.name for ix in cast(Table, Split.__table__).indexes}
    assert names == {
        "ix_splits_transaction_id",
        "ix_splits_account_id",
        "ix_splits_category_id",
    }


def test_split_leg_role_has_closed_set_check() -> None:
    # S08.5.1 (ADR 0017): a defense-in-depth CHECK on the closed 2-value set
    # `leg_role`, the fail-closed backstop against any out-of-enum write (raw
    # SQL, `model_copy`). Mirrors the domain `LegRole` (gabarit
    # `debt_generation_override`). The constraint `name="leg_role"` is prefixed
    # to `ck_splits_leg_role` by the NAMING_CONVENTION.
    table = cast(Table, Split.__table__)
    checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    leg_role_checks = [c for c in checks if "leg_role" in str(c.sqltext)]
    assert len(leg_role_checks) == 1
    body = str(leg_role_checks[0].sqltext)
    for value in ("funding", "classification"):
        assert value in body


def test_split_leg_role_default_is_context_callable() -> None:
    # The ORM Python-side default derives `leg_role` from `category_id` at INSERT
    # (context-sensitive callable), NOT a server_default — keeps create_all /
    # Alembic snapshot parity.
    col = cast(Table, Split.__table__).c["leg_role"]
    assert col.nullable is False
    assert col.default is not None
    assert callable(col.default.arg)  # type: ignore[union-attr]
    assert col.server_default is None
