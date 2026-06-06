"""Integration tests for `TransactionEditableFieldsChangedEvent` emission (S11.1, P11.1.2).

Drives `update_editable_fields` against a real Postgres and asserts the mini-bus
spy behaviour the overflow re-materialisation (S11.3, P11.3.4) relies on:

* an editable field changing on a `confirmed` transaction emits exactly one event
  carrying `transaction_id` + the precise `changed_fields` set;
* NO event when nothing changes (idempotent edit), when the transaction is below
  `confirmed` (free-editing window — the `CONFIRMED` guard), or when a frozen
  field raises BEFORE the flush;
* an async subscriber runs inside the request transaction (proof the S11.3 handler
  can re-materialise in the same session).

No subscriber is wired in S11.1 — only spies (`debts` is wired at the composition
root in S11.3). Gabarit `test_transactions_transitions.py` (spy + `_clear_bus`).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Iterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.transactions import domain
from backend.modules.transactions.events import TransactionEditableFieldsChangedEvent
from backend.modules.transactions.models import Transaction as TxModel
from backend.modules.transactions.service.lifecycle import update_editable_fields
from backend.shared.events import clear_subscribers, subscribe, subscribe_async

Factories = tuple[type, type, type, type]
BoundFactories = Callable[[], Awaitable[Factories]]
CategoryMaker = Callable[..., Awaitable[object]]


@pytest.fixture(autouse=True)
def _clear_bus() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Empty the global mini-bus registry around every test (process-global state)."""
    clear_subscribers()
    yield
    clear_subscribers()


async def _seed_account(
    session: AsyncSession, bound: BoundFactories
) -> tuple[uuid.UUID, uuid.UUID]:
    user_factory, account_factory, _tx, _split = await bound()

    def _build(_sync: object) -> tuple[uuid.UUID, uuid.UUID]:
        user = user_factory()
        return account_factory(owner_id=user.id).id, user.id

    return await session.run_sync(_build)


async def _seed_tx(
    session: AsyncSession,
    bound: BoundFactories,
    *,
    account_id: uuid.UUID,
    user_id: uuid.UUID,
    state: str,
) -> uuid.UUID:
    """A balanced same-account pair in `state` (factory sets the column directly)."""
    _u, _a, tx_factory, _split = await bound()

    def _build(_sync: object) -> uuid.UUID:
        return tx_factory(account_id=account_id, created_by=user_id, state=state).id

    return await session.run_sync(_build)


# ---------------------------------------------------------------------------
# Emission on a confirmed transaction
# ---------------------------------------------------------------------------


async def test_override_change_emits_event(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    received: list[TransactionEditableFieldsChangedEvent] = []
    subscribe(TransactionEditableFieldsChangedEvent, received.append)
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="confirmed",
    )

    await update_editable_fields(
        household_singleton, tx_id=tx_id, debt_generation_override="force_full_debt"
    )

    assert len(received) == 1
    assert received[0].transaction_id == tx_id
    assert received[0].changed_fields == frozenset({"debt_generation_override"})


async def test_multiple_changed_fields_reported(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    received: list[TransactionEditableFieldsChangedEvent] = []
    subscribe(TransactionEditableFieldsChangedEvent, received.append)
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="confirmed",
    )

    await update_editable_fields(
        household_singleton,
        tx_id=tx_id,
        debt_generation_override="force_full_debt",
        description="vacances",
    )

    assert len(received) == 1
    assert received[0].changed_fields == frozenset({"debt_generation_override", "description"})


# ---------------------------------------------------------------------------
# No emission (idempotent edit, below confirmed, frozen field, terminal void)
# ---------------------------------------------------------------------------


async def test_no_event_when_value_unchanged(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    # The override already is `default` (factory default) → passing `default`
    # changes nothing → no emission ("not emitted if nothing changes", AC).
    received: list[TransactionEditableFieldsChangedEvent] = []
    subscribe(TransactionEditableFieldsChangedEvent, received.append)
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="confirmed",
    )

    await update_editable_fields(
        household_singleton, tx_id=tx_id, debt_generation_override="default"
    )

    assert received == []


async def test_no_event_when_tags_unchanged_as_list(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    # Passing `tags` as a `list` equal in VALUE to the stored `tuple` must NOT
    # emit: `changed` diffs `old` vs the domain rebuilt post-flush (`tuple(tx.tags)`
    # on both sides), so there is no spurious `list != tuple` positive. The initial
    # tag-set happens BEFORE subscribing so it does not pollute the spy.
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="confirmed",
    )
    await update_editable_fields(household_singleton, tx_id=tx_id, tags=("x", "y"))

    received: list[TransactionEditableFieldsChangedEvent] = []
    subscribe(TransactionEditableFieldsChangedEvent, received.append)

    await update_editable_fields(household_singleton, tx_id=tx_id, tags=["x", "y"])

    assert received == []


async def test_no_event_below_confirmed(
    household_singleton: AsyncSession,
    bound_transaction_factories: BoundFactories,
    bound_category_factory: CategoryMaker,
) -> None:
    # A `draft` transaction: editing an editable field is part of construction,
    # not a change of a frozen aggregate → the `CONFIRMED` guard suppresses the
    # event (no parasitic overflow re-materialisation while still building).
    received: list[TransactionEditableFieldsChangedEvent] = []
    subscribe(TransactionEditableFieldsChangedEvent, received.append)
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="draft",
    )
    cat = (await bound_category_factory()).id  # type: ignore[attr-defined]

    await update_editable_fields(household_singleton, tx_id=tx_id, category_id=cat)

    assert received == []


async def test_frozen_field_change_raises_before_emit(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    # `check_mutation_allowed` raises `ImmutableFieldViolation` BEFORE the flush
    # (and therefore before any `dispatch`) → the spy stays empty (raise-before-emit).
    received: list[TransactionEditableFieldsChangedEvent] = []
    subscribe(TransactionEditableFieldsChangedEvent, received.append)
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="confirmed",
    )

    with pytest.raises(domain.ImmutableFieldViolation):
        await update_editable_fields(household_singleton, tx_id=tx_id, account_id=uuid.uuid4())

    assert received == []


async def test_no_event_on_void(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    # `void` is terminal and below the `CONFIRMED` guard: editing an editable
    # field there (no `ImmutableFieldViolation` — the checker is a no-op outside
    # `confirmed`) emits NO event. Documents the absence of a parasitic trigger on
    # the terminal state.
    received: list[TransactionEditableFieldsChangedEvent] = []
    subscribe(TransactionEditableFieldsChangedEvent, received.append)
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="void",
    )

    await update_editable_fields(household_singleton, tx_id=tx_id, description="note")

    assert received == []


# ---------------------------------------------------------------------------
# Async channel — runs inside the request transaction
# ---------------------------------------------------------------------------


async def test_async_subscriber_runs_in_request_transaction(
    household_singleton: AsyncSession, bound_transaction_factories: BoundFactories
) -> None:
    # An ASYNC subscriber (the S11.3 channel) receives `(session, event)` during
    # the edit and runs INSIDE the request transaction: it reads the just-flushed
    # override through the very session it was handed (proof of same-tx → S11.3
    # can re-materialise).
    seen: list[tuple[bool, str]] = []

    async def _async_handler(
        session: AsyncSession, event: TransactionEditableFieldsChangedEvent
    ) -> None:
        override = (
            await session.execute(
                select(TxModel.debt_generation_override).where(TxModel.id == event.transaction_id)
            )
        ).scalar_one()
        seen.append((session is household_singleton, override))

    subscribe_async(TransactionEditableFieldsChangedEvent, _async_handler)
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="confirmed",
    )

    await update_editable_fields(
        household_singleton, tx_id=tx_id, debt_generation_override="force_full_debt"
    )

    assert seen == [(True, "force_full_debt")]
