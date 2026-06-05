"""Unit tests for the pure helpers of `debts.service.settlement` (S10.4, P10.4.1).

The effectful `create_settlement` is exercised in the integration tier
(`test_create_settlement.py`); here we lock the PURE pieces it delegates to:

- `_assert_single_household` — the foyer comparator (its reject branch is NOT
  constructible in integration under the singleton ADR 0010, so the unit test is
  the only place the `!=` path is exercised directly; the integration tier proves
  the comparator is *wired* into `create_settlement` via a monkeypatch).
- `derive_transfer_amount` — the `Σ positive splits` derivation (D3), pinned with
  a Hypothesis property over zero-sum split sets (ADR 0001 ⇒ Σ+ == |Σ−|), the
  candidate the test strategy names for this invariant (T-M3).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st

from backend.modules.debts.service.settlement import (
    CrossHouseholdError,
    _assert_single_household,  # pyright: ignore[reportPrivateUsage]  # pure comparator under test
    derive_transfer_amount,
)

HOUSEHOLD_ID = uuid4()


def test_single_household_does_not_raise_when_all_match() -> None:
    _assert_single_household({HOUSEHOLD_ID}, expected=HOUSEHOLD_ID)  # no raise
    _assert_single_household(set(), expected=HOUSEHOLD_ID)  # empty set is vacuously single


def test_single_household_raises_on_divergent_id() -> None:
    # A synthetic foreign foyer id mixed in → CrossHouseholdError (→ 404). This is
    # the reject branch the singleton makes un-seedable in integration (plan §6).
    with pytest.raises(CrossHouseholdError):
        _assert_single_household({HOUSEHOLD_ID, uuid4()}, expected=HOUSEHOLD_ID)


def test_derive_transfer_amount_example() -> None:
    # internal_transfer: 2 funding legs −X/+X on 2 accounts → magnitude X.
    assert derive_transfer_amount([-5000, 5000]) == 5000
    # external_transfer: funding(−X) + classification(+X) on 1 account → X.
    assert derive_transfer_amount([-3000, 3000]) == 3000
    # empty / no positive leg → 0.
    assert derive_transfer_amount([]) == 0


@given(
    st.lists(
        st.integers(min_value=-1_000_000, max_value=1_000_000),
        min_size=0,
        max_size=12,
    )
)
def test_derive_transfer_amount_equals_abs_negatives_on_zero_sum(amounts: list[int]) -> None:
    # ADR 0001 zero-sum: a confirmed tx's splits sum to 0. We complete any list to
    # a zero-sum set by appending the balancing leg, then assert the derivation
    # (Σ positives) equals |Σ negatives| — the property D3 relies on.
    balanced = [*amounts, -sum(amounts)]
    positives = sum(a for a in balanced if a > 0)
    negatives = sum(a for a in balanced if a < 0)
    assert derive_transfer_amount(balanced) == positives == abs(negatives)
