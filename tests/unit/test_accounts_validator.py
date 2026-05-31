"""Unit tests for `accounts.domain.AccountValidator` (S05.2, P05.2.1).

The validator is the **pure** core of account creation: it owns the three
business rules — currency must equal `household.base_currency` (ADR 0008),
ownership shape `(owner_id IS NOT NULL) XOR (len(members) >= 2)`, and
`Σ default_share_ratio == Decimal("1.0000")` in **exact** Decimal (no float
tolerance). It imports only the stdlib (no session / ORM / FastAPI), so the
whole rule-set is testable without a database, and the quantifiable invariants
are pinned with Hypothesis (domain-only, per Stratégie §4.2).

The rule **order** is part of the contract and several tests pin it: currency
is checked first, then shape, then — only for the shared form — the ratio sum.
"""

from __future__ import annotations

from decimal import Decimal
from string import ascii_uppercase
from uuid import UUID, uuid4

import hypothesis.strategies as st
import pytest
from hypothesis import assume, given

from backend.modules.accounts.domain import (
    AccountValidationError,
    AccountValidator,
    CurrencyMismatchError,
    DuplicateMemberError,
    MemberShare,
    NonPositiveShareRatioError,
    OwnershipShapeError,
    ShareRatioSumError,
    TooFewMembersError,
)

_BASE = "EUR"


def _members(*ratios: str) -> list[MemberShare]:
    """Build members with fresh user_ids and the given Decimal ratios."""
    return [MemberShare(user_id=uuid4(), ratio=Decimal(r)) for r in ratios]


# ---------------------------------------------------------------------------
# Accepted shapes
# ---------------------------------------------------------------------------


def test_accepts_personal_owner_without_members() -> None:
    AccountValidator.validate(
        currency=_BASE,
        household_base_currency=_BASE,
        owner_id=uuid4(),
        members=(),
    )


def test_accepts_shared_two_members_summing_one() -> None:
    AccountValidator.validate(
        currency=_BASE,
        household_base_currency=_BASE,
        owner_id=None,
        members=_members("0.5000", "0.5000"),
    )


def test_accepts_shared_three_members_summing_one() -> None:
    AccountValidator.validate(
        currency=_BASE,
        household_base_currency=_BASE,
        owner_id=None,
        members=_members("0.5000", "0.2500", "0.2500"),
    )


def test_share_ratio_trailing_zeros_accepted() -> None:
    # Decimal "==" ignores trailing zeros: Decimal("0.5") == Decimal("0.5000"),
    # so 0.5 + 0.5 == Decimal("1.0000") holds even at a coarser scale.
    AccountValidator.validate(
        currency=_BASE,
        household_base_currency=_BASE,
        owner_id=None,
        members=_members("0.5", "0.5"),
    )


# ---------------------------------------------------------------------------
# Currency rule
# ---------------------------------------------------------------------------


def test_rejects_currency_mismatch_personal() -> None:
    with pytest.raises(CurrencyMismatchError):
        AccountValidator.validate(
            currency="USD",
            household_base_currency=_BASE,
            owner_id=uuid4(),
            members=(),
        )


def test_rejects_currency_mismatch_shared() -> None:
    with pytest.raises(CurrencyMismatchError):
        AccountValidator.validate(
            currency="USD",
            household_base_currency=_BASE,
            owner_id=None,
            members=_members("0.5000", "0.5000"),
        )


def test_currency_checked_before_shape() -> None:
    # Bad currency AND an invalid shape (owner + members): currency wins
    # because `_check_currency` runs first. Pins the rule order.
    with pytest.raises(CurrencyMismatchError):
        AccountValidator.validate(
            currency="USD",
            household_base_currency=_BASE,
            owner_id=uuid4(),
            members=_members("0.5000", "0.5000"),
        )


# ---------------------------------------------------------------------------
# Ownership shape rule
# ---------------------------------------------------------------------------


def test_rejects_owner_and_members_both_present() -> None:
    with pytest.raises(OwnershipShapeError):
        AccountValidator.validate(
            currency=_BASE,
            household_base_currency=_BASE,
            owner_id=uuid4(),
            members=_members("0.5000", "0.5000"),
        )


def test_rejects_neither_owner_nor_members() -> None:
    with pytest.raises(OwnershipShapeError):
        AccountValidator.validate(
            currency=_BASE,
            household_base_currency=_BASE,
            owner_id=None,
            members=(),
        )


def test_rejects_shared_single_member() -> None:
    with pytest.raises(TooFewMembersError):
        AccountValidator.validate(
            currency=_BASE,
            household_base_currency=_BASE,
            owner_id=None,
            members=_members("1.0000"),
        )


def test_rejects_single_member_with_invalid_ratio() -> None:
    # A shared account with one member whose ratio is NOT 1: the shape check
    # (≥ 2 members) fires *before* the ratio-sum check, so the error is
    # TooFewMembersError, not ShareRatioSumError. Pins shape-before-ratios.
    with pytest.raises(TooFewMembersError):
        AccountValidator.validate(
            currency=_BASE,
            household_base_currency=_BASE,
            owner_id=None,
            members=_members("0.5000"),
        )


# ---------------------------------------------------------------------------
# Share-ratio sum rule (exact Decimal, no tolerance)
# ---------------------------------------------------------------------------


def test_rejects_ratios_sum_below_one() -> None:
    with pytest.raises(ShareRatioSumError):
        AccountValidator.validate(
            currency=_BASE,
            household_base_currency=_BASE,
            owner_id=None,
            members=_members("0.5000", "0.4999"),
        )


def test_rejects_ratios_sum_above_one() -> None:
    with pytest.raises(ShareRatioSumError):
        AccountValidator.validate(
            currency=_BASE,
            household_base_currency=_BASE,
            owner_id=None,
            members=_members("0.5000", "0.5001"),
        )


def test_share_ratio_sum_is_exact_decimal_no_tolerance() -> None:
    # ⚠️ Delta roadmap pin: NO 1e-6 float tolerance. 0.3333×3 = 0.9999 is
    # rejected exactly, because the sum is computed in Decimal, never float.
    with pytest.raises(ShareRatioSumError):
        AccountValidator.validate(
            currency=_BASE,
            household_base_currency=_BASE,
            owner_id=None,
            members=_members("0.3333", "0.3333", "0.3333"),
        )


# ---------------------------------------------------------------------------
# Per-ratio positivity rule (each quote-part strictly > 0)
# ---------------------------------------------------------------------------


def test_rejects_negative_ratio() -> None:
    with pytest.raises(NonPositiveShareRatioError):
        AccountValidator.validate(
            currency=_BASE,
            household_base_currency=_BASE,
            owner_id=None,
            members=_members("0.7000", "-0.2000"),
        )


def test_rejects_zero_ratio() -> None:
    # A zero quote-part is meaningless even when the others sum the rest to 1.
    with pytest.raises(NonPositiveShareRatioError):
        AccountValidator.validate(
            currency=_BASE,
            household_base_currency=_BASE,
            owner_id=None,
            members=_members("1.0000", "0.0000"),
        )


def test_positivity_checked_before_sum() -> None:
    # [1.5, -0.5] sums *exactly* to 1.0000, so only the positivity rule can
    # reject it — pins positivity-before-sum and proves the Σ check alone is
    # insufficient (Numeric(5, 4) is signed).
    with pytest.raises(NonPositiveShareRatioError):
        AccountValidator.validate(
            currency=_BASE,
            household_base_currency=_BASE,
            owner_id=None,
            members=_members("1.5000", "-0.5000"),
        )


# ---------------------------------------------------------------------------
# Duplicate-member rule (a user cannot be listed twice)
# ---------------------------------------------------------------------------


def test_rejects_duplicate_member() -> None:
    dup = uuid4()
    with pytest.raises(DuplicateMemberError):
        AccountValidator.validate(
            currency=_BASE,
            household_base_currency=_BASE,
            owner_id=None,
            members=[
                MemberShare(user_id=dup, ratio=Decimal("0.5000")),
                MemberShare(user_id=dup, ratio=Decimal("0.5000")),
            ],
        )


def test_duplicate_checked_before_ratios() -> None:
    # Duplicate members whose ratios would also be invalid: the duplicate rule
    # fires first (before positivity / sum). Pins the rule order.
    dup = uuid4()
    with pytest.raises(DuplicateMemberError):
        AccountValidator.validate(
            currency=_BASE,
            household_base_currency=_BASE,
            owner_id=None,
            members=[
                MemberShare(user_id=dup, ratio=Decimal("0.3000")),
                MemberShare(user_id=dup, ratio=Decimal("0.3000")),
            ],
        )


# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------


def test_all_leaf_errors_subclass_base() -> None:
    # The route (S05.3) maps the whole family with one `except
    # AccountValidationError` → 422; the leaves let precise callers branch.
    for leaf in (
        CurrencyMismatchError,
        OwnershipShapeError,
        TooFewMembersError,
        ShareRatioSumError,
        NonPositiveShareRatioError,
        DuplicateMemberError,
    ):
        assert issubclass(leaf, AccountValidationError)


# ---------------------------------------------------------------------------
# Property-based (Hypothesis, inline strategies — shared strategy lands S05.5)
# ---------------------------------------------------------------------------


@st.composite
def _members_summing_to(draw: st.DrawFn, *, total: int, max_size: int = 6) -> list[MemberShare]:
    """N∈[2,max_size] strictly-positive 4dp Decimal ratios summing to total/10000.

    Partition `total` into N integer parts ≥ 1 via distinct cut-points, then
    map each part p to Decimal(p)/Decimal(10000) — exact at scale 4. The sum is
    `total/10000`, so `total == 10000` yields Σ == Decimal("1.0000") exactly.
    """
    n = draw(st.integers(min_value=2, max_value=max_size))
    assume(total >= n)  # need at least 1 unit per part
    cuts = sorted(
        draw(
            st.lists(
                st.integers(min_value=1, max_value=total - 1),
                min_size=n - 1,
                max_size=n - 1,
                unique=True,
            )
        )
    )
    bounds = [0, *cuts, total]
    parts = [bounds[i + 1] - bounds[i] for i in range(n)]
    return [MemberShare(user_id=uuid4(), ratio=Decimal(p) / Decimal(10000)) for p in parts]


@given(members=_members_summing_to(total=10000))
def test_property_valid_shared_is_accepted(members: list[MemberShare]) -> None:
    # ∀ multiset of Decimal ratios summing to 1 with |members| ≥ 2 → accepted.
    AccountValidator.validate(
        currency=_BASE,
        household_base_currency=_BASE,
        owner_id=None,
        members=members,
    )


@given(owner_id=st.uuids(), members=_members_summing_to(total=10000))
def test_property_owner_plus_members_always_rejected(
    owner_id: UUID, members: list[MemberShare]
) -> None:
    # ∀ owner_id + non-empty members → contradictory shape → OwnershipShapeError.
    with pytest.raises(OwnershipShapeError):
        AccountValidator.validate(
            currency=_BASE,
            household_base_currency=_BASE,
            owner_id=owner_id,
            members=members,
        )


@given(
    currency=st.text(alphabet=ascii_uppercase, min_size=3, max_size=3),
    owner_id=st.uuids(),
)
def test_property_currency_mismatch_always_rejected(currency: str, owner_id: UUID) -> None:
    # ∀ currency != base → CurrencyMismatchError, whatever the shape — holds
    # because `_check_currency` runs first (currency beats any shape error).
    assume(currency != _BASE)
    with pytest.raises(CurrencyMismatchError):
        AccountValidator.validate(
            currency=currency,
            household_base_currency=_BASE,
            owner_id=owner_id,
            members=(),
        )


@given(
    total=st.integers(min_value=2, max_value=20000),
    data=st.data(),
)
def test_property_ratios_not_summing_to_one_rejected(total: int, data: st.DataObject) -> None:
    # ∀ positive 4dp ratios, |members| ≥ 2, Σ != 1.0000 → ShareRatioSumError.
    assume(total != 10000)
    members = data.draw(_members_summing_to(total=total))
    with pytest.raises(ShareRatioSumError):
        AccountValidator.validate(
            currency=_BASE,
            household_base_currency=_BASE,
            owner_id=None,
            members=members,
        )


# === S05.4 validate_member_set ===
# `validate_member_set` re-validates a shared account's member set alone (no
# currency / ownership-shape rules), used by the S05.4 member mutations. It
# reuses the same private helpers as `validate`'s shared branch, so the rules
# (>= 2, no duplicate, each ratio > 0, Σ == 1.0000) must hold identically.


def test_member_set_accepts_two_members_summing_one() -> None:
    AccountValidator.validate_member_set(_members("0.5000", "0.5000"))


def test_member_set_accepts_three_members_summing_one() -> None:
    AccountValidator.validate_member_set(_members("0.3300", "0.3300", "0.3400"))


def test_member_set_rejects_single_member() -> None:
    with pytest.raises(TooFewMembersError):
        AccountValidator.validate_member_set(_members("1.0000"))


def test_member_set_rejects_empty() -> None:
    with pytest.raises(TooFewMembersError):
        AccountValidator.validate_member_set([])


def test_member_set_rejects_sum_not_one() -> None:
    with pytest.raises(ShareRatioSumError):
        AccountValidator.validate_member_set(_members("0.5000", "0.4000"))


def test_member_set_rejects_non_positive_ratio() -> None:
    members = [
        MemberShare(user_id=uuid4(), ratio=Decimal("1.5000")),
        MemberShare(user_id=uuid4(), ratio=Decimal("-0.5000")),
    ]
    with pytest.raises(NonPositiveShareRatioError):
        AccountValidator.validate_member_set(members)


def test_member_set_rejects_duplicate_member() -> None:
    dup = uuid4()
    members = [
        MemberShare(user_id=dup, ratio=Decimal("0.5000")),
        MemberShare(user_id=dup, ratio=Decimal("0.5000")),
    ]
    with pytest.raises(DuplicateMemberError):
        AccountValidator.validate_member_set(members)
