"""Structural tests for `budget.models.Category` (S06.1, P06.1.1)."""

from __future__ import annotations

from typing import cast

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, String, Table

from backend.modules.budget.models import Category


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
