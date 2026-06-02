"""Public surface of the budget module — re-exports for cross-module use.

Première surface publique du module (S08.2) : la consommation budget est
consommée par les routes S08.4 (mapping `BudgetConsumption` → `Money`, RBAC,
drill-down) et, plus tard, par `debts`/F10 (E11). Les re-exports ci-dessous sont
**intra-module** (le contrat `2-budget` interdit aux *pairs* d'atteindre les
internals, pas à `public` lui-même), donc aucune exception import-linter n'est
requise pour eux.

`categories` (S06) reste intra-module : elle est consommée via les routes du
module, pas re-exportée ici (aucun consommateur cross-module à ce jour).
"""

from __future__ import annotations

from backend.modules.budget.domain import BudgetConsumption
from backend.modules.budget.service.budgets import (
    BudgetWithConsumption,
    list_active_budgets_for_user,
)
from backend.modules.budget.service.consumption import compute_consumption

__all__ = [
    "BudgetConsumption",
    "BudgetWithConsumption",
    "compute_consumption",
    "list_active_budgets_for_user",
]
