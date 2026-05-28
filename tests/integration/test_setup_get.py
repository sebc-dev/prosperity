"""Integration tests for `GET /setup` (S03.2 P03.2.1).

Pins the lock-after-init contract on the probe endpoint: 200 only when
the deployment is truly empty (no users AND no household row), 404
otherwise.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.models import Household
from backend.modules.accounts.service.household import invalidate_household_cache
from backend.modules.auth.models import User, UserRole


@pytest.fixture(autouse=True)
def _reset_household_cache() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Per-test cache reset — same rationale as `test_accounts_household`."""
    invalidate_household_cache()
    yield
    invalidate_household_cache()


async def test_get_setup_returns_200_when_db_empty(
    async_client: AsyncClient,
    auth_schema: AsyncSession,  # noqa: ARG001 — fixture materialises schema in the request connection
) -> None:
    resp = await async_client.get("/setup")
    assert resp.status_code == 200
    assert resp.json() == {"status": "open"}


async def test_get_setup_sets_no_store_cache_headers(
    async_client: AsyncClient,
    auth_schema: AsyncSession,  # noqa: ARG001
) -> None:
    resp = await async_client.get("/setup")
    assert resp.status_code == 200
    assert resp.headers.get("Cache-Control") == "no-store"
    assert resp.headers.get("Pragma") == "no-cache"


async def test_get_setup_returns_404_when_user_exists(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
) -> None:
    auth_schema.add(
        User(
            email="existing@example.com",
            password_hash="x" * 60,
            display_name="Existing",
            role=UserRole.ADMIN,
        )
    )
    await auth_schema.flush()
    resp = await async_client.get("/setup")
    assert resp.status_code == 404


async def test_get_setup_returns_404_when_household_initialized(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
) -> None:
    auth_schema.add(
        Household(
            name="Foyer",
            base_currency="EUR",
            initialized_at=datetime.now(tz=UTC),
        )
    )
    await auth_schema.flush()
    resp = await async_client.get("/setup")
    assert resp.status_code == 404


async def test_get_setup_returns_404_when_household_row_exists_even_uninitialized(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
) -> None:
    """Pin the durci semantics of `is_setup_open` (cf. addendum Q8).

    `is_setup_open` returns False as soon as the singleton row exists,
    independent of `initialized_at`. The "row + initialized_at NULL"
    state cannot arise from the production flow — only out-of-band SQL
    by a sysop can produce it, and the prescribed recovery is
    `DELETE FROM household`. Locking the probe at 404 guarantees
    GET/POST consistency (a 200 followed by a 404 on POST due to PK
    violation would be a worse UX).
    """
    auth_schema.add(Household(name="Stuck", base_currency="EUR"))  # initialized_at NULL
    await auth_schema.flush()
    resp = await async_client.get("/setup")
    assert resp.status_code == 404


async def test_get_setup_returns_404_when_both_user_and_household_present(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
) -> None:
    auth_schema.add(
        Household(
            name="Foyer",
            base_currency="EUR",
            initialized_at=datetime.now(tz=UTC),
        )
    )
    auth_schema.add(
        User(
            email="present@example.com",
            password_hash="x" * 60,
            display_name="Present",
            role=UserRole.ADMIN,
        )
    )
    await auth_schema.flush()
    resp = await async_client.get("/setup")
    assert resp.status_code == 404
