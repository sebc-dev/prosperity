"""Unit tests for `backend.modules.budget.public` cross-module surface (S08.2, P08.2.3).

Pins the exact `__all__` and the re-export identities — guards against a refactor
that re-implements a stub in `public.py` instead of re-exporting the real
symbols. First public surface of the budget module. Gabarit
`test_transactions_public.py` / `test_accounts_public.py`.
"""

from __future__ import annotations

import backend.modules.budget.public as budget_public
from backend.modules.budget import domain as _domain
from backend.modules.budget.public import (
    BudgetConsumption,
    BudgetWithConsumption,
    compute_consumption,
    list_active_budgets_for_user,
)
from backend.modules.budget.service import budgets as _budgets
from backend.modules.budget.service import consumption as _consumption

_EXPECTED = {
    "BudgetConsumption",
    "BudgetWithConsumption",
    "compute_consumption",
    "list_active_budgets_for_user",
}


def test_public_exports_exact_set() -> None:
    assert set(budget_public.__all__) == _EXPECTED


def test_public_names_are_identical_re_exports() -> None:
    assert BudgetConsumption is _domain.BudgetConsumption
    assert compute_consumption is _consumption.compute_consumption
    assert list_active_budgets_for_user is _budgets.list_active_budgets_for_user
    assert BudgetWithConsumption is _budgets.BudgetWithConsumption


def test_public_symbols_are_callable_or_types() -> None:
    assert callable(compute_consumption)
    assert callable(list_active_budgets_for_user)
    assert isinstance(BudgetConsumption, type)
    assert isinstance(BudgetWithConsumption, type)
