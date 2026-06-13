"""Broadcaster SSE in-memory + ring buffer par user (S17.1, ADR 0012).

Structure PURE (aucune I/O, aucune DB) : un `_UserChannel` par user porte un ring
buffer (5 min / 100 events, `now_fn` injectable pour l'éviction) et un ensemble de
connexions (`asyncio.Queue`, une par onglet, plafonnées). Le `replay_after`
implémente le resume `Last-Event-ID` (exactly-once, capé à la fenêtre).

⚠️ MONO-PROCESS : le registre vit dans le process. En multi-worker, un `publish`
sur le worker A n'atteint pas une connexion sur le worker B (runbook : 1 worker /
backplane futur).

⚠️ ISOLATION : `publish`/`connect`/`replay_after` indexent sur `user_id` (le `sub`
du token vérifié, jamais un paramètre client) → un user ne reçoit JAMAIS les events
d'un autre. `Last-Event-ID` (fourni par le client) n'indexe QUE le buffer du user
authentifié ; un id forgé/hors-fenêtre déclenche un resync, jamais la lecture du
buffer d'autrui (cf. `replay_after`).

D9 (testabilité) : singleton module-level + `get_broadcaster`/`set_broadcaster`,
partagé par la route (`transports.http`) ET le subscriber post-commit
(`service.delivery`), tous deux via `get_broadcaster()` au runtime.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

_BUFFER_TTL_SECONDS = 300.0  # 5 min (ADR 0012)
_BUFFER_MAX_EVENTS = 100  # 100 events par user (ADR 0012)
_MAX_CONNS_PER_USER = 8  # plafond anti-DoS (multi-onglets bornés)


class TooManyConnections(Exception):
    """Levée par `connect` quand un user dépasse `max_conns` (→ 429 fail-closed)."""


@dataclass(frozen=True, slots=True)
class SseFrame:
    """Un event SSE. `id` est monotone PAR user (sert le `Last-Event-ID`).

    `data` = JSON signal/id — JAMAIS de PII (ADR 0003 : le client re-fetch via REST).
    """

    id: int
    event: str
    data: str


class _UserChannel:
    """Ring buffer horodaté + connexions d'un user. PUR, `now_fn` injectable."""

    def __init__(
        self,
        *,
        now_fn: Callable[[], float],
        ttl_seconds: float = _BUFFER_TTL_SECONDS,
        max_events: int = _BUFFER_MAX_EVENTS,
        max_conns: int = _MAX_CONNS_PER_USER,
    ) -> None:
        self._now_fn = now_fn
        self._ttl = ttl_seconds
        self._max_conns = max_conns
        self._counter = 0  # dernier id attribué (monotone, jamais réinitialisé)
        self._buffer: deque[tuple[SseFrame, float]] = deque(maxlen=max_events)
        self._conns: set[asyncio.Queue[SseFrame]] = set()

    def _evict(self) -> None:
        """Purge paresseuse des frames plus vieilles que `ttl` (gauche du deque)."""
        cutoff = self._now_fn() - self._ttl
        while self._buffer and self._buffer[0][1] < cutoff:
            self._buffer.popleft()

    def publish(self, event: str, data: str) -> SseFrame:
        self._counter += 1
        frame = SseFrame(id=self._counter, event=event, data=data)
        self._evict()
        self._buffer.append((frame, self._now_fn()))
        for q in self._conns:
            q.put_nowait(frame)  # fan-out non bloquant (queue non bornée par conn)
        return frame

    def replay_after(self, last_id: int | None) -> list[SseFrame] | None:
        """Frames à rejouer pour un `Last-Event-ID`.

        - `None` : aucun `Last-Event-ID` (connexion fraîche) → `[]` (live only).
        - `last_id >= dernier id` : client à jour ou en avance (id forgé futur) → `[]`.
        - **gap** (buffer vide alors que des events existaient, ou plus ancien id
          bufferisé `> last_id + 1` : des events ont été évincés / id forgé ancien)
          → `None` (le client DOIT re-sync REST ; jamais un replay partiel trompeur,
          jamais le buffer d'un autre user).
        - sinon : la sous-séquence **contiguë** des frames d'id `> last_id` (exactly-once).
        """
        self._evict()
        if last_id is None or last_id >= self._counter:
            return []
        if not self._buffer:
            return None  # des events ont existé (last_id < counter) mais tous évincés
        oldest = self._buffer[0][0].id
        if oldest > last_id + 1:
            return None  # gap : events entre last_id et oldest évincés (ou id forgé ancien)
        return [frame for frame, _ts in self._buffer if frame.id > last_id]

    def connect(self) -> asyncio.Queue[SseFrame]:
        if len(self._conns) >= self._max_conns:
            raise TooManyConnections
        q: asyncio.Queue[SseFrame] = asyncio.Queue()
        self._conns.add(q)
        return q

    def disconnect(self, q: asyncio.Queue[SseFrame]) -> None:
        self._conns.discard(q)

    def is_collectible(self) -> bool:
        """Vrai ssi le channel peut être GC (0 connexion ET buffer vide après éviction)."""
        self._evict()
        return not self._conns and not self._buffer


class Broadcaster:
    """Registre `user_id → _UserChannel`. Isolation par user (cf. module docstring)."""

    def __init__(self, *, now_fn: Callable[[], float] = time.monotonic, **caps: float) -> None:
        self._now_fn = now_fn
        self._caps = caps  # ttl_seconds / max_events / max_conns optionnels (tests)
        self._users: dict[UUID, _UserChannel] = {}

    def _channel(self, user_id: UUID) -> _UserChannel:
        channel = self._users.get(user_id)
        if channel is None:
            channel = _UserChannel(now_fn=self._now_fn, **self._caps)  # type: ignore[arg-type]
            self._users[user_id] = channel
        return channel

    def publish(self, user_id: UUID, event: str, data: str) -> SseFrame:
        return self._channel(user_id).publish(event, data)

    def connect(self, user_id: UUID) -> asyncio.Queue[SseFrame]:
        return self._channel(user_id).connect()

    def disconnect(self, user_id: UUID, q: asyncio.Queue[SseFrame]) -> None:
        channel = self._users.get(user_id)
        if channel is None:
            return
        channel.disconnect(q)
        if channel.is_collectible():  # GC : 0 conn + buffer vide → borne le nb de channels
            del self._users[user_id]

    def replay_after(self, user_id: UUID, last_id: int | None) -> list[SseFrame] | None:
        channel = self._users.get(user_id)
        if channel is None:
            # Pas de channel : connexion fraîche → live ; reconnexion (last_id fourni)
            # sur un channel GC'd/jamais créé → resync (le buffer n'existe pas/plus).
            return [] if last_id is None else None
        return channel.replay_after(last_id)


# ── D9 : singleton module-level + couture de remplacement test ─────────────────
_broadcaster = Broadcaster()


def get_broadcaster() -> Broadcaster:
    """Le broadcaster partagé (route + subscriber post-commit l'appellent au runtime)."""
    return _broadcaster


def set_broadcaster(broadcaster: Broadcaster) -> None:
    """**Test-only** : substitue le singleton (un autouse fixture restaure l'original)."""
    global _broadcaster  # noqa: PLW0603 — couture de test assumée (cf. D9)
    _broadcaster = broadcaster
