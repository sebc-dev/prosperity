"""Unit tests for the budget Pydantic schemas (S06.3, P06.3.2).

Pin the boundary contracts that the HTTP routes lean on:
- `color` accepts only `#RRGGBB` (the `categories.color` column has no CHECK);
- `CategoryCreate` rejects a client-supplied `id` (id is server-side, #104);
- `CategoryUpdate` rejects a `parent_id` (re-parenting has its own route);
- `icon` is length-bounded at the edge (the column is unbounded DB-side).

No DB — pure Pydantic validation, so this lives in the `unit` tier.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.modules.budget.schemas import CategoryCreate, CategoryUpdate


@pytest.mark.parametrize("color", ["#ffffff", "#000000", "#0A1b2C", "#FFFFFF"])
def test_color_valid(color: str) -> None:
    assert CategoryCreate(name="X", color=color).color == color


@pytest.mark.parametrize(
    "color",
    ["#fff", "#GGGGGG", "ffffff", "#1234567", "#12345", "red", ""],
)
def test_color_invalid(color: str) -> None:
    with pytest.raises(ValidationError):
        CategoryCreate(name="X", color=color)


def test_color_optional() -> None:
    # color is nullable / UI-defaulted; omitting it is fine.
    assert CategoryCreate(name="X").color is None


def test_create_forbids_client_id() -> None:
    # #104: the id is strictly server-side; a client-supplied `id` → 422.
    with pytest.raises(ValidationError):
        CategoryCreate.model_validate({"name": "X", "id": str(uuid4())})


def test_create_forbids_unknown_field() -> None:
    with pytest.raises(ValidationError):
        CategoryCreate.model_validate({"name": "X", "bogus": 1})


def test_create_accepts_parent_id() -> None:
    parent = uuid4()
    assert CategoryCreate(name="X", parent_id=parent).parent_id == parent


def test_update_forbids_parent_id() -> None:
    # Re-parenting is a distinct route; a `parent_id` in the edit body → 422.
    with pytest.raises(ValidationError):
        CategoryUpdate.model_validate({"name": "X", "parent_id": str(uuid4())})


def test_update_all_fields_optional() -> None:
    # A partial edit may send nothing; exclude_unset then applies no change.
    assert CategoryUpdate().model_dump(exclude_unset=True) == {}


def test_icon_too_long() -> None:
    with pytest.raises(ValidationError):
        CategoryCreate(name="X", icon="a" * 65)


def test_name_bounds() -> None:
    with pytest.raises(ValidationError):
        CategoryCreate(name="")
    with pytest.raises(ValidationError):
        CategoryCreate(name="a" * 121)
