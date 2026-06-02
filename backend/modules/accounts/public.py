"""Public surface of the accounts module — re-exports for cross-module use.

This module is the only one in `backend.modules.accounts` that other
modules may import from. The import-linter contract "Only public
surface importable cross-module" forbids any cross-module import that
reaches into `backend.modules.accounts.{service,models,domain,repository}`.

`HOUSEHOLD_SINGLETON_UUID` is re-exported under the shorter name
`HOUSEHOLD_ID` because that is the name the rest of the codebase
references (matches the S03.1 issue acceptance criteria and the future
RBAC code in E04).
"""

from __future__ import annotations

from backend.modules.accounts.events import (
    AccountMemberAdded,
    AccountMemberRemoved,
    ShareRatioUpdated,
)
from backend.modules.accounts.models import HOUSEHOLD_SINGLETON_UUID as HOUSEHOLD_ID
from backend.modules.accounts.service.accounts import (
    accessible_account_ids,
    account_is_accessible,
)
from backend.modules.accounts.service.household import (
    HouseholdNotInitializedError,
    get_household,
)
from backend.modules.accounts.service.setup import bootstrap_initial_admin_from_env

__all__ = [
    "AccountMemberAdded",
    "AccountMemberRemoved",
    "HOUSEHOLD_ID",
    "HouseholdNotInitializedError",
    "ShareRatioUpdated",
    "accessible_account_ids",
    "account_is_accessible",
    "bootstrap_initial_admin_from_env",
    "get_household",
]
