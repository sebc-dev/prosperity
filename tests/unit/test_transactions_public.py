"""Unit tests for `backend.modules.transactions.public` cross-module surface (S07.4, P07.4.4).

Pins the exact `__all__`, the re-export identities (guards against a refactor that
re-implements a stub in `public.py` instead of re-exporting the real symbols),
and the error/event subclassing the route boundary (S07.5) relies on.
Gabarit `test_accounts_public.py`.
"""

from __future__ import annotations

import backend.modules.transactions.public as transactions_public
from backend.modules.transactions import domain as _domain
from backend.modules.transactions import events as _events
from backend.modules.transactions.public import (
    ImmutableFieldViolation,
    InvalidStateTransitionError,
    MultipleFundingLegsError,
    SplitNotFoundError,
    TransactionConfirmedEvent,
    TransactionError,
    TransactionNotFoundError,
    TransactionState,
    TransactionVoidedEvent,
    UnbalancedTransactionError,
    UncategorizedExpenseError,
    add_split,
    create_draft,
    get_transaction,
    is_transfer,
    list_transactions,
    remove_split,
    transition_to_confirmed,
    transition_to_planned,
    update_editable_fields,
    void,
)
from backend.modules.transactions.service import lifecycle as _lifecycle
from backend.modules.transactions.service import queries as _queries
from backend.shared.events import DomainEvent

_EXPECTED = {
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
    "is_transfer",
    "list_transactions",
    "remove_split",
    "transition_to_confirmed",
    "transition_to_planned",
    "update_editable_fields",
    "void",
}


def test_public_exports_exact_set() -> None:
    assert set(transactions_public.__all__) == _EXPECTED


def test_service_functions_are_identical_re_exports() -> None:
    assert create_draft is _lifecycle.create_draft
    assert add_split is _lifecycle.add_split
    assert remove_split is _lifecycle.remove_split
    assert transition_to_planned is _lifecycle.transition_to_planned
    assert transition_to_confirmed is _lifecycle.transition_to_confirmed
    assert update_editable_fields is _lifecycle.update_editable_fields
    assert void is _lifecycle.void
    assert get_transaction is _queries.get_transaction
    assert list_transactions is _queries.list_transactions
    assert is_transfer is _domain.is_transfer


def test_errors_and_state_are_identical_re_exports() -> None:
    assert TransactionNotFoundError is _lifecycle.TransactionNotFoundError
    assert SplitNotFoundError is _lifecycle.SplitNotFoundError
    assert TransactionError is _domain.TransactionError
    assert ImmutableFieldViolation is _domain.ImmutableFieldViolation
    assert InvalidStateTransitionError is _domain.InvalidStateTransitionError
    assert UnbalancedTransactionError is _domain.UnbalancedTransactionError
    assert UncategorizedExpenseError is _domain.UncategorizedExpenseError
    assert MultipleFundingLegsError is _domain.MultipleFundingLegsError
    assert TransactionState is _domain.TransactionState


def test_events_are_identical_re_exports() -> None:
    assert TransactionConfirmedEvent is _events.TransactionConfirmedEvent
    assert TransactionVoidedEvent is _events.TransactionVoidedEvent


def test_service_errors_subclass_transaction_error() -> None:
    # The boundary maps the whole family with a single `except TransactionError`.
    assert issubclass(TransactionNotFoundError, TransactionError)
    assert issubclass(SplitNotFoundError, TransactionError)


def test_event_types_are_domain_events() -> None:
    for event_type in (TransactionConfirmedEvent, TransactionVoidedEvent):
        assert issubclass(event_type, DomainEvent)
