"""Integration regression lock for the overflow F10 socle (S11.1, P11.1.1).

Pins, against a real Postgres, the couple the overflow mechanics rests on: on a
`confirmed` transaction the `debt_generation_override` toggles freely across the
whole enum, BUT a frozen financial field (`account_id`) is still refused
(anti-regression of the ADR 0001 freeze). The socle itself comes from E07/S07.4
— this is the E11-OWNED lock, distinct from the generic `update_editable_fields`
tests, so an F10-pointing failure surfaces if the override stops being editable
or the freeze leaks.

Rollback-isolated tier (`bound_transaction_factories`): a `confirmed` transaction
is built by the factory (balanced same-account pair, state set directly).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.transactions import domain
from backend.modules.transactions.service.lifecycle import update_editable_fields

Factories = tuple[type, type, type, type]
BoundFactories = Callable[[], Awaitable[Factories]]


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


async def test_override_togglable_post_confirmed_frozen_field_still_refused(
    household_singleton: AsyncSession,
    bound_transaction_factories: BoundFactories,
) -> None:
    account_id, user_id = await _seed_account(household_singleton, bound_transaction_factories)
    tx_id = await _seed_tx(
        household_singleton,
        bound_transaction_factories,
        account_id=account_id,
        user_id=user_id,
        state="confirmed",
    )

    # The three enum values all accepted on a `confirmed` transaction (the return
    # value carries the persisted override).
    for value in ("force_full_debt", "force_no_debt", "default"):
        after = await update_editable_fields(
            household_singleton, tx_id=tx_id, debt_generation_override=value
        )
        assert after.debt_generation_override == value

    # A frozen financial field is still refused (ADR 0001 freeze intact).
    with pytest.raises(domain.ImmutableFieldViolation) as exc:
        await update_editable_fields(household_singleton, tx_id=tx_id, account_id=uuid.uuid4())
    assert exc.value.field == "account_id"
