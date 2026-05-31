"""Unit tests for `backend.modules.accounts.public` cross-module surface (S03.1)."""

from __future__ import annotations

import backend.modules.accounts.public as accounts_public
from backend.modules.accounts import events as _events
from backend.modules.accounts.models import HOUSEHOLD_SINGLETON_UUID
from backend.modules.accounts.public import (
    HOUSEHOLD_ID,
    AccountMemberAdded,
    AccountMemberRemoved,
    HouseholdNotInitializedError,
    ShareRatioUpdated,
    bootstrap_initial_admin_from_env,
    get_household,
)
from backend.modules.accounts.service import household as _household_service
from backend.modules.accounts.service import setup as _setup_service
from backend.shared.events import DomainEvent


def test_public_exports_exact_set() -> None:
    assert set(accounts_public.__all__) == {
        "HOUSEHOLD_ID",
        "AccountMemberAdded",
        "AccountMemberRemoved",
        "HouseholdNotInitializedError",
        "ShareRatioUpdated",
        "bootstrap_initial_admin_from_env",
        "get_household",
    }


def test_public_symbols_are_callable_or_exceptions() -> None:
    assert callable(get_household)
    assert callable(bootstrap_initial_admin_from_env)
    assert issubclass(HouseholdNotInitializedError, Exception)


def test_household_id_is_the_singleton_uuid() -> None:
    assert HOUSEHOLD_ID == HOUSEHOLD_SINGLETON_UUID


def test_public_names_are_identical_objects_to_internals() -> None:
    # Guards against a refactor that re-implements a stub in `public.py`
    # instead of re-exporting the real symbols from internal modules.
    assert accounts_public.HOUSEHOLD_ID is HOUSEHOLD_SINGLETON_UUID
    assert (
        accounts_public.HouseholdNotInitializedError
        is _household_service.HouseholdNotInitializedError
    )
    assert accounts_public.get_household is _household_service.get_household
    assert (
        accounts_public.bootstrap_initial_admin_from_env
        is _setup_service.bootstrap_initial_admin_from_env
    )
    # The S05.4 events re-export the concrete types defined in `accounts.events`.
    assert accounts_public.AccountMemberAdded is _events.AccountMemberAdded
    assert accounts_public.AccountMemberRemoved is _events.AccountMemberRemoved
    assert accounts_public.ShareRatioUpdated is _events.ShareRatioUpdated


def test_exception_is_a_plain_exception_subclass() -> None:
    assert issubclass(HouseholdNotInitializedError, Exception)


def test_event_types_are_domain_events() -> None:
    for event_type in (AccountMemberAdded, AccountMemberRemoved, ShareRatioUpdated):
        assert issubclass(event_type, DomainEvent)
