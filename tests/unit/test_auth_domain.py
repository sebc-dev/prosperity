"""Unit tests for `backend.modules.auth.domain` (S04.1, P04.1.1).

`UserRole` now lives in `domain.py` (SQLAlchemy-free) and is re-exported
by `models.py`. These tests pin the enum's value mapping, cardinality,
and the cross-module identity that keeps the move transparent.
"""

from __future__ import annotations

import pytest

import backend.modules.auth.domain as auth_domain
import backend.modules.auth.models as auth_models
from backend.modules.auth.domain import UserRole


def test_userrole_values_match_pg_enum() -> None:
    # The stored values (not member names) mirror the Postgres `user_role`
    # ENUM (Alembic 0002); StrEnum makes the members compare equal to them.
    assert UserRole.ADMIN.value == "admin"
    assert UserRole.MEMBER.value == "member"


def test_userrole_has_exactly_two_members() -> None:
    # Cardinality is part of the contract: a third role must be a
    # deliberate change (migration + RBAC fail-closed branch review).
    assert list(UserRole) == [UserRole.ADMIN, UserRole.MEMBER]


def test_userrole_lookup_by_value_is_canonical_member() -> None:
    assert UserRole("admin") is UserRole.ADMIN
    assert UserRole("member") is UserRole.MEMBER


def test_userrole_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="invalid"):
        UserRole("invalid")


def test_userrole_identity_is_shared_with_models() -> None:
    # `models.py` re-imports the enum from `domain.py`; the SQLAlchemy
    # mapping (`User.role`) and every re-export resolve the same object.
    assert auth_models.UserRole is auth_domain.UserRole
