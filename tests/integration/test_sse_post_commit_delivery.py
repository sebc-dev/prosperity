"""Livraison POST-COMMIT des signaux SSE (S17.1, P17.1.5, D6).

Tier **`committed_engine`** (vrais commit/rollback, gabarit S13.6) — PAS le harnais
savepoint, où `commit()` est un *release* de SAVEPOINT qui ferait fire `after_commit`
à tort et masquerait l'invariant « après, pas avant ». Broadcaster espionné
(`set_broadcaster`)."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.modules.sse.events import SseSignal
from backend.modules.sse.service.broadcaster import Broadcaster, get_broadcaster, set_broadcaster
from backend.modules.sse.service.delivery import _PENDING, register_sse_delivery
from backend.shared.events import clear_subscribers, dispatch


class _SpyBroadcaster(Broadcaster):
    def __init__(self) -> None:
        super().__init__()
        self.published: list[tuple[UUID, str, str]] = []

    def publish(self, user_id: UUID, event: str, data: str) -> object:
        self.published.append((user_id, event, data))
        return super().publish(user_id, event, data)


@pytest.fixture
def spy() -> Iterator[_SpyBroadcaster]:
    """Substitue le broadcaster par un espion + enregistre la livraison SSE ; restaure après."""
    original = get_broadcaster()
    spy = _SpyBroadcaster()
    set_broadcaster(spy)
    clear_subscribers()
    register_sse_delivery()
    yield spy
    clear_subscribers()
    set_broadcaster(original)


@pytest.mark.usefixtures("_clean_committed_db")
async def test_signal_delivered_after_commit_not_before(
    committed_engine: AsyncEngine, spy: _SpyBroadcaster
) -> None:
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    uid = uuid4()
    session: AsyncSession
    async with sm() as session:
        await dispatch(session, SseSignal(user_id=uid, event="n", data='{"id": 1}'))
        assert spy.published == []  # rien tant que la transaction est OUVERTE (post-commit)
        await session.commit()
        assert spy.published == [(uid, "n", '{"id": 1}')]  # diffusé APRÈS commit, une fois
        assert _PENDING not in session.info  # session.info vidée (anti-fuite, symétrie rollback)


@pytest.mark.usefixtures("_clean_committed_db")
async def test_rollback_delivers_nothing(
    committed_engine: AsyncEngine, spy: _SpyBroadcaster
) -> None:
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    async with sm() as session:
        # Un signal accompagne toujours un write réel → une transaction est active
        # (sinon `rollback()` d'une session sans transaction ne fire pas `after_rollback`).
        await session.execute(text("SELECT 1"))
        await dispatch(session, SseSignal(user_id=uuid4(), event="n", data="{}"))
        await session.rollback()
        assert spy.published == []  # rollback → AUCUNE diffusion (pas d'event fantôme)
        assert _PENDING not in session.info


@pytest.mark.usefixtures("_clean_committed_db")
async def test_two_signals_one_transaction_flush_once_each(
    committed_engine: AsyncEngine, spy: _SpyBroadcaster
) -> None:
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    uid = uuid4()
    async with sm() as session:
        await dispatch(session, SseSignal(user_id=uid, event="n", data="a"))
        await dispatch(session, SseSignal(user_id=uid, event="n", data="b"))
        await session.commit()
    assert spy.published == [(uid, "n", "a"), (uid, "n", "b")]  # 2 events, flush unique


@pytest.mark.usefixtures("_clean_committed_db")
async def test_two_sequential_transactions_rearm_listener(
    committed_engine: AsyncEngine, spy: _SpyBroadcaster
) -> None:
    # Verrou du `once=True` : le listener doit se ré-armer à la 2e transaction (même session).
    sm = async_sessionmaker(committed_engine, expire_on_commit=False)
    uid = uuid4()
    async with sm() as session:
        await dispatch(session, SseSignal(user_id=uid, event="n", data="a"))
        await session.commit()
        await dispatch(session, SseSignal(user_id=uid, event="n", data="b"))
        await session.commit()
    assert spy.published == [(uid, "n", "a"), (uid, "n", "b")]
