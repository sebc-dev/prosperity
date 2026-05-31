"""Pure domain values for the accounts module (no SQLAlchemy dependency).

Holds the persistence-independent value catalogue of the module: the
`AccountType` enum (S05.1) plus the pure `AccountValidator` (S05.2) — the
currency / owner-XOR-members / Σ share_ratio rules — its typed error
taxonomy, and the `MemberShare` value object the shared-account path passes
in. The enum lives here rather than in `models.py` precisely so the
validator can reason about account types without importing the ORM stack.

Internal to `modules.accounts`: cross-module callers reach domain values
through `backend.modules.accounts.public`. Import-linter forbids reaching
into `backend.modules.accounts.domain` directly from peer modules.
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final
from uuid import UUID


class AccountType(enum.StrEnum):
    """Financial account categories (F02).

    Mirrored by the Postgres `account_type` ENUM (Alembic 0007). Adding a
    value requires a migration that ALTERs that type. `StrEnum` gives
    runtime enforcement on assignment plus a single source of truth for
    the Pydantic transports landing in S05.3.

    The SQLAlchemy mapping lives in `models.py`
    (`mapped_column(Enum(AccountType, name="account_type",
    values_callable=_account_type_values))`); `values_callable` keeps the
    stored values (`"courant"`…) aligned with the PG ENUM rather than the
    member *names*. A round-trip integration test (P05.1.3) pins that.
    """

    COURANT = "courant"
    LIVRET = "livret"
    EPARGNE = "epargne"
    ESPECES = "especes"
    CREDIT = "credit"


# Exact target for the sum of a shared account's share ratios. Decimal "=="
# ignores trailing zeros (Decimal("1.0") == Decimal("1.0000")); we spell it at
# four decimals to mirror the `Numeric(5, 4)` column and document the intent.
_SHARE_RATIO_TOTAL: Final[Decimal] = Decimal("1.0000")
_MIN_SHARED_MEMBERS: Final[int] = 2


class AccountValidationError(Exception):
    """Base of every pure account-creation rule violation (S05.2).

    A common base lets the S05.3 route map the whole family with a single
    `except AccountValidationError` → 422, while precise callers can still
    branch on a typed leaf.
    """


class CurrencyMismatchError(AccountValidationError):
    """`account.currency` != `household.base_currency` (ADR 0008 lock)."""


class OwnershipShapeError(AccountValidationError):
    """Neither a clean personal (owner, 0 member) nor shared (0 owner, members) form."""


class TooFewMembersError(AccountValidationError):
    """A shared account declared with fewer than two members."""


class ShareRatioSumError(AccountValidationError):
    """Σ default_share_ratio != Decimal('1.0000') (exact, no float tolerance)."""


@dataclass(frozen=True, slots=True)
class MemberShare:
    """A prospective membership of a shared account: a user + their quote-part.

    Pure value object (UUID + Decimal, zero ORM). The service maps each
    instance to an `AccountMember` row; the validator only reads `.ratio` and
    the cardinality.
    """

    user_id: UUID
    ratio: Decimal


class AccountValidator:
    """Pure account-creation rules (SQLAlchemy-free, no session/FastAPI).

    The service supplies `household_base_currency` (read via `get_household`)
    so this class never imports the ORM. `validate` is the single rule engine:
    the personal call passes `owner_id` + `members=()`, the shared call passes
    `owner_id=None` + the list — so the owner-XOR-members invariant is one
    centralised, fully property-testable rule.

    Rule order is part of the contract: currency, then ownership shape, then —
    only once the shared form is confirmed — the share-ratio sum.
    """

    @classmethod
    def validate(
        cls,
        *,
        currency: str,
        household_base_currency: str,
        owner_id: UUID | None,
        members: Sequence[MemberShare],
    ) -> None:
        cls._check_currency(currency, household_base_currency)
        cls._check_ownership_shape(owner_id, members)
        if owner_id is None:  # shared form confirmed by the shape check
            cls._check_share_ratios(members)

    @staticmethod
    def _check_currency(currency: str, household_base_currency: str) -> None:
        if currency != household_base_currency:
            raise CurrencyMismatchError(
                f"account currency {currency!r} != household base {household_base_currency!r}"
            )

    @staticmethod
    def _check_ownership_shape(owner_id: UUID | None, members: Sequence[MemberShare]) -> None:
        has_owner = owner_id is not None
        count = len(members)
        if has_owner and count > 0:
            raise OwnershipShapeError("a personal account (owner set) cannot carry members")
        if not has_owner and count == 0:
            raise OwnershipShapeError("an account needs either an owner or members")
        if not has_owner and count < _MIN_SHARED_MEMBERS:
            raise TooFewMembersError(
                f"a shared account needs >= {_MIN_SHARED_MEMBERS} members, got {count}"
            )

    @staticmethod
    def _check_share_ratios(members: Sequence[MemberShare]) -> None:
        total = sum((m.ratio for m in members), start=Decimal("0"))
        if total != _SHARE_RATIO_TOTAL:
            raise ShareRatioSumError(
                f"Σ default_share_ratio == {total}, expected {_SHARE_RATIO_TOTAL}"
            )
