"""Unit tests for the pure consumption domain (S08.2, P08.2.1).

Pins `consumption_from_totals` (the `remaining`/`percent` derivation) and the
`BudgetConsumption` immutability. No DB — pure-domain tier (Stratégie de tests
§4.1/§4.2). The SUM-over-subtree side lives at the service and is covered by the
integration tier (`test_budget_consumption.py`).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.modules.budget.domain import BudgetConsumption, consumption_from_totals


def test_consumption_from_totals_under_budget() -> None:
    c = consumption_from_totals(consumed_cents=5000, amount_cents=40000, splits_count=3)
    assert c.consumed_cents == 5000
    assert c.remaining_cents == 35000
    assert c.percent == Decimal("0.125")
    assert c.splits_count == 3


def test_consumption_from_totals_over_budget() -> None:
    # Dépassement : remaining négatif, percent > 1.
    c = consumption_from_totals(consumed_cents=45000, amount_cents=40000, splits_count=7)
    assert c.remaining_cents == -5000
    assert c.percent == Decimal("1.125")


def test_consumption_percent_not_prematurely_rounded() -> None:
    # `percent` conserve la précision Decimal du contexte (pas un arrondi à 2
    # décimales) — le formatage est une décision d'UI (D9).
    c = consumption_from_totals(consumed_cents=10000, amount_cents=30000, splits_count=1)
    assert c.percent != Decimal("0.33")
    assert c.percent == Decimal(10000) / Decimal(30000)


def test_consumption_zero_amount_guard() -> None:
    # amount <= 0 → percent forcé à 0 (pas de ZeroDivisionError).
    c = consumption_from_totals(consumed_cents=1000, amount_cents=0, splits_count=2)
    assert c.percent == Decimal("0")
    assert c.remaining_cents == -1000


def test_consumption_negative_amount_guard() -> None:
    c = consumption_from_totals(consumed_cents=0, amount_cents=-100, splits_count=0)
    assert c.percent == Decimal("0")


def test_consumption_zero_consumed() -> None:
    c = consumption_from_totals(consumed_cents=0, amount_cents=40000, splits_count=0)
    assert c.consumed_cents == 0
    assert c.remaining_cents == 40000
    assert c.percent == Decimal("0")
    assert c.splits_count == 0


def test_budget_consumption_is_frozen() -> None:
    c = consumption_from_totals(consumed_cents=1, amount_cents=2, splits_count=1)
    with pytest.raises(ValidationError):
        c.consumed_cents = 999  # type: ignore[misc]


def test_budget_consumption_is_strict() -> None:
    # strict=True : pas de coercition implicite int←float pour les *_cents.
    with pytest.raises(ValidationError):
        BudgetConsumption(
            consumed_cents=1.5,  # type: ignore[arg-type]
            remaining_cents=0,
            percent=Decimal("0"),
            splits_count=0,
        )
