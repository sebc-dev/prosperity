"""Purge nightly du journal d'idempotence `sync_request_log` (S13.2 / P13.2.2).

Exerce `service.retention.purge_expired_sync_request_log` sur le tier
d'intégration (rollback-isolé via `db_session`/`auth_schema`) : sélection par
borne stricte, idempotence, table vide, et `retention_days` paramétrable (câblé
au `cutoff`, pas codé en dur). `now` est injecté ⇒ déterministe.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.models import User
from backend.modules.sync.models import SyncRequestLog
from backend.modules.sync.service.retention import (
    SYNC_REQUEST_LOG_RETENTION_DAYS,
    purge_expired_sync_request_log,
)

_NOW = dt.datetime(2026, 6, 11, 3, 0, tzinfo=dt.UTC)


async def _insert(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    processed_at: dt.datetime,
    table_name: str = "transactions",
) -> None:
    session.add(
        SyncRequestLog(
            user_id=user_id,
            client_request_id=uuid.uuid4(),
            table_name=table_name,
            processed_at=processed_at,
        )
    )
    await session.flush()


async def _count(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(SyncRequestLog))
    return result.scalar_one()


async def test_purge_removes_only_rows_older_than_retention(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    """J-31 disparaît ; J-29 / J-1 restent. La purge renvoie le compte supprimé."""
    user = await bound_user_factory()
    await _insert(auth_schema, user_id=user.id, processed_at=_NOW - dt.timedelta(days=31))
    await _insert(auth_schema, user_id=user.id, processed_at=_NOW - dt.timedelta(days=29))
    await _insert(auth_schema, user_id=user.id, processed_at=_NOW - dt.timedelta(days=1))

    deleted = await purge_expired_sync_request_log(auth_schema, now=_NOW)

    assert deleted == 1
    assert await _count(auth_schema) == 2


async def test_purge_is_idempotent(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    """Un 2ᵉ appel ne retrouve plus la ligne expirée → `0`."""
    user = await bound_user_factory()
    await _insert(auth_schema, user_id=user.id, processed_at=_NOW - dt.timedelta(days=40))

    assert await purge_expired_sync_request_log(auth_schema, now=_NOW) == 1
    assert await purge_expired_sync_request_log(auth_schema, now=_NOW) == 0


async def test_purge_bound_is_strict(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    """Une ligne EXACTEMENT à `cutoff` (`now - retention`) n'est PAS supprimée
    (`processed_at < cutoff`, borne stricte)."""
    user = await bound_user_factory()
    cutoff = _NOW - dt.timedelta(days=SYNC_REQUEST_LOG_RETENTION_DAYS)
    await _insert(auth_schema, user_id=user.id, processed_at=cutoff)

    assert await purge_expired_sync_request_log(auth_schema, now=_NOW) == 0
    assert await _count(auth_schema) == 1


async def test_purge_on_empty_table_returns_zero(auth_schema: AsyncSession) -> None:
    """Run nocturne sur une base fraîche : table vide → `0` (jamais d'erreur)."""
    assert await purge_expired_sync_request_log(auth_schema, now=_NOW) == 0


async def test_retention_days_parameter_drives_the_cutoff(
    auth_schema: AsyncSession,
    bound_user_factory: Callable[..., Awaitable[User]],
) -> None:
    """`retention_days=7` supprime J-8 mais pas J-6 (le paramètre alimente le
    `cutoff` — pas une rétention 30j codée en dur)."""
    user = await bound_user_factory()
    await _insert(auth_schema, user_id=user.id, processed_at=_NOW - dt.timedelta(days=8))
    await _insert(auth_schema, user_id=user.id, processed_at=_NOW - dt.timedelta(days=6))

    deleted = await purge_expired_sync_request_log(auth_schema, now=_NOW, retention_days=7)

    assert deleted == 1
    assert await _count(auth_schema) == 1
