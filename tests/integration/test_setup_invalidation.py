"""Pin the `after_commit` cache invalidation contract of POST /setup (S03.2).

Four pinned invariants:

* Happy path → transaction commits → listener fires → cache cleared.
* Race-lost rollback → listener registered but txn rolled back →
  listener does NOT fire → cache untouched. **Load-bearing case** for
  the `after_commit`-only invalidation design: a precheck-locked 404
  would never register the listener in the first place, so the real
  invariant is "listener exists but doesn't fire on rollback".
* Precheck-locked 404 → no `initialize_bootstrap` call → no listener
  registered → cache untouched (lighter-weight version of the contract,
  documents the early-exit path).
* End-to-end → after a successful POST, `get_household()` from an
  independent session sees the real row (not None and not a stale
  sentinel).

Uses `committed_client` / `committed_sessionmaker` because the
`async_client` fixture wraps requests in SAVEPOINTs, which never fire
`after_commit` on the outer transaction.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.modules.accounts.models import Household
from backend.modules.accounts.public import get_household
from backend.modules.accounts.service import household as household_service
from backend.modules.accounts.service.household import (
    get_household_cache_for_testing,
    set_household_cache_for_testing,
)
from backend.modules.accounts.service.setup import initialize_bootstrap
from backend.modules.auth.models import User, UserRole

# `_clean_committed_db` truncates the schema before & after each test
# (cf. tests/integration/conftest.py); without it the committed-engine
# state would leak between tests.
pytestmark = [pytest.mark.usefixtures("_clean_committed_db")]


@pytest.fixture(autouse=True)
async def _reset_household_cache() -> AsyncIterator[None]:  # pyright: ignore[reportUnusedFunction]
    household_service.invalidate_household_cache()
    yield
    household_service.invalidate_household_cache()


def _setup_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "email": "admin@example.com",
        "password": "correct-horse-battery-staple",
        "display_name": "Admin",
        "household_name": "Foyer Dupont",
    }
    base.update(overrides)
    return base


def _sentinel_household() -> Household:
    return Household(
        name="STALE",
        base_currency="EUR",
        initialized_at=datetime.now(tz=UTC),
    )


async def test_post_setup_invalidates_cache_after_commit(
    committed_client: AsyncClient,
) -> None:
    """Happy path: after a real commit, the listener fires and the cache is None."""
    sentinel = _sentinel_household()
    set_household_cache_for_testing(sentinel)
    assert get_household_cache_for_testing() is sentinel

    resp = await committed_client.post("/setup", json=_setup_payload())
    assert resp.status_code == 200

    # Listener fired post-commit → cache cleared. The next call to
    # `get_household()` will re-read from DB.
    assert get_household_cache_for_testing() is None


async def test_initialize_bootstrap_rollback_does_not_fire_listener(
    committed_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Load-bearing race-lost contract: listener registered → rollback → cache survives.

    Direct-call variant of the race-lost branch the route catches at
    `http.py` `except DBAPIError`. We invoke `initialize_bootstrap`
    (which registers the `after_commit` listener and persists the
    pending writes), then roll back without committing — emulating the
    `get_db` dependency rolling back on the 404 exception. The
    invariant under test:

      1. The listener IS registered (otherwise the test is vacuously
         true). Asserted via the listener count on `dispatch.after_commit`.
      2. The rollback does NOT fire the listener → cache state from
         before the failed setup survives untouched.

    The precheck-locked 404 test below covers a different (lighter)
    path where `initialize_bootstrap` is never called at all; this test
    pins the **dangerous** case where the listener was registered.
    """
    sentinel = _sentinel_household()
    set_household_cache_for_testing(sentinel)

    async with committed_sessionmaker() as session:
        listeners_before = len(session.sync_session.dispatch.after_commit)
        await initialize_bootstrap(
            session,
            email="admin@example.com",
            password="correct-horse-battery-staple",
            display_name="Admin",
            household_name="Foyer Test",
        )
        listeners_after = len(session.sync_session.dispatch.after_commit)
        # Without this guard, a regression that silently drops the
        # listener registration would make the rollback assertion below
        # trivially true.
        assert listeners_after == listeners_before + 1, (
            "initialize_bootstrap must register exactly one after_commit listener"
        )
        await session.rollback()

    # Listener was registered but never fired (rollback path) → cache
    # state from before the failed setup survives.
    assert get_household_cache_for_testing() is sentinel


async def test_post_setup_precheck_locked_does_not_invalidate_cache(
    committed_client: AsyncClient,
    committed_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Precheck-locked 404 → `initialize_bootstrap` never called → cache untouched.

    Lighter-weight than the race-lost test above: the precheck rejects
    before any DB write, so no listener is ever registered. Documents
    that the early-exit path also leaves cache state intact.
    """
    # Pre-init the household + a user so the precheck fails.
    async with committed_sessionmaker() as session:
        session.add(
            Household(
                name="Existing",
                base_currency="EUR",
                initialized_at=datetime.now(tz=UTC),
            )
        )
        session.add(
            User(
                email="existing@example.com",
                password_hash="x" * 60,
                display_name="Existing",
                role=UserRole.ADMIN,
            )
        )
        await session.commit()

    # Prime the cache with a sentinel; if invalidation fires it'll go to None.
    sentinel = _sentinel_household()
    set_household_cache_for_testing(sentinel)

    resp = await committed_client.post("/setup", json=_setup_payload())
    assert resp.status_code == 404

    # Precheck rejected before the write → listener never registered →
    # nothing to fire → cache survives.
    assert get_household_cache_for_testing() is sentinel


async def test_get_household_post_setup_returns_initialized_row(
    committed_client: AsyncClient,
    committed_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """End-to-end: post-`/setup`, a fresh `get_household()` sees the row.

    Pre-seeding the cache with a `STALE` sentinel is what makes this test
    non-tautological: an empty cache would also pass the post-POST read
    by going straight to the DB. By forcing the cache to a wrong value
    *before* the POST, we prove the `after_commit` listener actually
    replaced it — `get_household()` must return the freshly-committed
    "Foyer Dupont", not the stale sentinel still sitting in the slot.
    """
    sentinel = _sentinel_household()
    set_household_cache_for_testing(sentinel)
    assert get_household_cache_for_testing() is sentinel

    resp = await committed_client.post("/setup", json=_setup_payload())
    assert resp.status_code == 200

    # Cache slot was cleared by the `after_commit` listener; `get_household`
    # repopulates it from the just-committed row.
    assert get_household_cache_for_testing() is None

    async with committed_sessionmaker() as session:
        h = await get_household(session)
        assert h.name == "Foyer Dupont"
        assert h.initialized_at is not None
        # If the listener had failed to clear the slot, this would be
        # the `STALE` sentinel name instead of the real row.
        assert h.name != "STALE"
