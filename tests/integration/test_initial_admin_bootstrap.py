"""Integration tests for `bootstrap_initial_admin_from_env` (S03.3).

Tests run on `committed_engine` so the `after_commit` listener that
invalidates `_household_cache` actually fires — same pattern used by
`tests/integration/test_setup_invalidation.py`. Each test gets a
fresh, truncated schema via the autouse `_clean_committed_db` fixture.

The orchestrator never raises on DB / infra failure (see its docstring);
these tests pin that contract together with the logging surface every
operator runbook step relies on (cf. `runbooks/initial_admin_via_env.md`
"Modes d'échec" table).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from pwdlib import PasswordHash
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.config import Settings
from backend.modules.accounts.models import HOUSEHOLD_SINGLETON_UUID, Household
from backend.modules.accounts.service import household as household_service
from backend.modules.accounts.service import setup as setup_service
from backend.modules.accounts.service.setup import bootstrap_initial_admin_from_env
from backend.modules.auth.models import User, UserRole

# Truncate the committed-engine schema before AND after each test so
# the env-var bootstrap always starts on a vierge state.
pytestmark = [pytest.mark.usefixtures("_clean_committed_db")]


_HASHER = PasswordHash.recommended()
_PLAINTEXT = "correct-horse-battery-staple-12chars"


def _build_settings(
    *,
    email: str | None = "admin@example.com",
    password_hash: str | None = None,
    display_name: str = "Admin",
    household_name: str = "Foyer",
) -> Settings:
    """Construct a `Settings` for the orchestrator without going through env vars.

    Bypassing `get_settings()` keeps tests deterministic — they don't
    have to clear the `lru_cache` or coordinate with adjacent tests
    that touch the environment.
    """
    hash_secret = SecretStr(password_hash) if password_hash is not None else None
    return Settings(
        # `EmailStr | None` accepts `None` directly.
        initial_admin_email=email,  # type: ignore[arg-type]
        initial_admin_password_hash=hash_secret,
        initial_admin_display_name=display_name,
        initial_household_name=household_name,
    )


@pytest_asyncio.fixture(autouse=True)
async def _reset_household_cache() -> AsyncIterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Prevent module-state bleed across tests (cache is process-local)."""
    household_service.invalidate_household_cache()
    yield
    household_service.invalidate_household_cache()


@pytest.fixture(autouse=True)
def _noop_asyncio_sleep(monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    """Make retry backoff instant so the suite stays fast.

    Scoped to `backend.modules.accounts.service.setup.asyncio.sleep`
    rather than globally, so pytest-asyncio's own internal sleeps stay
    intact.
    """

    async def _noop(_: float) -> None:
        return None

    monkeypatch.setattr(setup_service.asyncio, "sleep", _noop)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _count_users(sm: async_sessionmaker[AsyncSession]) -> int:
    async with sm() as s:
        result = await s.execute(select(func.count()).select_from(User))
        return int(result.scalar_one())


async def _count_households(sm: async_sessionmaker[AsyncSession]) -> int:
    async with sm() as s:
        result = await s.execute(select(func.count()).select_from(Household))
        return int(result.scalar_one())


def _make_orig(sqlstate: str | None) -> object:
    """Forge a fake DBAPI `orig` attribute that satisfies `getattr(..., 'sqlstate')`.

    Same shape as `tests/integration/test_setup_unexpected_integrity.py`.
    """
    if sqlstate is None:
        return object()
    return type("PgError", (), {"sqlstate": sqlstate})()


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


async def test_happy_path_creates_admin_and_initialises_household(
    committed_sessionmaker: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Env vars set + DB vide → admin créé, household init, log info, cache invalidé."""
    precomputed = _HASHER.hash(_PLAINTEXT)
    settings = _build_settings(
        email="admin@example.com",
        password_hash=precomputed,
        display_name="Alice",
        household_name="Foyer Dupont",
    )

    # Pre-poison the cache so we can assert the `after_commit` listener
    # cleared it — same pattern as test_setup_invalidation.
    household_service._household_cache = Household(  # pyright: ignore[reportPrivateUsage]
        name="STALE",
        base_currency="EUR",
        initialized_at=datetime.now(tz=UTC),
    )

    with caplog.at_level(logging.INFO, logger=setup_service.__name__):
        await bootstrap_initial_admin_from_env(committed_sessionmaker, settings)

    # Listener fired post-commit → cache invalidated.
    assert household_service._household_cache is None  # pyright: ignore[reportPrivateUsage]

    # One user, one household, with the right shape.
    async with committed_sessionmaker() as s:
        users = (await s.execute(select(User))).scalars().all()
        households = (await s.execute(select(Household))).scalars().all()
    assert len(users) == 1
    u = users[0]
    assert u.email == "admin@example.com"
    assert u.display_name == "Alice"
    assert u.role is UserRole.ADMIN
    # Hash stored AS-IS — round-trip with the original plaintext.
    assert u.password_hash == precomputed
    assert _HASHER.verify(_PLAINTEXT, u.password_hash)
    assert len(households) == 1
    h = households[0]
    assert h.id == HOUSEHOLD_SINGLETON_UUID
    assert h.name == "Foyer Dupont"
    assert h.base_currency == "EUR"
    assert h.initialized_at is not None

    assert any(r.message == "initial_admin_created" for r in caplog.records)


async def test_happy_path_lowercases_email(
    committed_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """`User._normalize_email` validator fires on the env-var path too."""
    precomputed = _HASHER.hash(_PLAINTEXT)
    settings = _build_settings(
        email="ADMIN@FOO.COM",
        password_hash=precomputed,
    )
    await bootstrap_initial_admin_from_env(committed_sessionmaker, settings)
    async with committed_sessionmaker() as s:
        user = (await s.execute(select(User))).scalar_one()
    assert user.email == "admin@foo.com"


# ---------------------------------------------------------------------------
# 2. Configuration absente / partielle
# ---------------------------------------------------------------------------


async def test_no_env_vars_silent_skip(
    committed_sessionmaker: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Both unset → silent (no log) + no DB mutation. Normal-mode default."""
    settings = _build_settings(email=None, password_hash=None)
    with caplog.at_level(logging.DEBUG, logger=setup_service.__name__):
        await bootstrap_initial_admin_from_env(committed_sessionmaker, settings)

    assert await _count_users(committed_sessionmaker) == 0
    assert await _count_households(committed_sessionmaker) == 0
    # Strict: no `initial_admin_*` log at any level — quiet boot.
    assert not [r for r in caplog.records if r.message.startswith("initial_admin_")]


async def test_email_only_partial_config(
    committed_sessionmaker: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = _build_settings(email="admin@example.com", password_hash=None)
    with caplog.at_level(logging.WARNING, logger=setup_service.__name__):
        await bootstrap_initial_admin_from_env(committed_sessionmaker, settings)

    assert await _count_users(committed_sessionmaker) == 0
    record = next(r for r in caplog.records if r.message == "initial_admin_partial_config")
    assert record.levelname == "WARNING"
    assert record.__dict__["has_email"] is True
    assert record.__dict__["has_hash"] is False


async def test_hash_only_partial_config(
    committed_sessionmaker: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = _build_settings(email=None, password_hash=_HASHER.hash(_PLAINTEXT))
    with caplog.at_level(logging.WARNING, logger=setup_service.__name__):
        await bootstrap_initial_admin_from_env(committed_sessionmaker, settings)

    assert await _count_users(committed_sessionmaker) == 0
    record = next(r for r in caplog.records if r.message == "initial_admin_partial_config")
    assert record.__dict__["has_email"] is False
    assert record.__dict__["has_hash"] is True


# ---------------------------------------------------------------------------
# 3. Idempotence: déjà initialisé
# ---------------------------------------------------------------------------


async def test_already_initialized_is_skipped(
    committed_sessionmaker: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """DB non vide → skip + log info, l'admin existant n'est pas touché."""
    async with committed_sessionmaker() as s:
        s.add(
            Household(
                name="Existing",
                base_currency="EUR",
                initialized_at=datetime.now(tz=UTC),
            )
        )
        s.add(
            User(
                email="existing@example.com",
                password_hash="x" * 60,
                display_name="Existing",
                role=UserRole.ADMIN,
            )
        )
        await s.commit()

    settings = _build_settings(
        email="newcomer@example.com",
        password_hash=_HASHER.hash(_PLAINTEXT),
    )
    with caplog.at_level(logging.INFO, logger=setup_service.__name__):
        await bootstrap_initial_admin_from_env(committed_sessionmaker, settings)

    # Same counts before/after, existing admin untouched.
    assert await _count_users(committed_sessionmaker) == 1
    assert await _count_households(committed_sessionmaker) == 1
    async with committed_sessionmaker() as s:
        u = (await s.execute(select(User))).scalar_one()
    assert u.email == "existing@example.com"

    record = next(r for r in caplog.records if r.message == "initial_admin_skipped")
    assert record.__dict__["reason"] == "already_initialized"


# ---------------------------------------------------------------------------
# 4. Hash invalide / non reconnu par pwdlib
# ---------------------------------------------------------------------------


async def test_hash_invalid_skips_with_error_log(
    committed_sessionmaker: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`pwdlib` doesn't recognise this string → skip + ERROR log."""
    settings = _build_settings(
        email="admin@example.com",
        password_hash="not-an-argon2-hash-at-all",
    )
    with caplog.at_level(logging.ERROR, logger=setup_service.__name__):
        await bootstrap_initial_admin_from_env(committed_sessionmaker, settings)

    assert await _count_users(committed_sessionmaker) == 0
    assert await _count_households(committed_sessionmaker) == 0
    record = next(r for r in caplog.records if r.message == "initial_admin_hash_invalid")
    assert record.levelname == "ERROR"


# ---------------------------------------------------------------------------
# 5. Race-lost simulé via forged DBAPIError (parité avec test_setup_unexpected_integrity)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sqlstate", ["23505", "23514", "40001"])
async def test_race_lost_sqlstate_skips_silently(
    sqlstate: str,
    committed_sessionmaker: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Race-lost SQLSTATEs → log info `initial_admin_race_lost`, no exception, no retry."""
    settings = _build_settings(
        email="admin@example.com",
        password_hash=_HASHER.hash(_PLAINTEXT),
    )

    call_count = {"n": 0}

    async def _explode(*_args: object, **_kwargs: object) -> None:
        call_count["n"] += 1
        raise DBAPIError("forged", params=None, orig=_make_orig(sqlstate))  # type: ignore[arg-type]

    monkeypatch.setattr(setup_service, "_bootstrap_from_hash", _explode)

    with caplog.at_level(logging.INFO, logger=setup_service.__name__):
        await bootstrap_initial_admin_from_env(committed_sessionmaker, settings)

    # Race-lost: skip after the first attempt. No retry (the loser
    # would lose again — `is_setup_open` will be False next pass).
    assert call_count["n"] == 1
    record = next(r for r in caplog.records if r.message == "initial_admin_race_lost")
    assert record.__dict__["sqlstate"] == sqlstate


# ---------------------------------------------------------------------------
# 6. Transient errors: retry then succeed
# ---------------------------------------------------------------------------


async def test_transient_error_retry_then_success(
    committed_sessionmaker: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transient SQLSTATE 08*** → retry → success on the 2nd attempt.

    `OperationalError` is a `DBAPIError` subclass; the orchestrator
    classifies it via `sqlstate.startswith("08")`. Tests pass through
    the real `_bootstrap_from_hash` on the second attempt so we
    actually persist the row.
    """
    settings = _build_settings(
        email="admin@example.com",
        password_hash=_HASHER.hash(_PLAINTEXT),
    )

    real_bootstrap = setup_service._bootstrap_from_hash  # pyright: ignore[reportPrivateUsage]
    attempts: list[int] = []

    async def _flaky(*args: Any, **kwargs: Any) -> Any:
        attempts.append(len(attempts))
        if len(attempts) == 1:
            raise OperationalError("transient", params=None, orig=_make_orig("08006"))  # type: ignore[arg-type]
        return await real_bootstrap(*args, **kwargs)

    monkeypatch.setattr(setup_service, "_bootstrap_from_hash", _flaky)

    with caplog.at_level(logging.INFO, logger=setup_service.__name__):
        await bootstrap_initial_admin_from_env(committed_sessionmaker, settings)

    assert await _count_users(committed_sessionmaker) == 1
    retries = [r for r in caplog.records if r.message == "initial_admin_db_error_retry"]
    assert len(retries) == 1
    assert retries[0].__dict__["sqlstate"] == "08006"
    assert any(r.message == "initial_admin_created" for r in caplog.records)


async def test_transient_error_persistent_does_not_crash_startup(
    committed_sessionmaker: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """3 consecutive transient errors → log ERROR + return cleanly (no raise)."""
    settings = _build_settings(
        email="admin@example.com",
        password_hash=_HASHER.hash(_PLAINTEXT),
    )

    async def _always_transient(*_args: object, **_kwargs: object) -> None:
        raise OperationalError("transient", params=None, orig=_make_orig("08001"))  # type: ignore[arg-type]

    monkeypatch.setattr(setup_service, "_bootstrap_from_hash", _always_transient)

    with caplog.at_level(logging.WARNING, logger=setup_service.__name__):
        # The contract: never raises on infra failure.
        await bootstrap_initial_admin_from_env(committed_sessionmaker, settings)

    assert await _count_users(committed_sessionmaker) == 0
    persistent = [
        r for r in caplog.records if r.message == "initial_admin_db_error_persistent"
    ]
    assert len(persistent) == 1
    assert persistent[0].levelname == "ERROR"


async def test_unknown_sqlstate_logs_persistent_error(
    committed_sessionmaker: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-race, non-transient SQLSTATE (e.g. 23502 NOT NULL) → ERROR + skip.

    Critical: the orchestrator is for infra/race issues. An app bug
    (NOT NULL violation = the model is wrong) is logged at ERROR and
    swallowed *only because* the runbook says "operator can /setup
    manually" — surfacing the underlying bug is the operator's job.
    """
    settings = _build_settings(
        email="admin@example.com",
        password_hash=_HASHER.hash(_PLAINTEXT),
    )

    async def _not_null(*_args: object, **_kwargs: object) -> None:
        raise DBAPIError("forged", params=None, orig=_make_orig("23502"))  # type: ignore[arg-type]

    monkeypatch.setattr(setup_service, "_bootstrap_from_hash", _not_null)

    with caplog.at_level(logging.ERROR, logger=setup_service.__name__):
        await bootstrap_initial_admin_from_env(committed_sessionmaker, settings)

    record = next(r for r in caplog.records if r.message == "initial_admin_db_error_persistent")
    assert record.__dict__["sqlstate"] == "23502"


# ---------------------------------------------------------------------------
# 7. Concurrence: asyncio.gather N workers — pin "no advisory lock needed"
# ---------------------------------------------------------------------------


async def test_concurrent_bootstrap_workers_serialise_via_db_constraints(
    committed_sessionmaker: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """N parallel workers + env vars set → exactly 1 wins, N-1 race-lost.

    The orchestrator deliberately has no advisory lock — we rely on
    the household PK + email UNIQUE to serialise. This test pins the
    invariant by launching 4 concurrent calls and asserting end state.
    """
    precomputed = _HASHER.hash(_PLAINTEXT)
    settings = _build_settings(email="admin@example.com", password_hash=precomputed)

    n_workers = 4
    with caplog.at_level(logging.INFO, logger=setup_service.__name__):
        await asyncio.gather(
            *(
                bootstrap_initial_admin_from_env(committed_sessionmaker, settings)
                for _ in range(n_workers)
            )
        )

    # Exactly one row each (the DB constraints sorted out the race).
    assert await _count_users(committed_sessionmaker) == 1
    assert await _count_households(committed_sessionmaker) == 1

    created = [r for r in caplog.records if r.message == "initial_admin_created"]
    losers = [
        r
        for r in caplog.records
        if r.message in {"initial_admin_race_lost", "initial_admin_skipped"}
    ]
    # Exactly one winner; the rest take one of the two skip paths
    # depending on whether their precheck saw the committed row.
    assert len(created) == 1
    assert len(created) + len(losers) == n_workers
