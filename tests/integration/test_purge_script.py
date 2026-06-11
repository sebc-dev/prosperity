"""Entrypoint cron de la purge — `backend.scripts.purge_sync_request_log` (S13.2 / Tests F3).

C'est le SEUL appelant de prod de `purge_expired_sync_request_log` ; sans test il
serait du code prod non couvert (`source = ["backend"]`, pas d'`omit`). Exerce le
chemin COMPLET de `main()` (engine bâti depuis `get_settings()`, commit, dispose)
contre le container réel-commit en surchargeant `DATABASE_URL`, puis vérifie
depuis une session DISTINCTE que la suppression a bien été persistée (un `commit()`
oublié passerait inaperçu autrement). Assure aussi que l'entrypoint ne logge JAMAIS
le DSN (review Sécu F3).
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.config import get_settings
from backend.modules.auth.domain import UserRole
from backend.modules.auth.models import User
from backend.modules.sync.models import SyncRequestLog
from backend.scripts import purge_sync_request_log

pytestmark = [pytest.mark.usefixtures("_clean_committed_db")]


@pytest_asyncio.fixture(loop_scope="session")
async def _seeded_user(  # pyright: ignore[reportUnusedFunction]  # consumed by name as a fixture
    committed_sessionmaker: async_sessionmaker[AsyncSession],
) -> uuid.UUID:
    """A committed `User` to satisfy `sync_request_log.user_id` FK RESTRICT."""
    user = User(
        email="purge-script@test.local",
        password_hash="x",
        display_name="Purge Script",
        role=UserRole.MEMBER,
    )
    async with committed_sessionmaker() as session:
        session.add(user)
        await session.commit()
        return user.id


async def _insert(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    user_id: uuid.UUID,
    processed_at: dt.datetime,
) -> None:
    async with sessionmaker() as session:
        session.add(
            SyncRequestLog(
                user_id=user_id,
                client_request_id=uuid.uuid4(),
                table_name="transactions",
                processed_at=processed_at,
            )
        )
        await session.commit()


async def test_main_purges_and_commits(
    committed_sessionmaker: async_sessionmaker[AsyncSession],
    postgres_container: object,
    _seeded_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    now = dt.datetime.now(tz=dt.UTC)
    expired_at = now - dt.timedelta(days=40)
    fresh_at = now - dt.timedelta(days=1)
    await _insert(committed_sessionmaker, user_id=_seeded_user, processed_at=expired_at)
    await _insert(committed_sessionmaker, user_id=_seeded_user, processed_at=fresh_at)

    dsn = postgres_container.get_connection_url()  # type: ignore[attr-defined]
    monkeypatch.setenv("DATABASE_URL", dsn)
    get_settings.cache_clear()
    try:
        with caplog.at_level(logging.INFO):
            await purge_sync_request_log.main()
    finally:
        get_settings.cache_clear()  # don't leak the container DSN to sibling tests

    # Verified from a DISTINCT session: the real commit persisted the delete.
    async with committed_sessionmaker() as verify:
        remaining = (
            await verify.execute(select(func.count()).select_from(SyncRequestLog))
        ).scalar_one()
        survivor = (await verify.execute(select(SyncRequestLog.user_id))).scalars().all()
    assert remaining == 1  # only the J-1 row survives
    assert survivor == [_seeded_user]

    # The entrypoint logs the COUNT, never the DSN (Sécu F3).
    full_log = " ".join(rec.getMessage() for rec in caplog.records)
    assert "row(s)" in full_log
    assert dsn not in full_log
    assert "@" not in full_log  # no `user:pass@host` connection string fragment
