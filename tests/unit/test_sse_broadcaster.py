"""Tests unitaires DB-free du broadcaster SSE (S17.1, P17.1.3).

Structure pure : horloge injectée (`_Clock`), pas d'event loop requis
(`asyncio.Queue` n'est manipulée qu'en `put_nowait`/`get_nowait`/`qsize`)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from backend.modules.sse.service.broadcaster import (
    OVERFLOW_FRAME,
    Broadcaster,
    TooManyConnections,
)


class _Clock:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def _bc(clock: _Clock, **caps: float) -> Broadcaster:
    return Broadcaster(now_fn=clock, **caps)


def test_broadcast_reaches_all_connections_of_a_user() -> None:
    bc = _bc(_Clock())
    user = uuid4()
    q1, q2 = bc.connect(user), bc.connect(user)
    bc.publish(user, "notification", '{"id": 1}')
    assert q1.get_nowait().data == '{"id": 1}'
    assert q2.get_nowait().data == '{"id": 1}'


def test_disconnect_of_one_tab_does_not_affect_the_other() -> None:
    # Piège fan-out multi-onglets : déconnecter une queue ne doit PAS couper l'autre.
    bc = _bc(_Clock())
    user = uuid4()
    q1, q2 = bc.connect(user), bc.connect(user)
    bc.disconnect(user, q1)
    bc.publish(user, "n", '{"id": 1}')
    assert q1.qsize() == 0  # l'onglet fermé ne reçoit plus rien
    assert q2.get_nowait().data == '{"id": 1}'  # l'onglet resté ouvert reçoit toujours


def test_slow_consumer_overflow_is_disconnected_and_poisoned() -> None:
    # File de fan-out bornée (anti-DoS slow consumer) : au-delà de `max_queue`, la
    # connexion lente est retirée du fan-out et reçoit OVERFLOW_FRAME (→ fermeture + resync).
    bc = _bc(_Clock(), max_queue=2)
    user = uuid4()
    slow = bc.connect(user)
    for i in range(5):  # 5 publications, file de 2 jamais drainée
        bc.publish(user, "n", str(i))
    drained = []
    while slow.qsize():
        drained.append(slow.get_nowait())
    assert OVERFLOW_FRAME in drained  # sentinelle poussée au consommateur trop lent
    # La connexion morte ne reçoit plus rien (retirée du fan-out) ; un nouvel onglet, lui, reçoit.
    fresh = bc.connect(user)
    bc.publish(user, "n", "after")
    assert slow.qsize() == 0
    assert fresh.get_nowait().data == "after"


def test_publish_is_isolated_per_user() -> None:
    bc = _bc(_Clock())
    alice, bob = uuid4(), uuid4()
    qb = bc.connect(bob)
    bc.publish(alice, "n", "{}")
    assert qb.qsize() == 0  # Bob ne reçoit JAMAIS l'event d'Alice


def test_eviction_after_ttl() -> None:
    clock = _Clock()
    bc = _bc(clock, ttl_seconds=10.0)
    user = uuid4()
    bc.publish(user, "n", "a")  # id=1 à t=1000
    clock.t += 20.0  # au-delà du TTL (10s)
    bc.publish(user, "n", "b")  # id=2 à t=1020 → id=1 évincé
    # Client à last_id=0 : il attend id=1 (évincé) → gap → resync.
    assert bc.replay_after(user, 0) is None
    # Client à last_id=1 : il a vu 1, reçoit 2 (contigu, pas de gap).
    assert [f.id for f in (bc.replay_after(user, 1) or [])] == [2]


def test_overflow_evicts_oldest() -> None:
    bc = _bc(_Clock(), max_events=3)
    user = uuid4()
    for i in range(5):
        bc.publish(user, "n", str(i))  # ids 1..5, buffer garde les 3 derniers (3,4,5)
    frames = bc.replay_after(user, 2) or []
    assert [f.id for f in frames] == [3, 4, 5]
    assert bc.replay_after(user, 1) is None  # id 2 évincé → gap → resync


def test_connection_cap_fails_closed() -> None:
    bc = _bc(_Clock(), max_conns=2)
    user = uuid4()
    bc.connect(user)
    bc.connect(user)
    with pytest.raises(TooManyConnections):
        bc.connect(user)


def test_disconnect_gcs_empty_channel() -> None:
    bc = _bc(_Clock())
    user = uuid4()
    q = bc.connect(user)
    bc.disconnect(user, q)
    # 0 conn + buffer vide → channel GC'd → reconnexion avec last_id → resync.
    assert bc.replay_after(user, 5) is None
    assert bc.replay_after(user, None) == []  # connexion fraîche → live only


def test_replay_after_semantics() -> None:
    bc = _bc(_Clock())
    user = uuid4()
    for i in range(3):
        bc.publish(user, "n", str(i))  # ids 1,2,3
    assert bc.replay_after(user, None) == []  # fraîche → pas de replay
    assert bc.replay_after(user, 3) == []  # à jour
    assert bc.replay_after(user, 9) == []  # id forgé futur → rien
    assert [f.id for f in (bc.replay_after(user, 1) or [])] == [2, 3]  # post-id
    assert bc.replay_after(user, -5) is None  # id forgé ancien → resync, jamais d'exception
