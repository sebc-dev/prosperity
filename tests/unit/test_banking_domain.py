"""Unit tests for `backend.modules.banking.domain` (S12.2, P12.2.1/P12.2.3).

Pure unit tier — no DB. Pins the common `BankTransaction` data contract (frozen,
strict integer cents — guards "jamais de float"), the `decimal_euros_to_cents`
helper (HALF_UP, determinism, round-trip — Hypothesis per test strategy §4.2),
and the `BankingProviderError` hierarchy the S12.4 boundary catches in one block.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from pydantic import ValidationError

from backend.modules.banking.domain import (
    BankingProviderError,
    BankTransaction,
    EncodingDetectionError,
    IncompatibleAccountError,
    ParsedOFX,
    ProviderUnavailableError,
    decimal_euros_to_cents,
)

# ---------------------------------------------------------------------------
# BankTransaction — frozen / strict / optional fitid
# ---------------------------------------------------------------------------


def _txn(**overrides: object) -> BankTransaction:
    base: dict[str, object] = {
        "external_ref": "ACC-1",
        "date": dt.date(2026, 1, 15),
        "amount_cents": -4250,
        "currency": "EUR",
        "payee": "Café",
        "description": "Déjeuner",
    }
    base.update(overrides)
    return BankTransaction(**base)  # type: ignore[arg-type]


def test_bank_transaction_is_frozen() -> None:
    t = _txn()
    with pytest.raises(ValidationError):
        t.amount_cents = 0  # type: ignore[misc]


def test_bank_transaction_strict_rejects_float_cents() -> None:
    # strict=True : un float monétaire est refusé (garde-fou ADR 0008 « jamais float »).
    with pytest.raises(ValidationError):
        _txn(amount_cents=12.34)


def test_bank_transaction_fitid_optional() -> None:
    assert _txn().fitid is None
    assert _txn(fitid="FIT-1").fitid == "FIT-1"


# ---------------------------------------------------------------------------
# decimal_euros_to_cents — example-based + property-based
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("euros", "cents"),
    [
        (Decimal("12.34"), 1234),
        (Decimal("-12.34"), -1234),
        (Decimal("0"), 0),
        (Decimal("-0.005"), -1),  # HALF_UP s'éloigne de zéro
        (Decimal("0.005"), 1),
        (Decimal("0.015"), 2),
    ],
)
def test_decimal_euros_to_cents_examples(euros: Decimal, cents: int) -> None:
    assert decimal_euros_to_cents(euros) == cents


@given(
    st.decimals(
        min_value=Decimal("-1e7"),
        max_value=Decimal("1e7"),
        places=2,
        allow_nan=False,
        allow_infinity=False,
    )
)
def test_decimal_euros_to_cents_is_deterministic_int(amount: Decimal) -> None:
    first = decimal_euros_to_cents(amount)
    assert isinstance(first, int)
    assert decimal_euros_to_cents(amount) == first  # déterminisme


@given(
    st.decimals(
        min_value=Decimal("-1e6"),
        max_value=Decimal("1e6"),
        places=3,
        allow_nan=False,
        allow_infinity=False,
    )
)
@example(Decimal("-0.005"))
@example(Decimal("0.005"))
@example(Decimal("0.015"))
def test_decimal_euros_to_cents_half_up(amount: Decimal) -> None:
    # places=3 atteint réellement le demi-centime (places=2 ne l'exerce jamais).
    expected = int((amount * 100).quantize(Decimal("1"), rounding="ROUND_HALF_UP"))
    assert decimal_euros_to_cents(amount) == expected


@given(st.integers(min_value=-(10**9), max_value=10**9))
def test_decimal_euros_to_cents_round_trip(cents: int) -> None:
    # Division Decimal exacte → l'arrondi est un no-op : round-trip exact.
    assert decimal_euros_to_cents(Decimal(cents) / 100) == cents


# ---------------------------------------------------------------------------
# ParsedOFX
# ---------------------------------------------------------------------------


def test_parsed_ofx_is_frozen() -> None:
    parsed = ParsedOFX(accounts=("A",), transactions=(_txn(),), encoding_confidence="high")
    with pytest.raises(AttributeError):
        parsed.accounts = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# BankingProviderError hierarchy — single `except BankingProviderError` at S12.4
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subclass",
    [IncompatibleAccountError, ProviderUnavailableError, EncodingDetectionError],
)
def test_error_family_subclassing(subclass: type[BankingProviderError]) -> None:
    assert issubclass(subclass, BankingProviderError)
