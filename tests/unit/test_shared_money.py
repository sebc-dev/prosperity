"""Unit tests for `backend.shared.money` (S07.1, P07.1.2 + P07.1.3).

Pure unit tier — no DB. Pins the `Money` value object (arithmetic, cross-currency
refusal, ordering, immutability, strict integer cents, hashing) and the French
formatter / parser pair (`format_french` / `parse_french`). Properties are
non-tautological (they relate `+` to `×`, exercise the format/parse round-trip
and `-` involution), with `@example()` pins on the round-trip per the test
strategy (§4.2).
"""

from __future__ import annotations

import re
from dataclasses import FrozenInstanceError

import pytest
from hypothesis import example, given
from pydantic import ValidationError

from backend.shared.money import IncompatibleCurrencyError, Money, parse_french
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


# ---------------------------------------------------------------------------
# P07.1.3 — format_french (example-based)
# ---------------------------------------------------------------------------


def test_format_thousands() -> None:
    # Codepoints exacts : U+202F (milliers) et U+00A0 (avant symbole).
    assert Money(123456, "EUR").format_french() == "1 234,56 €"


def test_format_zero() -> None:
    assert Money(0, "EUR").format_french() == "0,00 €"


def test_format_sub_unit() -> None:
    assert Money(56, "EUR").format_french() == "0,56 €"


def test_format_negative() -> None:
    assert Money(-123456, "EUR").format_french() == "-1 234,56 €"


def test_format_millions() -> None:
    assert Money(123456789, "EUR").format_french() == "1 234 567,89 €"


def test_format_very_large() -> None:
    # 4 groupes, au-delà de _MONEY_BOUND : _group_thousands tient ; round-trip OK.
    m = Money(1234567890123, "EUR")
    assert m.format_french() == "12 345 678 901,23 €"
    assert parse_french(m.format_french()) == m


@pytest.mark.parametrize(
    ("currency", "symbol"),
    [("EUR", "€"), ("USD", "$"), ("GBP", "£"), ("CHF", "CHF")],
)
def test_format_each_currency_symbol(currency: str, symbol: str) -> None:
    out = Money(123456, currency).format_french()  # type: ignore[arg-type]
    # Le gap U+00A0 doit précéder le symbole (pas un espace ASCII).
    assert out.endswith(f" {symbol}")


# ---------------------------------------------------------------------------
# P07.1.3 — parse_french : nominal + laxiste sur le groupage
# ---------------------------------------------------------------------------


def test_parse_nominal() -> None:
    assert parse_french("1 234,56 €") == Money(123456, "EUR")


def test_parse_accepts_plain_space() -> None:
    # Normalisation _SPACE_TRANSLATION : espaces ASCII ordinaires acceptés.
    assert parse_french("1 234,56 €") == Money(123456, "EUR")


def test_parse_accepts_ungrouped() -> None:
    # Groupage non vérifié (décision laxiste assumée).
    assert parse_french("1234,56 €") == Money(123456, "EUR")


def test_parse_negative_zero() -> None:
    assert parse_french("-0,00 €") == Money(0, "EUR")


# ---------------------------------------------------------------------------
# P07.1.3 — parse_french : entrées invalides
# ---------------------------------------------------------------------------


def test_parse_unknown_symbol_raises() -> None:
    with pytest.raises(ValueError, match="Symbole de devise inconnu"):
        parse_french("1 234,56 ¥")


def test_parse_no_symbol_raises() -> None:
    with pytest.raises(ValueError, match="Symbole de devise inconnu"):
        parse_french("12,34")


@pytest.mark.parametrize("text", ["", "   "])
def test_parse_empty_raises(text: str) -> None:
    with pytest.raises(ValueError, match="Symbole de devise inconnu"):
        parse_french(text)


def test_parse_no_decimal_separator_raises() -> None:
    with pytest.raises(ValueError, match="Montant FR invalide"):
        parse_french("1 234 €")


@pytest.mark.parametrize("text", ["1 234,5 €", "1 234,567 €"])
def test_parse_bad_decimals_raises(text: str) -> None:
    with pytest.raises(ValueError, match="Montant FR invalide"):
        parse_french(text)


@pytest.mark.parametrize("text", ["１２,３４ €", "²²,²² €"])
def test_parse_rejects_non_ascii_digits(text: str) -> None:
    # Chiffres Unicode (fullwidth, exposants) rejetés avec message contrôlé.
    with pytest.raises(ValueError, match="Montant FR invalide"):
        parse_french(text)


# ---------------------------------------------------------------------------
# P07.1.3 — properties
# ---------------------------------------------------------------------------


@given(money_strategy())
@example(Money(123456, "EUR"))  # cas pivot multi-séparateurs
@example(Money(0, "EUR"))
@example(Money(-123456, "USD"))
def test_property_format_parse_roundtrip(m: Money) -> None:
    assert parse_french(m.format_french()) == m


@given(money_strategy())
def test_property_format_has_two_decimals(m: Money) -> None:
    # La sortie se termine toujours par `,DD<gap><symbole>` (non tautologique).
    assert re.search(r",\d{2} \S+$", m.format_french()) is not None
