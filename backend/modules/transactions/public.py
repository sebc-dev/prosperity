"""Public surface of the transactions module — re-exports for cross-module use.

This module is the only one in `backend.modules.transactions` that other modules
may import from. The import-linter contract `2-transactions` forbids any
cross-module import that reaches into
`backend.modules.transactions.{service,models,domain,...}`. The re-exports below
are all **intra-module** (the contract bars *peers* from reaching the internals,
not `public` itself), so no new exception is needed.

Exposes the lifecycle service functions, the concrete domain events, the
`TransactionState` enum + the typed error taxonomy — everything the S07.5 route
boundary needs to drive the aggregate and map failures to HTTP.
"""

from __future__ import annotations

from backend.modules.transactions.domain import (
    ImmutableFieldViolation,
    InvalidStateTransitionError,
    MultipleFundingLegsError,
    TransactionError,
    TransactionState,
    UnbalancedTransactionError,
    UncategorizedExpenseError,
)
from backend.modules.transactions.events import (
    TransactionConfirmedEvent,
    TransactionVoidedEvent,
)
from backend.modules.transactions.service.lifecycle import (
    SplitNotFoundError,
    TransactionNotFoundError,
    add_split,
    create_draft,
    remove_split,
    transition_to_confirmed,
    transition_to_planned,
    update_editable_fields,
    void,
)
from backend.modules.transactions.service.queries import get_transaction, list_transactions

__all__ = [
    "ImmutableFieldViolation",
    "InvalidStateTransitionError",
    "MultipleFundingLegsError",
    "SplitNotFoundError",
    "TransactionConfirmedEvent",
    "TransactionError",
    "TransactionNotFoundError",
    "TransactionState",
    "TransactionVoidedEvent",
    "UnbalancedTransactionError",
    "UncategorizedExpenseError",
    "add_split",
    "create_draft",
    "get_transaction",
    "list_transactions",
    "remove_split",
    "transition_to_confirmed",
    "transition_to_planned",
    "update_editable_fields",
    "void",
]
