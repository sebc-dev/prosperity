"""Smoke property test proving Hypothesis is wired into pytest."""

from hypothesis import given
from hypothesis import strategies as st

from tests import strategies as _strategies

assert _strategies is not None


@given(st.integers(), st.integers())
def test_integer_addition_is_commutative(a: int, b: int) -> None:
    assert a + b == b + a
