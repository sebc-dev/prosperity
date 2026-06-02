"""Structural tests for `budget.models` (S06.1 `Category`, S08.1 `Budget` /
`BudgetContributor`)."""

from __future__ import annotations

from typing import cast

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    SmallInteger,
    String,
    Table,
    UniqueConstraint,
)

from backend.modules.budget.models import (
    Budget,
    BudgetContributor,
    BudgetThresholdAlert,
    Category,
)


def test_tablename_is_categories() -> None:
    assert Category.__tablename__ == "categories"


def test_expected_columns_and_nullability() -> None:
    cols = cast(Table, Category.__table__).c
    assert cols["id"].primary_key is True
    assert cols["name"].nullable is False
    assert cols["color"].nullable is True
    assert cols["icon"].nullable is True
    assert cols["parent_id"].nullable is True
    assert cols["created_at"].nullable is False
    assert cols["archived_at"].nullable is True


def test_name_is_string_120() -> None:
    col_type = cast(Table, Category.__table__).c["name"].type
    assert isinstance(col_type, String)
    assert col_type.length == 120


def test_color_is_string_7() -> None:
    col_type = cast(Table, Category.__table__).c["color"].type
    assert isinstance(col_type, String)
    assert col_type.length == 7


def test_no_check_constraint_on_table() -> None:
    # color format + cycle prevention are NOT enforced in SQL (D4, D7).
    table = cast(Table, Category.__table__)
    assert not any(isinstance(c, CheckConstraint) for c in table.constraints)


def test_parent_fk_is_self_ref_restrict() -> None:
    table = cast(Table, Category.__table__)
    fks = [c for c in table.constraints if isinstance(c, ForeignKeyConstraint)]
    assert len(fks) == 1
    fk = fks[0]
    assert fk.name == "fk_categories_parent_id_categories"
    assert fk.elements[0].column.table.name == "categories"  # self-ref
    assert fk.ondelete == "RESTRICT"


def test_index_names_are_explicit_and_distinct() -> None:
    # Both indexes are named explicitly in the model (not derived from the
    # NAMING_CONVENTION): they both cover `parent_id`, so the convention's
    # `column_0_N_label` token would collide on a single name. The literal
    # names also pin the create_all/Alembic parity the snapshot checks.
    names = {ix.name for ix in cast(Table, Category.__table__).indexes}
    assert names == {"ix_categories_parent_id", "ix_categories_active"}


def test_active_index_is_partial() -> None:
    active = next(
        ix for ix in cast(Table, Category.__table__).indexes if ix.name == "ix_categories_active"
    )
    where = active.dialect_options["postgresql"]["where"]
    # Assert the exact predicate, not just its presence: it must match the
    # migration's `postgresql_where` byte-for-byte (create_all/Alembic parity,
    # same trap as `uq_invitations_pending_email`).
    assert str(where) == "archived_at IS NULL"


# ---------------------------------------------------------------------------
# Budget / BudgetContributor (S08.1, P08.1.1)
# ---------------------------------------------------------------------------
#
# Same doctrine as `test_accounts_models.py:67-74`: `__tablename__` and the FK
# `ondelete` are NOT re-tested here — they live byte-for-byte in the level-1
# snapshot (migration-authoritative) and fire in the integration behaviour
# tests (RESTRICT/CASCADE). The unit tier only pins decisions invisible to the
# snapshot or uncovered elsewhere: column set (incl. the *absence* of
# `account_id`), absence of CHECK, the unique, the lack of a standalone
# `budget_id` index, the partial nature of `ix_budgets_active`, and the
# `carry_over_remainder` server_default (the snapshot ignores column defaults).


def test_budget_columns_present() -> None:
    table = cast(Table, Budget.__table__)
    assert set(table.c.keys()) == {
        "id",
        "category_id",
        "period_kind",
        "period_start",
        "amount_cents",
        "currency",
        "scope",
        "created_by",
        "created_at",
        "archived_at",
        "carry_over_remainder",
    }
    # No `account_id`: a budget binds to category + scope + contributors, not
    # to an account (CONTEXT.md §Budget). Pins the structural decision §1 —
    # invisible to the snapshot, which only lists columns that exist.
    assert "account_id" not in table.c


def test_budget_contributor_columns_present() -> None:
    assert set(cast(Table, BudgetContributor.__table__).c.keys()) == {
        "id",
        "budget_id",
        "user_id",
    }


def test_no_check_on_budgets_or_contributors() -> None:
    # `period_kind`/`scope` are closed sets locked at the Pydantic boundary
    # (S08.4), NOT in the column — anti-regression guard if someone "hardens"
    # by adding a CHECK. Extended to both tables.
    for model in (Budget, BudgetContributor):
        table = cast(Table, model.__table__)
        assert not [c for c in table.constraints if isinstance(c, CheckConstraint)]


def test_unique_contributor_constraint() -> None:
    table = cast(Table, BudgetContributor.__table__)
    uc = next(
        c
        for c in table.constraints
        if isinstance(c, UniqueConstraint) and c.name == "uq_budget_contributors_budget_id_user_id"
    )
    assert list(uc.columns.keys()) == ["budget_id", "user_id"]


def test_contributor_budget_id_has_no_standalone_index() -> None:
    # The composite unique already indexes `budget_id` as its leading column →
    # serves the CASCADE lookup, so no standalone `[budget_id]` index is
    # declared (would be redundant write cost). Pins the delta vs a naive
    # split that would index both FKs. Jumeau
    # `test_account_member_account_id_has_no_standalone_index`.
    table = cast(Table, BudgetContributor.__table__)
    assert all(list(idx.columns.keys()) != ["budget_id"] for idx in table.indexes)


def test_budgets_active_index_is_partial() -> None:
    active = next(
        ix for ix in cast(Table, Budget.__table__).indexes if ix.name == "ix_budgets_active"
    )
    where = active.dialect_options["postgresql"]["where"]
    # The *partial* nature (vs a full index) is invisible to a bare index-name
    # list. Assert the exact predicate — it must match the migration's
    # `postgresql_where` byte-for-byte (create_all/Alembic parity).
    assert str(where) == "archived_at IS NULL"
    # `ix_budgets_category_id` (full) and `ix_budgets_active` (partial) both
    # cover `category_id` but play distinct roles — both must exist. Exact set
    # (== not <=) doubles as the anti-surnumerary guard: the three explicit
    # names are required and no extra index sneaks in. The literal names also
    # pin the create_all/Alembic parity the snapshot checks.
    names = {ix.name for ix in cast(Table, Budget.__table__).indexes}
    assert names == {"ix_budgets_category_id", "ix_budgets_created_by", "ix_budgets_active"}


def test_carry_over_default_false() -> None:
    # The snapshot does NOT capture `column_default` (`_format_schema` extracts
    # only type + nullability), so this is the only static guard on the
    # server_default. Access via `server_default.arg.text` (the SQL literal).
    server_default = cast(Table, Budget.__table__).c.carry_over_remainder.server_default
    assert server_default is not None
    assert server_default.arg.text == "false"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# BudgetThresholdAlert (S08.3, P08.3.1) — table d'idempotence des alertes
# ---------------------------------------------------------------------------


def test_threshold_alert_columns_present() -> None:
    assert set(cast(Table, BudgetThresholdAlert.__table__).c.keys()) == {
        "id",
        "budget_id",
        "period_start",
        "threshold_pct",
    }


def test_threshold_pct_is_small_integer() -> None:
    col_type = cast(Table, BudgetThresholdAlert.__table__).c["threshold_pct"].type
    assert isinstance(col_type, SmallInteger)


def test_threshold_alert_no_check_constraint() -> None:
    # threshold_pct ∈ {80,100,120} verrouillé au domaine (`crossed_thresholds`),
    # PAS par un CHECK — anti-regression si quelqu'un « durcit » en SQL.
    table = cast(Table, BudgetThresholdAlert.__table__)
    assert not [c for c in table.constraints if isinstance(c, CheckConstraint)]


def test_threshold_alert_unique_named_dedup() -> None:
    # The unique is the target of `ON CONFLICT ON CONSTRAINT` — its literal name
    # is load-bearing (the detector references it). Pin name + column order.
    table = cast(Table, BudgetThresholdAlert.__table__)
    uc = next(
        c
        for c in table.constraints
        if isinstance(c, UniqueConstraint) and c.name == "uq_budget_threshold_alerts_dedup"
    )
    assert list(uc.columns.keys()) == ["budget_id", "period_start", "threshold_pct"]


def test_threshold_alert_budget_fk_cascade() -> None:
    table = cast(Table, BudgetThresholdAlert.__table__)
    fks = [c for c in table.constraints if isinstance(c, ForeignKeyConstraint)]
    assert len(fks) == 1
    fk = fks[0]
    assert fk.name == "fk_budget_threshold_alerts_budget_id_budgets"
    assert fk.elements[0].column.table.name == "budgets"
    assert fk.ondelete == "CASCADE"


def test_threshold_alert_budget_id_has_no_standalone_index() -> None:
    # The composite unique already indexes `budget_id` as its leading column →
    # serves the CASCADE lookup, so no standalone `[budget_id]` index is
    # declared (gabarit `budget_contributors`).
    table = cast(Table, BudgetThresholdAlert.__table__)
    assert all(list(idx.columns.keys()) != ["budget_id"] for idx in table.indexes)
