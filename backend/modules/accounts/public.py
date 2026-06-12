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

from backend.modules.accounts.domain import AccountType, AccountValidationError, MemberShare
from backend.modules.accounts.events import (
    AccountMemberAdded,
    AccountMemberRemoved,
    ShareRatioUpdated,
)
from backend.modules.accounts.models import HOUSEHOLD_SINGLETON_UUID as HOUSEHOLD_ID
from backend.modules.accounts.service.accounts import (
    accessible_account_ids,
    account_is_accessible,
    archive,
    create_personal,
    create_shared,
    owned_personal_account_ids,
    rename,
    shared_account_ids_with_members_subset,
    shared_account_member_ids,
    shared_account_members_with_ratios,
)
from backend.modules.accounts.service.household import (
    HouseholdNotInitializedError,
    get_household,
)
from backend.modules.accounts.service.setup import bootstrap_initial_admin_from_env

# The write surface (`create_personal`/`create_shared`/`rename`/`archive`) plus the
# value objects the caller must build to drive it (`AccountType`, `MemberShare`) are
# re-exported for the sync write upload handler (S13.4): the handler maps a PowerSync
# mutation onto these acts and never reaches into `accounts.{service,domain}` itself
# (ADR 0014 — public-surface-only). The re-exports are intra-module (the `2-*`
# contracts bar *peers*, not `public`); the `2-sync` `ignore_imports` block carries
# the second-hop entries (`accounts.public -> accounts.{service.accounts,domain}`).
__all__ = [
    "AccountMemberAdded",
    "AccountMemberRemoved",
    "AccountType",
    "AccountValidationError",
    "HOUSEHOLD_ID",
    "HouseholdNotInitializedError",
    "MemberShare",
    "ShareRatioUpdated",
    "accessible_account_ids",
    "account_is_accessible",
    "archive",
    "bootstrap_initial_admin_from_env",
    "create_personal",
    "create_shared",
    "get_household",
    "owned_personal_account_ids",
    "rename",
    "shared_account_ids_with_members_subset",
    "shared_account_member_ids",
    "shared_account_members_with_ratios",
]
