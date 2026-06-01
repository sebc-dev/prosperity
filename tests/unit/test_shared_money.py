"""Unit tests for `backend.shared.money` (S07.1, P07.1.2).

Pure unit tier — no DB. Pins the `Money` value object: arithmetic, cross-currency
refusal, ordering, immutability, strict integer cents, hashing. Properties are
non-tautological (they relate `+` to `×`, exercise `-` involution and the
additive inverse), and the cross-currency refusal is swept over genuinely
distinct currency pairs.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from hypothesis import given
from pydantic import ValidationError

from backend.shared.money import IncompatibleCurrencyError, Money
from tests.strategies import distinct_currency_pair, money_strategy

# ---------------------------------------------------------------------------
# Arithmetic, ordering, immutability (example-based)
# ---------------------------------------------------------------------------


def test_add_same_currency() -> None:
    assert Money(100, "EUR") + Money(50, "EUR") == Money(150, "EUR")


def test_sub_same_currency() -> None:
    assert Money(100, "EUR") - Money(50, "EUR") == Money(50, "EUR")


def test_add_cross_currency_raises() -> None:
    with pytest.raises(IncompatibleCurrencyError) as exc:
        _ = Money(100, "EUR") + Money(50, "USD")
    assert exc.value.left == "EUR"
    assert exc.value.right == "USD"


def test_sub_cross_currency_raises() -> None:
    with pytest.raises(IncompatibleCurrencyError):
        _ = Money(100, "EUR") - Money(50, "USD")


def test_lt_cross_currency_raises() -> None:
    with pytest.raises(IncompatibleCurrencyError):
        _ = Money(100, "EUR") < Money(50, "USD")


def test_le_cross_currency_raises() -> None:
    # `<=` est dérivé par @total_ordering depuis `__lt__` -> propage le refus.
    with pytest.raises(IncompatibleCurrencyError):
        _ = Money(100, "EUR") <= Money(50, "USD")


def test_eq_cross_currency_is_false() -> None:
    # `==` cross-devise ne lève PAS : inégalité structurelle (D5).
    assert (Money(1, "EUR") == Money(1, "USD")) is False


def test_lt_same_currency() -> None:
    assert Money(50, "EUR") < Money(100, "EUR")
    assert Money(100, "EUR") <= Money(100, "EUR")


def test_mul_scalar() -> None:
    assert Money(100, "EUR") * 3 == Money(300, "EUR")
    assert 3 * Money(100, "EUR") == Money(300, "EUR")  # __rmul__


def test_mul_bool_rejected() -> None:
    with pytest.raises(TypeError):
        _ = Money(100, "EUR") * True


def test_mul_float_rejected() -> None:
    with pytest.raises(TypeError):
        _ = Money(100, "EUR") * 1.5


def test_neg() -> None:
    assert -Money(100, "EUR") == Money(-100, "EUR")


def test_add_non_money_raises_type_error() -> None:
    # `__add__` renvoie NotImplemented sur un non-`Money` -> TypeError Python.
    with pytest.raises(TypeError):
        _ = Money(100, "EUR") + 5  # type: ignore[operator]


def test_sub_non_money_raises_type_error() -> None:
    with pytest.raises(TypeError):
        _ = Money(100, "EUR") - 5  # type: ignore[operator]


def test_lt_non_money_raises_type_error() -> None:
    with pytest.raises(TypeError):
        _ = Money(100, "EUR") < 5  # type: ignore[operator]


def test_frozen_amount_immutable() -> None:
    m = Money(100, "EUR")
    with pytest.raises(FrozenInstanceError):
        m.amount_cents = 1  # type: ignore[misc]


def test_frozen_currency_immutable() -> None:
    m = Money(100, "EUR")
    with pytest.raises(FrozenInstanceError):
        m.currency = "USD"  # type: ignore[misc]


def test_amount_float_rejected() -> None:
    # strict=True : `float` rejeté, même un entier exact comme 1.0.
    with pytest.raises(ValidationError):
        Money(1.5, "EUR")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Money(1.0, "EUR")  # type: ignore[arg-type]


def test_unknown_currency_rejected() -> None:
    with pytest.raises(ValidationError):
        Money(100, "JPY")  # type: ignore[arg-type]


def test_hashable_in_set() -> None:
    assert len({Money(1, "EUR"), Money(1, "EUR")}) == 1
    assert len({Money(1, "EUR"), Money(1, "USD")}) == 2


# ---------------------------------------------------------------------------
# Properties (non-tautological)
# ---------------------------------------------------------------------------


@given(money_strategy(currency="EUR"), money_strategy(currency="EUR"))
def test_property_add_commutative(a: Money, b: Money) -> None:
    assert a + b == b + a


@given(
    money_strategy(currency="EUR"),
    money_strategy(currency="EUR"),
    money_strategy(currency="EUR"),
)
def test_property_add_associative(a: Money, b: Money, c: Money) -> None:
    assert (a + b) + c == a + (b + c)


@given(money_strategy(currency="EUR"))
def test_property_double_is_add_self(a: Money) -> None:
    # Relie `+` et `×` (non tautologique vis-à-vis de l'implémentation).
    assert a + a == a * 2


@given(money_strategy())
def test_property_neg_involution(a: Money) -> None:
    neg = -a
    assert -neg == a


@given(money_strategy(currency="EUR"), money_strategy(currency="EUR"))
def test_property_sub_inverse(a: Money, b: Money) -> None:
    assert (a + b) - b == a


@given(distinct_currency_pair(), money_strategy(), money_strategy())
def test_property_cross_currency_always_raises(pair: tuple[str, str], x: Money, y: Money) -> None:
    cur_a, cur_b = pair
    left = Money(x.amount_cents, cur_a)  # type: ignore[arg-type]
    right = Money(y.amount_cents, cur_b)  # type: ignore[arg-type]
    with pytest.raises(IncompatibleCurrencyError):
        _ = left + right
    with pytest.raises(IncompatibleCurrencyError):
        _ = left - right
    with pytest.raises(IncompatibleCurrencyError):
        _ = left < right
