"""Concurrency integration tests for `rotate()` (S02.4 follow-up — issue #54).

Exercises true `asyncio.gather()` races on two independent connections.
The shared `db_session` fixture is unusable here: both parallel tasks
need independent transactional contexts and must see each other's
committed state. We therefore build a dedicated engine pinned to
production isolation (REPEATABLE READ) and create the auth schema
committed for the duration of each test.

Two race shapes covered:

- `test_rotate_replay_branch_fires_when_loser_starts_after_commit` —
  `asyncio.Event` makes the loser open its REPEATABLE READ snapshot
  strictly after the winner has committed. Pins the deterministic
  `rowcount=0` → replay branch path.
- `test_rotate_concurrent_race_with_barrier` — `asyncio.Barrier`
  forces both tasks to issue their UPDATE inside the same snapshot
  window. Pins the SerializationFailure (SQLSTATE 40001) → replay
  recovery path added by issue #57.

Both tests verify post-race family state via a third independent
session, which is the canonical pinning for "the family invalidation
committed by `rotate()` actually persisted to the database"
(cf. ADR 0015 and issue #58).
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from backend.config import get_settings
from backend.modules.auth.models import RefreshToken, User, UserRole
from backend.modules.auth.service.refresh_tokens import (
    InvalidRefreshTokenError,
    RevokedRefreshTokenError,
    hash_refresh_token,
    issue,
    rotate,
)

# Truncate every Base.metadata table before & after each test on the
# shared module-scoped `committed_engine`. Without this opt-in cleanup
# the per-user fixtures below would collide on the UNIQUE email index
# after the first run.
pytestmark = [pytest.mark.usefixtures("_clean_committed_db")]

_settings = get_settings()


async def test_rotate_replay_branch_fires_when_loser_starts_after_commit(
    committed_engine: AsyncEngine,
) -> None:
    """Two `rotate(T0)` on independent sessions; loser starts after winner commits.

    Pins the `rowcount=0` → replay branch path described in `rotate()`'s
    docstring: the loser opens its REPEATABLE READ snapshot **after**
    the winner has committed, so the row already shows `revoked_at IS
    NOT NULL`; its UPDATE filter (`revoked_at IS NULL`) matches zero
    rows and the replay-detection branch fires.

    Coordination via an `asyncio.Event` rather than relying on the
    default `asyncio.gather()` scheduling. Without that explicit sync
    the outcome would depend on Python-version / loop-impl ordering and
    could occasionally flake into the true-contention case where the
    loser surfaces `SerializationFailure` (40001) instead of revoked —
    see #57 and the barrier variant below for the contention path.
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

    winner_committed = asyncio.Event()

    async def winner() -> tuple[str, BaseException | None]:
        async with sm() as session:
            try:
                _, _new_raw = await rotate(session, raw_t0, settings=_settings)
                await session.commit()
                return ("success", None)
            except Exception as exc:  # noqa: BLE001 — defensive: surface, never hang
                await session.rollback()
                return ("winner-failed", exc)
            finally:
                # Unblock the loser even on failure so `gather()` doesn't hang.
                winner_committed.set()

    async def loser() -> tuple[str, BaseException | None]:
        await winner_committed.wait()
        async with sm() as session:
            try:
                _, _new_raw = await rotate(session, raw_t0, settings=_settings)
                await session.commit()
                return ("success", None)
            except RevokedRefreshTokenError as exc:
                # No `session.commit()` here on purpose: the replay branch
                # of `rotate()` commits the family invalidation itself
                # (ADR 0015). If we observe the family revoked from a
                # separate session below, the contract holds.
                return ("revoked", exc)
            except InvalidRefreshTokenError as exc:
                await session.rollback()
                return ("invalid", exc)
            except Exception as exc:  # noqa: BLE001 — exploratory net
                await session.rollback()
                return ("other", exc)

    # `wait_for` is belt-and-braces against the `winner_committed.set()`
    # in `winner`'s `finally` being skipped by a future refactor (e.g. a
    # `BaseException` like `CancelledError` bypassing the try/except).
    # The Event-based handoff already guards the happy path; the timeout
    # guarantees the suite fails loudly instead of hanging on regression.
    outcomes = await asyncio.wait_for(asyncio.gather(winner(), loser()), timeout=10.0)
    statuses = [o[0] for o in outcomes]

    # Order is deterministic by construction: winner first, loser second.
    assert statuses == ["success", "revoked"], (
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

    Under true contention the Postgres loser is aborted with
    `SerializationFailure` (SQLSTATE 40001); `rotate()` catches that,
    rolls back the aborted txn, runs the replay branch against a fresh
    snapshot, and commits the family invalidation before raising
    `RevokedRefreshTokenError` (cf. issue #57 + ADR 0015). The strict
    assertion below pins that behaviour: exactly one success, the
    other revoked, and the entire family marked revoked in the
    database from the point of view of a third session.
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

    async with sm() as session:
        family_id_seed = (
            await session.execute(
                select(RefreshToken.family_id).where(
                    RefreshToken.token_hash == hash_refresh_token(raw_t0, settings=_settings)
                )
            )
        ).scalar_one()

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
                # `rotate()` already committed the family invalidation
                # internally (race-recovery path, ADR 0015). Don't add a
                # second commit — the verification below uses an
                # independent session.
                return ("revoked", None)
            except InvalidRefreshTokenError as exc:
                await session.rollback()
                return ("invalid", type(exc).__name__)
            except Exception as exc:  # noqa: BLE001 — exploratory net
                await session.rollback()
                return ("other", type(exc).__name__)

    # `Barrier(2)` deadlocks if one `attempt()` short-circuits before
    # reaching `barrier.wait()` (e.g. the warm-up SELECT raising). The
    # timeout fails the test loudly instead of hanging the suite.
    outcomes = await asyncio.wait_for(asyncio.gather(attempt(), attempt()), timeout=10.0)
    statuses = sorted(o[0] for o in outcomes)

    # Strict outcome contract: one success, one revoked. No 500-class
    # leakage ("other") and no double-success.
    assert statuses == ["revoked", "success"], (
        f"unexpected race outcome: {statuses}; detail: {[(s, d) for s, d in outcomes]}"
    )

    # Family fully invalidated, witnessed from an independent session.
    # This is the pinning for #58: the family revocation committed by
    # `rotate()` survived without help from any caller-side commit.
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
    # revoked: the winner revoked T0, then the loser's race-recovery
    # branch revoked every still-live row in the family (the winner's
    # successor included).
    assert len(rows) == 2
    assert all(row.revoked_at is not None for row in rows), (
        f"expected every row in the family to be revoked; got: "
        f"{[(r.token_hash[:8], r.revoked_at) for r in rows]}"
    )


async def test_rotate_replay_family_invalidation_persists_across_sessions(
    committed_engine: AsyncEngine,
) -> None:
    """Replay branch's family invalidation must survive caller-side rollback.

    Direct service-level pinning of issue #58: when `rotate()` detects
    a replay it commits the family invalidation itself (ADR 0015).
    Simulating the `get_db` `except: rollback` contract — the caller
    rolls back its session after `RevokedRefreshTokenError` — must
    not erase the tombstone. A third, independent session then
    asserts the family is fully revoked.

    Without the commit-inside-service in `rotate()`'s replay branch,
    the caller's rollback would revert the family invalidation flush
    and this test's final assertion would fail. With the test infra
    fix in `conftest.py:_override_get_db` this same contract is
    exercised end-to-end via `/auth/refresh`; this test corners the
    service layer directly so a future regression is attributed to
    `rotate()`, not to the HTTP transport.
    """
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)

    async with sm() as session:
        user = User(
            email="replay-pin@example.com",
            password_hash="x" * 60,
            display_name="Replay Pin",
            role=UserRole.MEMBER,
        )
        session.add(user)
        await session.flush()
        user_id = user.id
        raw_t0 = await issue(session, user_id, settings=_settings)
        await session.commit()

    async with sm() as session:
        _, _raw_t1 = await rotate(session, raw_t0, settings=_settings)
        await session.commit()

    async with sm() as session:
        family_id = (
            await session.execute(
                select(RefreshToken.family_id).where(
                    RefreshToken.token_hash == hash_refresh_token(raw_t0, settings=_settings)
                )
            )
        ).scalar_one()

    # Caller mimics `get_db`: enters a session, calls `rotate()`,
    # rollbacks on the resulting exception. The family invalidation
    # must already be committed by `rotate()` so this rollback is a
    # no-op for the security tombstone.
    async with sm() as session:
        with pytest.raises(RevokedRefreshTokenError):
            try:
                await rotate(session, raw_t0, settings=_settings)
            except Exception:
                await session.rollback()
                raise

    # Independent connection observes the family. If the replay branch
    # only flushed (no commit), the rollback above would have erased
    # the UPDATE and the live successor would still be live here.
    async with sm() as session:
        rows = (
            (await session.execute(select(RefreshToken).where(RefreshToken.family_id == family_id)))
            .scalars()
            .all()
        )
    assert len(rows) == 2
    assert all(row.revoked_at is not None for row in rows), (
        f"family invalidation did not persist across rollback: "
        f"{[(r.token_hash[:8], r.revoked_at) for r in rows]}"
    )
