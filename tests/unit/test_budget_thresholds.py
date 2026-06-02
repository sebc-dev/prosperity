"""Unit tests for the pure threshold detector `crossed_thresholds` (S08.3, P08.3.3).

`crossed_thresholds` is pure (no DB / session / clock) — its idempotence (one
alert per crossing) lives in the `budget_threshold_alerts` table at the service,
not here. Two layers (Stratégie de tests §4.1/§4.2):

* example-based — the percent boundaries, the integer-equality edge, the
  `amount<=0`/`consumed<=0` guards, multi-threshold crossing;
* property-based (Hypothesis) — MONOTONICITY (`consumed` ↑ ⇒ set ⊆) and the
  PREFIX shape, plus a CONSISTENCY property tying the integer detector to the
  `Decimal` `percent` of `consumption_from_totals` (no silent drift with the
  S08.4 display).
"""

from __future__ import annotations

from decimal import Decimal

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from backend.modules.budget.domain import (
    THRESHOLD_PERCENTS,
    consumption_from_totals,
    crossed_thresholds,
)


@pytest.mark.parametrize(
    ("consumed", "amount", "expected"),
    [
        (0, 1000, []),  # nothing spent
        (799, 1000, []),  # 79.9 % — below 80
        (800, 1000, [80]),  # exactly 80 %
        (810, 1000, [80]),  # 81 %
        (1000, 1000, [80, 100]),  # exactly 100 %
        (1050, 1000, [80, 100]),  # 105 %
        (1200, 1000, [80, 100, 120]),  # exactly 120 %
        (1300, 1000, [80, 100, 120]),  # 130 % — capped at the defined set
        (4, 5, [80]),  # integer-exact boundary: 4*100 == 80*5 → reached
        (2, 3, []),  # small amount: 200 < 240 → integer arithmetic matters
        (1000, 0, []),  # amount <= 0 → undefined ratio
        (1000, -100, []),  # negative amount → guard
        (-2000, 1000, []),  # net refund → crosses nothing
    ],
)
def test_crossed_thresholds_examples(consumed: int, amount: int, expected: list[int]) -> None:
    assert crossed_thresholds(consumed, amount) == expected


# Hypothesis strategies bounded to keep integer arithmetic in a sane range.
_amounts = st.integers(min_value=1, max_value=10_000_000)
_consumed = st.integers(min_value=0, max_value=20_000_000)


@given(c1=_consumed, c2=_consumed, amount=_amounts)
@settings(max_examples=200)
def test_crossed_thresholds_monotone_and_prefix(c1: int, c2: int, amount: int) -> None:
    lo, hi = sorted((c1, c2))
    set_lo = set(crossed_thresholds(lo, amount))
    set_hi = set(crossed_thresholds(hi, amount))
    # Monotone: more consumed ⇒ superset of crossed thresholds.
    assert set_lo <= set_hi
    # Always a prefix of THRESHOLD_PERCENTS (ascending, no gaps).
    result = crossed_thresholds(hi, amount)
    assert result == list(THRESHOLD_PERCENTS[: len(result)])


@given(consumed=_consumed, amount=_amounts)
@settings(max_examples=200)
def test_crossed_thresholds_consistent_with_percent(consumed: int, amount: int) -> None:
    # Tie the integer detector to the Decimal `percent` of the consumption domain
    # (S08.4 display) so the two never drift: a threshold is crossed iff the
    # Decimal ratio reaches it.
    percent = consumption_from_totals(
        consumed_cents=consumed, amount_cents=amount, splits_count=0
    ).percent
    crossed = set(crossed_thresholds(consumed, amount))
    for pct in THRESHOLD_PERCENTS:
        assert (pct in crossed) == (percent >= Decimal(pct) / Decimal(100))
