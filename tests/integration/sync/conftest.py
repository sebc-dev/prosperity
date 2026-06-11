"""Fixtures locales aux tests d'intégration du write upload handler (S13.4).

Le câblage des abonnés du mini-bus (`subscribe_async`) vit dans le `lifespan` de
`main.py` ; le tier d'intégration ne le déclenche pas. Les handlers `sync` appellent
des services métier qui `dispatch()` des events (confirm/void/edit → overflow ;
budget create/update → recompute), donc SANS ce câblage explicite les effets
d'abonnés (matérialisation overflow) seraient des FALSE-GREEN (aucun abonné →
`dispatch` no-op). La fixture autouse `_wire_sync_subscribers` reproduit le câblage
de `main.py` (gabarit `_wire_overflow`).

Note : `create_share_request` matérialise le `Debt` SYNCHRONIQUEMENT dans la
fonction (pas via le bus) — ce read-after-write reste fiable même sans cette
fixture. Le verrou de régression dédié de la matérialisation overflow est S13.5.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.modules.accounts.models import HOUSEHOLD_SINGLETON_UUID, Household
from backend.modules.accounts.service.household import invalidate_household_cache
from backend.modules.budget.events import BudgetCreatedEvent, BudgetUpdatedEvent
from backend.modules.budget.public import on_transaction_confirmed
from backend.modules.debts.public import (
    materialize_overflow,
    recompute_overflow_on_budget_event,
    rematerialize_overflow_on_edit,
    remove_overflow_on_void,
)
from backend.modules.transactions.events import (
    TransactionConfirmedEvent,
    TransactionEditableFieldsChangedEvent,
    TransactionVoidedEvent,
)
from backend.shared.events import clear_subscribers, subscribe_async


@pytest.fixture(autouse=True)
def _wire_sync_subscribers() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Re-câble sur le bus les abonnés que `main.py` enregistre au `lifespan`
    (le tier d'intégration ne lance pas le lifespan). `clear_subscribers()` d'abord
    (bus froid), de nouveau au teardown (état process-global, jamais de fuite)."""
    clear_subscribers()
    subscribe_async(TransactionConfirmedEvent, on_transaction_confirmed)
    subscribe_async(TransactionConfirmedEvent, materialize_overflow)
    subscribe_async(TransactionVoidedEvent, remove_overflow_on_void)
    subscribe_async(TransactionEditableFieldsChangedEvent, rematerialize_overflow_on_edit)
    subscribe_async(BudgetCreatedEvent, recompute_overflow_on_budget_event)
    subscribe_async(BudgetUpdatedEvent, recompute_overflow_on_budget_event)
    yield
    clear_subscribers()


@pytest_asyncio.fixture(loop_scope="session")
async def initialized_household(household_singleton: AsyncSession) -> AsyncSession:
    """Stamp `initialized_at` on the singleton (the base `household_singleton` leaves
    it NULL). Required by the acts that read `get_household` (`create_personal`/
    `create_shared`/`create_budget` — currency lock) ; the cache is invalidated so the
    next read sees the stamp. The transactional rollback removes it per test."""

    def _init(sync_session: Session) -> None:
        household = sync_session.get(Household, HOUSEHOLD_SINGLETON_UUID)
        assert household is not None
        household.initialized_at = datetime.now(UTC)

    await household_singleton.run_sync(_init)
    invalidate_household_cache()
    return household_singleton
