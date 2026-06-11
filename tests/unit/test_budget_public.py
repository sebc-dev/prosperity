"""Unit tests for `backend.modules.budget.public` cross-module surface (S08.2, P08.2.3).

Pins the exact `__all__` and the re-export identities — guards against a refactor
that re-implements a stub in `public.py` instead of re-exporting the real
symbols. First public surface of the budget module. Gabarit
`test_transactions_public.py` / `test_accounts_public.py`.
"""

from __future__ import annotations

import backend.modules.budget.public as budget_public
from backend.modules.budget import domain as _domain
from backend.modules.budget import events as _events
from backend.modules.budget.public import (
    BudgetConsumption,
    BudgetCreatedEvent,
    BudgetThresholdEvent,
    BudgetUpdatedEvent,
    BudgetWithConsumption,
    OverflowBudgetContext,
    archive_budget,
    archive_category,
    compute_consumption,
    create_budget,
    create_category,
    list_active_budgets_for_user,
    list_overflow_budget_ids_for_categories,
    list_overflow_recompute_tx_ids,
    move_category,
    on_transaction_confirmed,
    resolve_overflow_context,
    update_budget,
    update_category,
)
from backend.modules.budget.service import budget_crud as _budget_crud
from backend.modules.budget.service import budgets as _budgets
from backend.modules.budget.service import categories as _categories
from backend.modules.budget.service import consumption as _consumption
from backend.modules.budget.service import threshold_detector as _threshold_detector

_EXPECTED = {
    "BudgetConsumption",
    "BudgetCreatedEvent",
    "BudgetThresholdEvent",
    "BudgetUpdatedEvent",
    "BudgetWithConsumption",
    "OverflowBudgetContext",
    "PeriodKind",
    "Scope",
    "archive_budget",
    "archive_category",
    "compute_consumption",
    "create_budget",
    "create_category",
    "list_active_budgets_for_user",
    "list_overflow_budget_ids_for_categories",
    "list_overflow_recompute_tx_ids",
    "move_category",
    "on_transaction_confirmed",
    "resolve_overflow_context",
    "update_budget",
    "update_category",
}


def test_public_exports_exact_set() -> None:
    assert set(budget_public.__all__) == _EXPECTED


def test_public_names_are_identical_re_exports() -> None:
    # L'identité `is` garantit déjà la nature (type/callable) des symboles
    # ré-exportés : un test `callable()`/`isinstance(..., type)` séparé serait
    # tautologique, on ne le double pas.
    assert BudgetConsumption is _domain.BudgetConsumption
    assert compute_consumption is _consumption.compute_consumption
    assert list_active_budgets_for_user is _budgets.list_active_budgets_for_user
    assert BudgetWithConsumption is _budgets.BudgetWithConsumption
    assert BudgetThresholdEvent is _events.BudgetThresholdEvent
    assert on_transaction_confirmed is _threshold_detector.on_transaction_confirmed
    assert resolve_overflow_context is _consumption.resolve_overflow_context
    assert OverflowBudgetContext is _consumption.OverflowBudgetContext
    assert BudgetCreatedEvent is _events.BudgetCreatedEvent
    assert BudgetUpdatedEvent is _events.BudgetUpdatedEvent
    assert list_overflow_recompute_tx_ids is _consumption.list_overflow_recompute_tx_ids
    assert (
        list_overflow_budget_ids_for_categories
        is _consumption.list_overflow_budget_ids_for_categories
    )
    # S13.4 write surface (categories + budgets) consumed by the sync handlers.
    assert create_category is _categories.create_category
    assert move_category is _categories.move_category
    assert update_category is _categories.update_category
    assert archive_category is _categories.archive_category
    assert create_budget is _budget_crud.create_budget
    assert update_budget is _budget_crud.update_budget
    assert archive_budget is _budget_crud.archive_budget
