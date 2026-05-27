"""Integration tests for the `household` CHECK constraint (S03.1).

The snapshot test in `test_migrations_schema.py` proves the CHECK
constraint *exists* in the migrated schema; these tests prove it
actually *fires* at the runtime engine level — a CHECK declared but
silently disabled (e.g. by a future `NOT VALID` slip-up) would pass
the snapshot but fail here.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.models import HOUSEHOLD_SINGLETON_UUID, Household


async def test_insert_with_wrong_uuid_violates_check(
    auth_schema: AsyncSession,
) -> None:
    bogus = Household(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        name="Bogus",
        base_currency="EUR",
    )
    auth_schema.add(bogus)
    with pytest.raises(IntegrityError):
        await auth_schema.flush()


async def test_insert_with_singleton_uuid_succeeds(
    auth_schema: AsyncSession,
) -> None:
    household = Household(name="Famille Test", base_currency="EUR")
    auth_schema.add(household)
    await auth_schema.flush()
    assert household.id == HOUSEHOLD_SINGLETON_UUID
    # `initialized_at` defaults NULL until `/setup` runs (S03.2).
    assert household.initialized_at is None
    assert household.created_at is not None


async def test_second_insert_with_same_uuid_violates_pk(
    auth_schema: AsyncSession,
) -> None:
    auth_schema.add(Household(name="First", base_currency="EUR"))
    await auth_schema.flush()
    auth_schema.add(Household(name="Second", base_currency="EUR"))
    with pytest.raises(IntegrityError):
        await auth_schema.flush()


async def test_initialized_at_can_be_set_post_insert(
    auth_schema: AsyncSession,
) -> None:
    # Mirrors the S03.2 flow: row created in step 1, initialized_at set
    # in step 2 of the same transaction (with the first admin user).
    h = Household(name="Foyer", base_currency="EUR")
    auth_schema.add(h)
    await auth_schema.flush()
    h.initialized_at = datetime.now(tz=UTC)
    await auth_schema.flush()
    assert h.initialized_at is not None
