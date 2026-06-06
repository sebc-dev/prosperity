"""Unit tests for `transactions.events.TransactionEditableFieldsChangedEvent` (S11.1, P11.1.2).

Pins the event shape the overflow re-materialisation (S11.3) relies on: it is a
frozen `DomainEvent` carrying `transaction_id` and a `changed_fields` `frozenset`,
with value equality (`@dataclass(frozen=True)`). Gabarit
`TransactionConfirmedEvent`/`TransactionVoidedEvent`.
"""

from __future__ import annotations

import dataclasses
from uuid import uuid4

import pytest

from backend.modules.transactions.events import TransactionEditableFieldsChangedEvent
from backend.shared.events import DomainEvent


def test_is_domain_event() -> None:
    assert issubclass(TransactionEditableFieldsChangedEvent, DomainEvent)


def test_carries_transaction_id_and_changed_fields() -> None:
    tx_id = uuid4()
    event = TransactionEditableFieldsChangedEvent(
        transaction_id=tx_id, changed_fields=frozenset({"debt_generation_override"})
    )
    assert event.transaction_id == tx_id
    assert event.changed_fields == frozenset({"debt_generation_override"})
    assert isinstance(event.changed_fields, frozenset)


def test_value_equality() -> None:
    tx_id = uuid4()
    fields = frozenset({"debt_generation_override", "description"})
    assert TransactionEditableFieldsChangedEvent(
        transaction_id=tx_id, changed_fields=fields
    ) == TransactionEditableFieldsChangedEvent(transaction_id=tx_id, changed_fields=fields)


def test_is_frozen() -> None:
    event = TransactionEditableFieldsChangedEvent(
        transaction_id=uuid4(), changed_fields=frozenset()
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.transaction_id = uuid4()  # type: ignore[misc]
