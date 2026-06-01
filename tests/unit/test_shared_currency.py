"""Unit tests for `backend.shared.currency` (S07.1, P07.1.1).

Pure unit tier — no DB. Pins the `Currency` literal, its runtime mirror
`CURRENCIES`, the display symbols (uniqueness + non-suffix invariants required
by the `parse_french` round-trip, P07.1.3) and `validate_currency` at the
non-Pydantic boundary.
"""

from __future__ import annotations

import itertools

import pytest
from pydantic import ValidationError

from backend.shared.currency import (
    CURRENCIES,
    CURRENCY_SYMBOLS,
    validate_currency,
)

_KNOWN_CODES = ("EUR", "USD", "GBP", "CHF")


def test_currencies_set_derives_from_literal() -> None:
    assert CURRENCIES == set(_KNOWN_CODES)


def test_symbols_cover_exactly_the_currencies() -> None:
    # Garde anti-désync : autant de symboles que de codes, exactement les mêmes.
    assert set(CURRENCY_SYMBOLS) == CURRENCIES


@pytest.mark.parametrize("code", _KNOWN_CODES)
def test_validate_currency_accepts_each_known_code(code: str) -> None:
    assert validate_currency(code) == code


@pytest.mark.parametrize("bad", ["JPY", "", "eur", "EURO", "EU"])
def test_validate_currency_rejects_unknown_code(bad: str) -> None:
    with pytest.raises(ValidationError):
        validate_currency(bad)


def test_symbols_are_unique() -> None:
    # Invertibilité requise par le parseur (P07.1.3) : un symbole <-> une devise.
    assert len(set(CURRENCY_SYMBOLS.values())) == len(CURRENCY_SYMBOLS)


def test_no_symbol_is_suffix_of_another() -> None:
    # Fige l'invariant qui rend `parse_french`/`endswith` non ambigu et casse au
    # bon moment si une extension V2 ajoute un symbole suffixe d'un autre.
    symbols = list(CURRENCY_SYMBOLS.values())
    for s1, s2 in itertools.permutations(symbols, 2):
        assert not s1.endswith(s2), f"{s1!r} se termine par {s2!r} (ambiguïté de parse)"
