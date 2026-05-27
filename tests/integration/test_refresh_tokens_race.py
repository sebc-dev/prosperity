"""Concurrency integration tests for `rotate()` (S02.4 follow-up — issue #54).

Exercises true `asyncio.gather()` races on two independent connections.
The shared `db_session` fixture is unusable here: both parallel tasks
need independent transactional contexts and must see each other's
committed state. We therefore build a dedicated engine pinned to
production isolation (REPEATABLE READ) and create the auth schema
committed for the duration of each test.

Surfaced two pre-existing defects in `rotate()` while writing these
tests (both filed as follow-ups, not fixed here):

- #57: under true REPEATABLE READ contention the loser receives
  `SerializationFailure` (DBAPIError) instead of falling through to
  the replay branch. The barrier variant below pins this gap with a
  permissive assertion until #57 lands.
- #58: the family invalidation flushed in the replay branch is rolled
  back by `get_db`'s `except Exception: rollback` in production. The
  test infra (`_override_get_db`) yields the session without that wrap
  and therefore masks the bug — the assertions on family state below
  reflect the test-time semantics, not production semantics.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from backend.config import get_settings
from backend.modules.auth.models import Base as AuthBase
from backend.modules.auth.models import RefreshToken, User, UserRole
from backend.modules.auth.service.refresh_tokens import (
    InvalidRefreshTokenError,
    RevokedRefreshTokenError,
    hash_refresh_token,
    issue,
    rotate,
)

_settings = get_settings()


@pytest_asyncio.fixture(loop_scope="session")
async def committed_engine(
    postgres_container: PostgresContainer,
) -> AsyncIterator[AsyncEngine]:
    """Dedicated engine with committed auth schema, pinned to REPEATABLE READ.

    Drops the schema at teardown so other tests (which depend on the
    transactional `db_session` fixture and create their schema inside a
    rolled-back transaction) keep their fully-isolated semantics.
    """
    engine = create_async_engine(
        postgres_container.get_connection_url(),
        future=True,
        isolation_level="REPEATABLE READ",
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(AuthBase.metadata.create_all)
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(AuthBase.metadata.drop_all)
        await engine.dispose()


async def test_rotate_concurrent_race_via_asyncio_gather(
    committed_engine: AsyncEngine,
) -> None:
    """Two `rotate(T0)` launched in parallel on independent sessions.

    `asyncio.gather()` without explicit synchronisation typically
    serialises the two transactions enough that the loser observes the
    revoked state in its REPEATABLE READ snapshot and lands in the
    replay branch via `rowcount=0` (no row matches `revoked_at IS NULL`
    anymore). This is the path the `rotate()` docstring describes.

    The barrier variant below stresses the true-contention case where
    that path does **not** fire — see #57.
    """
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)

    # Setup: commit a user + a live refresh token (T0) both racers will target.
    async with sm() as session:
        user = User(
            email="race@example.com",
            password_hash="x" * 60,
            display_name="Race",
            role=UserRole.MEMBER,
        )
        session.add(user)
        await session.flush()
        user_id = user.id
        family_id_seed = None  # captured below
        raw_t0 = await issue(session, user_id, settings=_settings)
        await session.commit()

    # Capture the family for the post-race assertions on family invalidation.
    async with sm() as session:
        t0 = (
            await session.execute(
                select(RefreshToken).where(
                    RefreshToken.token_hash == hash_refresh_token(raw_t0, settings=_settings)
                )
            )
        ).scalar_one()
        family_id_seed = t0.family_id

    async def attempt() -> tuple[str, BaseException | None]:
        async with sm() as session:
            try:
                _, _new_raw = await rotate(session, raw_t0, settings=_settings)
                await session.commit()
                return ("success", None)
            except RevokedRefreshTokenError as exc:
                # Replay branch ran the family invalidation; persist that
                # before reporting.
                await session.commit()
                return ("revoked", exc)
            except InvalidRefreshTokenError as exc:
                await session.rollback()
                return ("invalid", exc)
            except Exception as exc:  # noqa: BLE001 — exploratory net
                await session.rollback()
                return ("other", exc)

    outcomes = await asyncio.gather(attempt(), attempt())
    statuses = sorted(o[0] for o in outcomes)

    # Pinned outcome: we observe one success and one revoked under
    # REPEATABLE READ on Postgres 17. If this assertion ever flips to
    # `("other", "success")` or similar, `rotate()`'s race contract has
    # drifted — investigate before "fixing" the test.
    assert statuses == ["revoked", "success"], (
        f"unexpected race outcome: {statuses}; "
        f"raw outcomes: {[(s, type(e).__name__ if e else None) for s, e in outcomes]}"
    )

    # Verify post-race state: family fully invalidated, no live tokens.
    async with sm() as session:
        rows = (
            (
                await session.execute(
                    select(RefreshToken).where(RefreshToken.family_id == family_id_seed)
                )
            )
            .scalars()
            .all()
        )
    # T0 + the successor inserted by the winner = 2 rows. Both must be
    # marked revoked: the winner revoked T0 explicitly, then the loser's
    # replay branch revoked every live row in the family (including the
    # successor that had just been committed by the winner).
    assert len(rows) == 2
    assert all(row.revoked_at is not None for row in rows), (
        f"expected every row in the family to be revoked; got: "
        f"{[(r.token_hash[:8], r.revoked_at) for r in rows]}"
    )


async def test_rotate_concurrent_race_with_barrier(
    committed_engine: AsyncEngine,
) -> None:
    """Same race, but with an `asyncio.Barrier` forcing both tasks to issue
    their `UPDATE` after both have already opened a snapshot.

    Without the barrier, `asyncio.gather()` often schedules one task to
    completion before the other even starts its UPDATE — the second one
    then sees the row as revoked in its initial snapshot and lands in
    the replay branch via `rowcount=0`. The barrier closes that window:
    both transactions take their REPEATABLE READ snapshot first, then
    contend on the UPDATE row lock simultaneously.

    **Current observed behaviour (pinning the gap from #57)**: the
    loser surfaces a Postgres `SerializationFailure` (40001) wrapped as
    `sqlalchemy.exc.DBAPIError` — NOT the replay branch. `rotate()`
    does not catch that exception, so in production the route returns
    500. This assertion is therefore deliberately permissive (just
    "exactly one success") until #57 lands. Tighten to
    `["revoked", "success"]` strict as part of that fix.
    """
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)

    async with sm() as session:
        user = User(
            email="race-barrier@example.com",
            password_hash="x" * 60,
            display_name="Race Barrier",
            role=UserRole.MEMBER,
        )
        session.add(user)
        await session.flush()
        user_id = user.id
        raw_t0 = await issue(session, user_id, settings=_settings)
        await session.commit()

    barrier = asyncio.Barrier(2)

    async def attempt() -> tuple[str, str | None]:
        async with sm() as session:
            # Force the snapshot to materialise before the barrier fires:
            # a trivial SELECT pins the REPEATABLE READ snapshot at this
            # point so both transactions enter the UPDATE contention with
            # the same view of the world.
            await session.execute(select(RefreshToken).limit(1))
            await barrier.wait()
            try:
                _, _new_raw = await rotate(session, raw_t0, settings=_settings)
                await session.commit()
                return ("success", None)
            except RevokedRefreshTokenError:
                await session.commit()
                return ("revoked", None)
            except InvalidRefreshTokenError as exc:
                await session.rollback()
                return ("invalid", type(exc).__name__)
            except Exception as exc:  # noqa: BLE001 — exploratory net
                await session.rollback()
                return ("other", type(exc).__name__)

    outcomes = await asyncio.gather(attempt(), attempt())
    statuses = sorted(o[0] for o in outcomes)

    # Exactly one task must succeed; the other must NOT also succeed.
    # The losing branch is left intentionally permissive — see docstring.
    assert statuses.count("success") == 1, (
        f"expected exactly one success; got {statuses}, "
        f"detail: {[(s, d) for s, d in outcomes]}"
    )
