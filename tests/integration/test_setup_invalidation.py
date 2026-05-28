"""Pin the `after_commit` cache invalidation contract of POST /setup (S03.2).

Three pinned invariants:

* Happy path → transaction commits → listener fires → cache cleared.
* Lock-after-init path → 404 → no transaction write → cache untouched.
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
    household_service._household_cache = sentinel  # pyright: ignore[reportPrivateUsage]
    assert household_service._household_cache is sentinel  # pyright: ignore[reportPrivateUsage]

    resp = await committed_client.post("/setup", json=_setup_payload())
    assert resp.status_code == 200

    # Listener fired post-commit → cache cleared. The next call to
    # `get_household()` will re-read from DB.
    assert household_service._household_cache is None  # pyright: ignore[reportPrivateUsage]


async def test_post_setup_does_not_invalidate_cache_on_rollback(
    committed_client: AsyncClient,
    committed_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Pre-existing init → precheck 404 → no transaction → cache preserved."""
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
    household_service._household_cache = sentinel  # pyright: ignore[reportPrivateUsage]

    resp = await committed_client.post("/setup", json=_setup_payload())
    assert resp.status_code == 404

    # Listener never registered (precheck rejected before the write) →
    # nothing to fire on rollback → cache survives.
    assert household_service._household_cache is sentinel  # pyright: ignore[reportPrivateUsage]


async def test_get_household_post_setup_returns_initialized_row(
    committed_client: AsyncClient,
    committed_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """End-to-end: post-`/setup`, a fresh `get_household()` sees the row.

    Critical because the cached `_household_cache` is process-local
    (cf. `accounts.service.household` docstring): if the listener
    hadn't cleared it, this fresh session would see whatever the
    sentinel was — None included.
    """
    resp = await committed_client.post("/setup", json=_setup_payload())
    assert resp.status_code == 200

    async with committed_sessionmaker() as session:
        h = await get_household(session)
        assert h.name == "Foyer Dupont"
        assert h.initialized_at is not None
