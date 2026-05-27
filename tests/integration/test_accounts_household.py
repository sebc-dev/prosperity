"""Integration tests for `accounts.public.get_household` (S03.1).

Covers the four observable states of `get_household()` — row absent,
row present but `initialized_at` NULL, fully initialised, and cache hit
— plus the detach contract (cached object survives session close) and
the explicit `invalidate_household_cache` knob used by S03.2 after
`/setup` commits.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.models import Household
from backend.modules.accounts.public import HouseholdNotInitializedError, get_household
from backend.modules.accounts.service.household import invalidate_household_cache


@pytest.fixture(autouse=True)
def _reset_household_cache() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Each test starts and ends with a cold cache.

    The cache lives in a module-level variable, so it survives the
    per-test transactional rollback that resets the DB. Without this
    fixture, a test that primes the cache would leak the cached
    `Household` into the next test that expects a cache miss.
    """
    invalidate_household_cache()
    yield
    invalidate_household_cache()


async def test_raises_when_row_absent(auth_schema: AsyncSession) -> None:
    with pytest.raises(HouseholdNotInitializedError):
        await get_household(auth_schema)


async def test_raises_when_initialized_at_is_null(auth_schema: AsyncSession) -> None:
    auth_schema.add(Household(name="Foyer", base_currency="EUR"))
    await auth_schema.flush()
    with pytest.raises(HouseholdNotInitializedError):
        await get_household(auth_schema)


async def test_returns_singleton_when_initialized(auth_schema: AsyncSession) -> None:
    h = Household(
        name="Famille Dupont",
        base_currency="EUR",
        initialized_at=datetime.now(tz=UTC),
    )
    auth_schema.add(h)
    await auth_schema.flush()
    result = await get_household(auth_schema)
    assert result.id == h.id
    assert result.name == "Famille Dupont"
    assert result.base_currency == "EUR"
    assert result.initialized_at is not None


async def test_second_call_hits_cache(
    auth_schema: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth_schema.add(
        Household(
            name="X",
            base_currency="EUR",
            initialized_at=datetime.now(tz=UTC),
        )
    )
    await auth_schema.flush()

    first = await get_household(auth_schema)

    # Subvert `session.get` to prove the 2nd call doesn't hit the DB:
    # if the cache is bypassed, this stub raises immediately.
    async def _exploding_get(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("session.get should not be called when cache is hot")

    monkeypatch.setattr(auth_schema, "get", _exploding_get)
    second = await get_household(auth_schema)
    assert second is first  # same detached ORM object


async def test_invalidate_forces_db_reread(auth_schema: AsyncSession) -> None:
    auth_schema.add(
        Household(
            name="X",
            base_currency="EUR",
            initialized_at=datetime.now(tz=UTC),
        )
    )
    await auth_schema.flush()

    first = await get_household(auth_schema)
    invalidate_household_cache()
    second = await get_household(auth_schema)
    # New ORM object instance — different identity, same id.
    assert second is not first
    assert second.id == first.id


async def test_returned_object_survives_session_close(auth_schema: AsyncSession) -> None:
    # `expunge` detaches the cached object so attribute access remains
    # safe after the session that loaded it is closed/rolled back.
    auth_schema.add(
        Household(
            name="Detached",
            base_currency="EUR",
            initialized_at=datetime.now(tz=UTC),
        )
    )
    await auth_schema.flush()
    h = await get_household(auth_schema)
    await auth_schema.close()
    # No DetachedInstanceError because no lazy-load is triggered
    # (the model declares no relationships).
    assert h.name == "Detached"
