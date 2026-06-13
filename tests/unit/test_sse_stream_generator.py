"""Tests DÉTERMINISTES du générateur `_event_stream` (S17.1, P17.1.4, D9).

Le générateur est pur et paramétré → on le pilote **hors HTTP** avec un `request`
espion (`is_disconnected` contrôlable), un `broadcaster` espion, une `now_fn`
injectée. C'est la vraie réponse au `request.is_disconnected()` non fiable sous
`httpx.ASGITransport` : ici aucun transport, le disconnect/expiration sont pilotés
à la main. Couvre replay/resync/heartbeat/expiration-mid-stream/désinscription/aclose."""

# Le test pilote des helpers internes du transport (`_event_stream`, `_format`,
# `_parse_last_event_id`) — désactivation `reportPrivateUsage` au fichier (convention repo).
# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest

from backend.modules.sse.service.broadcaster import OVERFLOW_FRAME, SseFrame
from backend.modules.sse.transports.http import _event_stream, _format, _parse_last_event_id


def test_parse_last_event_id_is_defensive() -> None:
    # Un `Last-Event-ID` valide est parsé ; absent ou forgé/malformé → None (jamais d'exception).
    assert _parse_last_event_id("5") == 5
    assert _parse_last_event_id("-3") == -3
    assert _parse_last_event_id(None) is None
    assert _parse_last_event_id("abc") is None
    assert _parse_last_event_id("") is None


class _SpyRequest:
    def __init__(self, *, disconnected: bool = False) -> None:
        self._disconnected = disconnected

    async def is_disconnected(self) -> bool:
        return self._disconnected


class _SpyBroadcaster:
    def __init__(self) -> None:
        self.disconnects: list[object] = []

    def disconnect(self, user_id: object, conn: object) -> None:
        self.disconnects.append((user_id, conn))


def _gen(  # noqa: PLR0913 — fabrique de test paramétrable
    *,
    replay: list[SseFrame] | None,
    disconnected: bool = False,
    now: int = 0,
    exp: int = 10_000,
    heartbeat: float = 0.01,
    conn: asyncio.Queue[SseFrame] | None = None,
) -> tuple[AsyncGenerator[str], asyncio.Queue[SseFrame], _SpyBroadcaster]:
    queue: asyncio.Queue[SseFrame] = conn if conn is not None else asyncio.Queue()
    bc = _SpyBroadcaster()
    gen = _event_stream(
        _SpyRequest(disconnected=disconnected),  # type: ignore[arg-type]
        uuid4(),
        queue,
        exp,
        broadcaster=bc,  # type: ignore[arg-type]
        now_fn=lambda: now,
        heartbeat_s=heartbeat,
        replay=replay,
    )
    return gen, queue, bc


async def test_resync_frame_when_replay_none() -> None:
    gen, _q, bc = _gen(replay=None, disconnected=True)
    assert await anext(gen) == "event: resync\ndata: {}\n\n"
    with pytest.raises(StopAsyncIteration):
        await anext(gen)
    assert len(bc.disconnects) == 1  # désinscription garantie (finally)


async def test_replay_frames_emitted_in_order() -> None:
    f1, f2 = SseFrame(1, "n", "a"), SseFrame(2, "n", "b")
    gen, _q, bc = _gen(replay=[f1, f2], disconnected=True)
    assert await anext(gen) == _format(f1)
    assert await anext(gen) == _format(f2)
    with pytest.raises(StopAsyncIteration):
        await anext(gen)
    assert bc.disconnects


async def test_live_frame_delivered_from_queue() -> None:
    queue: asyncio.Queue[SseFrame] = asyncio.Queue()
    gen, _q, _bc = _gen(replay=[], conn=queue)
    queue.put_nowait(SseFrame(7, "notification", '{"x": 1}'))
    assert await anext(gen) == _format(SseFrame(7, "notification", '{"x": 1}'))


async def test_heartbeat_on_idle() -> None:
    gen, _q, _bc = _gen(replay=[], heartbeat=0.01)  # aucune frame → timeout → heartbeat
    assert await anext(gen) == ": heartbeat\n\n"


async def test_stream_closes_when_token_expired() -> None:
    gen, _q, bc = _gen(replay=[], now=2000, exp=1000)  # remaining = -1000 ≤ 0
    with pytest.raises(StopAsyncIteration):
        await anext(gen)
    assert bc.disconnects  # fermeture + désinscription


async def test_overflow_frame_closes_stream() -> None:
    # Consommateur trop lent : le broadcaster pousse OVERFLOW_FRAME → le flux se ferme
    # (le client rouvre et resync) et la désinscription a lieu (finally).
    queue: asyncio.Queue[SseFrame] = asyncio.Queue()
    gen, _q, bc = _gen(replay=[], conn=queue)
    queue.put_nowait(OVERFLOW_FRAME)
    with pytest.raises(StopAsyncIteration):
        await anext(gen)
    assert bc.disconnects  # fermeture + désinscription, jamais d'émission de la sentinelle


async def test_aclose_runs_disconnect() -> None:
    f1 = SseFrame(1, "n", "a")
    gen, _q, bc = _gen(replay=[f1])
    await anext(gen)  # entre dans le try (yield f1)
    await gen.aclose()  # fermeture côté serveur → finally
    assert bc.disconnects
