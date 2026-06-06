"""Integration regression lock for the overflow F10 socle (S11.1, P11.1.1).

Pins, against a real Postgres, the couple the overflow mechanics rests on: on a
`confirmed` transaction the `debt_generation_override` toggles freely across the
whole enum, BUT a frozen financial field (`account_id`) is still refused
(anti-regression of the ADR 0001 freeze). The socle itself comes from E07/S07.4
— this is the E11-OWNED lock, distinct from the generic `update_editable_fields`
tests, so an F10-pointing failure surfaces if the override stops being editable
or the freeze leaks.

Rollback-isolated tier: the `seed_account`/`seed_tx` conftest fixtures build a
`confirmed` transaction (balanced same-account pair, state set directly).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.transactions import domain
from backend.modules.transactions.models import Transaction as TxModel
from backend.modules.transactions.service.lifecycle import update_editable_fields

SeedAccount = Callable[[], Awaitable[tuple[uuid.UUID, uuid.UUID]]]
SeedTx = Callable[..., Awaitable[uuid.UUID]]


async def test_override_togglable_post_confirmed_frozen_field_still_refused(
    household_singleton: AsyncSession,
    seed_account: SeedAccount,
    seed_tx: SeedTx,
) -> None:
    account_id, user_id = await seed_account()
    tx_id = await seed_tx(account_id=account_id, user_id=user_id, state="confirmed")

    # The three enum values all accepted on a `confirmed` transaction.
    for value in ("force_full_debt", "force_no_debt", "default"):
        after = await update_editable_fields(
            household_singleton, tx_id=tx_id, debt_generation_override=value
        )
        assert after.debt_generation_override == value

    # Persistence proof (not just the in-memory rebuild): the last value is
    # re-read straight from Postgres through the test session.
    persisted = (
        await household_singleton.execute(
            select(TxModel.debt_generation_override).where(TxModel.id == tx_id)
        )
    ).scalar_one()
    assert persisted == "default"

    # A frozen financial field is still refused (ADR 0001 freeze intact).
    with pytest.raises(domain.ImmutableFieldViolation) as exc:
        await update_editable_fields(household_singleton, tx_id=tx_id, account_id=uuid.uuid4())
    assert exc.value.field == "account_id"
