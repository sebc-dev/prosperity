"""Public surface of the budget module — re-exports for cross-module use.

Première surface publique du module (S08.2) : la consommation budget est
consommée par les routes S08.4 (mapping `BudgetConsumption` → `Money`, RBAC,
drill-down) et, plus tard, par `debts`/F10 (E11). Les re-exports ci-dessous sont
**intra-module** (le contrat `2-budget` interdit aux *pairs* d'atteindre les
internals, pas à `public` lui-même), donc aucune exception import-linter n'est
requise pour eux.

S08.3 ajoute le détecteur de seuils : `on_transaction_confirmed` (le **handler**
du mini-bus, typé en duck-typing sur l'event — `budget` n'importe PAS
`transactions.public`) et `BudgetThresholdEvent` (le type publié). Le câblage
`subscribe_async(TransactionConfirmedEvent, on_transaction_confirmed)` vit au
**composition root** (`backend/main.py`), pas ici : `budget ⊥ transactions`
(pairs), donc `budget` ne peut pas connaître `TransactionConfirmedEvent`.

`categories` (S06) reste intra-module : elle est consommée via les routes du
module, pas re-exportée ici (aucun consommateur cross-module à ce jour).
"""

from __future__ import annotations

from backend.modules.budget.domain import BudgetConsumption, PeriodKind, Scope
from backend.modules.budget.events import (
    BudgetCreatedEvent,
    BudgetThresholdEvent,
    BudgetUpdatedEvent,
)
from backend.modules.budget.service.budget_crud import (
    archive_budget,
    create_budget,
    update_budget,
)
from backend.modules.budget.service.budgets import (
    BudgetWithConsumption,
    list_active_budgets_for_user,
)
from backend.modules.budget.service.categories import (
    archive_category,
    create_category,
    move_category,
    update_category,
)
from backend.modules.budget.service.consumption import (
    OverflowBudgetContext,
    compute_consumption,
    list_overflow_budget_ids_for_categories,
    list_overflow_recompute_tx_ids,
    resolve_overflow_context,
)
from backend.modules.budget.service.threshold_detector import on_transaction_confirmed

# The category + budget write surface is re-exported for the sync write upload
# handler (S13.4, delta D5 — `Category` AND `Budget` both live in `budget`, so a
# single handler covers both): the handler maps PowerSync `categories`/`budgets`
# mutations onto these acts and never reaches into `budget.{service,domain}` itself
# (ADR 0014 — public-surface-only). `PeriodKind`/`Scope` (the closed `Literal`s the
# create payload must carry) ride along on the existing `budget.domain` arc. The
# `2-sync` `ignore_imports` block carries the second-hop entries.
__all__ = [
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
]
