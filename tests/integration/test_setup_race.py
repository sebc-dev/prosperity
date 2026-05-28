"""Concurrency tests for POST /setup (S03.2 P03.2.3).

Two distinct race windows coexist on the route; each exercises a
different code path. Both are pinned via dedicated tests so a
regression on one cannot hide behind the other.

* **After commit of the winner**: the loser starts its precheck after the
  winner committed, `is_setup_open` returns False, 404 direct from the
  route, no `IntegrityError` ever raised.
* **Before commit of the winner**: both sessions pass `is_setup_open`,
  both call `initialize_bootstrap`, PK violation on the loser at
  `flush()` surfaces as `IntegrityError(sqlstate=23505)`, the catch
  arm in the route returns 404.

Test 1 (`naive_gather`) — `asyncio.gather` two requests without
coordination; assert the terminal invariant (1×200 + 1×404). The
scheduler picks which window is exercised, so this test does not pin a
specific code path on its own.

Test 2 (`forced_race`) — monkey-patch `is_setup_open` with an
`asyncio.Barrier` that releases both racers only *after* both have
finished their precheck, forcing the IntegrityError window
deterministically. Pins the SQLSTATE-23505 catch arm via log
assertions.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.config import get_settings
from backend.modules.accounts.models import Household
from backend.modules.accounts.service import household as household_service
from backend.modules.accounts.service import setup as setup_service
from backend.modules.auth.models import User
from backend.modules.auth.service.jwt import verify_access_token

# Truncate Base.metadata tables before & after each test on the
# module-scoped `committed_engine`. Without this the second test
# would see leftover rows from the first.
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


async def test_two_concurrent_post_setup_one_wins_one_404(
    committed_client: AsyncClient,
    committed_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Naive `gather`: scheduler decides the window; assert terminal invariants.

    Typically the post-commit window is exercised (precheck → 404 direct),
    but the IntegrityError window can also fire depending on the loop's
    scheduling — both code paths satisfy this test. The forced-race
    variant below pins the IntegrityError window explicitly.
    """
    # `wait_for` guards against a future regression that leaves one of
    # the requests blocked (e.g. a hanging lock on the singleton row) —
    # without the timeout the suite would hang instead of failing fast.
    responses = await asyncio.wait_for(
        asyncio.gather(
            committed_client.post("/setup", json=_setup_payload(email="alice@example.com")),
            committed_client.post("/setup", json=_setup_payload(email="bob@example.com")),
        ),
        timeout=10.0,
    )
    statuses = sorted(r.status_code for r in responses)
    # Strict outcome contract: one 200, one 404. No 500 leakage and no
    # double-success.
    assert statuses == [200, 404], (
        f"unexpected race outcome: {statuses}; bodies: {[r.text for r in responses]}"
    )

    # Identify the winner and decode its access token. Catches an
    # admin-identity-swap regression where the 200 responder's token
    # would name a user different from the one actually persisted (e.g.
    # if a future refactor flushed both rows then 500'd the loser late).
    winner = next(r for r in responses if r.status_code == 200)
    settings = get_settings()
    token_sub = verify_access_token(winner.json()["access_token"], settings=settings)

    # Post-race DB state: exactly one household + one user (the winner).
    async with committed_sessionmaker() as session:
        users = (await session.execute(select(User))).scalars().all()
        household_count = (
            await session.execute(select(func.count()).select_from(Household))
        ).scalar_one()
    assert len(users) == 1
    assert household_count == 1
    # The surviving admin's id MUST match the 200 responder's token
    # `sub` — same user from end to end.
    assert users[0].id == token_sub


async def test_concurrent_post_setup_with_barrier_hits_integrity_error_branch(
    committed_client: AsyncClient,
    committed_sessionmaker: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Forced race: both racers pass precheck simultaneously → PK violation on loser.

    The barrier monkey-patched onto `is_setup_open` makes both racers
    complete their precheck before either calls `initialize_bootstrap`.
    The loser then hits the PK violation in `flush()`, surfacing as
    `IntegrityError(sqlstate=23505)` — pinned via log assertions.
    """
    barrier = asyncio.Barrier(2)
    original_is_open = setup_service.is_setup_open

    async def _coordinated_is_open(session: AsyncSession) -> bool:
        result = await original_is_open(session)
        # Both racers wait here AFTER the precheck so neither has
        # committed yet when the other moves to `initialize_bootstrap`.
        await barrier.wait()
        return result

    # Patch the symbol where the route imported it from (FastAPI route
    # binds `is_setup_open` at import time, so monkey-patching the
    # source module wouldn't affect it).
    with (
        patch(
            "backend.modules.accounts.transports.http.is_setup_open",
            side_effect=_coordinated_is_open,
        ),
        caplog.at_level("WARNING", logger="backend.modules.accounts.transports.http"),
    ):
        # `Barrier(2)` can deadlock if a future refactor short-circuits
        # one racer before it reaches `_coordinated_is_open` (e.g. a 422
        # on body validation), leaving the other side blocked on
        # `barrier.wait()` forever. `wait_for` fails the test loudly
        # instead of hanging the suite.
        responses = await asyncio.wait_for(
            asyncio.gather(
                committed_client.post("/setup", json=_setup_payload(email="alice@example.com")),
                committed_client.post("/setup", json=_setup_payload(email="bob@example.com")),
            ),
            timeout=10.0,
        )

    statuses = sorted(r.status_code for r in responses)
    assert statuses == [200, 404]

    # The 404 came via the IntegrityError → `race_lost` branch, not via
    # `precheck_locked`. SQLSTATE 23505 = unique_violation (PK on the
    # household singleton). The log assertion is the only way to
    # distinguish "this test really hit the race branch" from "the
    # scheduler took the post-commit window instead".
    race_lost_records = [
        r
        for r in caplog.records
        if r.message == "setup_locked"
        and getattr(r, "reason", None) == "race_lost"
        and getattr(r, "sqlstate", None) == "23505"
    ]
    assert len(race_lost_records) == 1, (
        f"Expected exactly one race_lost log, got: "
        f"{[(r.message, getattr(r, 'reason', None)) for r in caplog.records]}"
    )

    # Post-race state: exactly one household + one user (the winner committed).
    async with committed_sessionmaker() as session:
        user_count = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        household_count = (
            await session.execute(select(func.count()).select_from(Household))
        ).scalar_one()
    assert user_count == 1
    assert household_count == 1
