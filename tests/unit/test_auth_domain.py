"""Unit tests for `backend.modules.auth.domain` (S04.1, P04.1.1).

`UserRole` now lives in `domain.py` (SQLAlchemy-free) and is re-exported
by `models.py`. These tests pin the enum's value mapping, cardinality,
and the cross-module identity that keeps the move transparent.

`AdminAction` (S04.2, P04.2.1) also lives here. Its value mapping is the
contract between the Python catalogue and the `admin_audit_logs.action`
text column — `log_admin_action` coerces through it, so a drift between
member values and stored strings would silently corrupt the audit trail.
"""

from __future__ import annotations

import pytest

import backend.modules.auth.domain as auth_domain
import backend.modules.auth.models as auth_models
from backend.modules.auth.domain import AdminAction, UserRole


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


def test_adminaction_values_match_audit_column_strings() -> None:
    # These exact strings are what `admin_audit_logs.action` stores; the
    # column is plain `text`, so the enum is the only thing pinning them.
    assert {member.value for member in AdminAction} == {
        "invite_sent",
        "invite_revoked",
        "invite_regenerated",
        "invite_accepted",
        "user_promoted",
        "user_disabled",
        "2fa_reset_via_db",
        "category_moved",
    }


def test_adminaction_has_exactly_eight_members() -> None:
    # Cardinality is part of the contract: adding an action is a
    # deliberate code change reviewed against the never-log blacklist.
    # `category_moved` (S06.3) reuses this audit catalogue for a member action
    # (any household member may move a category) — see the AdminAction docstring.
    assert len(list(AdminAction)) == 8


def test_adminaction_twofa_member_value_is_leading_digit_string() -> None:
    # `2fa_reset_via_db` is not a valid Python identifier, so the member
    # name diverges from the value; pin the mapping that bridges them.
    assert AdminAction.TWOFA_RESET_VIA_DB.value == "2fa_reset_via_db"


def test_adminaction_lookup_by_value_is_canonical_member() -> None:
    assert AdminAction("user_promoted") is AdminAction.USER_PROMOTED


def test_adminaction_rejects_unknown_value() -> None:
    # The runtime guard `log_admin_action` relies on: a string outside the
    # catalogue must raise, not silently persist.
    with pytest.raises(ValueError, match="bogus"):
        AdminAction("bogus")
