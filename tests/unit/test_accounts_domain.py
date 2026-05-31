"""Unit tests for `backend.modules.accounts.domain` (S05.1, P05.1.1).

`AccountType` lives in `domain.py` (SQLAlchemy-free) and is re-exported by
`models.py`. These tests pin the enum's value mapping and cardinality —
the contract between the Python catalogue and the Postgres `account_type`
ENUM (Alembic 0007). A drift between member values and stored labels would
silently break the persistence round-trip pinned in the integration tier.
"""

from __future__ import annotations

import enum

import pytest

import backend.modules.accounts.domain as accounts_domain
import backend.modules.accounts.models as accounts_models
from backend.modules.accounts.domain import AccountType


def test_account_type_values_are_lowercase_french() -> None:
    # The stored values (not member names) mirror the Postgres `account_type`
    # ENUM (Alembic 0007); StrEnum makes the members compare equal to them.
    assert {member.value for member in AccountType} == {
        "courant",
        "livret",
        "epargne",
        "especes",
        "credit",
    }


def test_account_type_is_strenum() -> None:
    assert issubclass(AccountType, enum.StrEnum)
    assert AccountType.COURANT == "courant"


def test_account_type_has_exactly_five_members() -> None:
    # Cardinality is part of the contract: adding/removing a type must be a
    # deliberate change (an `ALTER TYPE` migration), not a silent edit.
    assert len(list(AccountType)) == 5


def test_account_type_lookup_by_value_is_canonical_member() -> None:
    assert AccountType("courant") is AccountType.COURANT
    assert AccountType("credit") is AccountType.CREDIT


def test_account_type_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="invalid"):
        AccountType("invalid")


def test_account_type_identity_is_shared_with_models() -> None:
    # `models.py` re-imports the enum from `domain.py`; the SQLAlchemy
    # mapping (`Account.type`) and every re-export resolve the same object.
    assert accounts_models.AccountType is accounts_domain.AccountType
