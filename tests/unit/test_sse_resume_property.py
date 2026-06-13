"""Property Hypothesis du resume `Last-Event-ID` (S17.1, D8).

Le ring buffer est une structure PURE (in-memory, sans I/O) → Hypothesis y est
légitime (exception §4.2 documentée). L'horloge est FIGÉE (constante + TTL géant)
pour isoler la sémantique d'**id** de l'éviction temporelle (couverte example-based
dans `test_sse_broadcaster`). On vérifie des **invariants relationnels** (monotonie,
contiguïté, partition exacte exactly-once, idempotence), PAS un oracle-miroir de
`replay_after`."""

from __future__ import annotations

from uuid import uuid4

from hypothesis import example, given
from hypothesis import strategies as st

from backend.modules.sse.service.broadcaster import Broadcaster

_FROZEN = 1000.0  # horloge constante → aucune éviction temporelle


def _channel_with(n: int, max_events: int) -> tuple[Broadcaster, object]:
    bc = Broadcaster(now_fn=lambda: _FROZEN, max_events=max_events, ttl_seconds=1e9)
    user = uuid4()
    for i in range(n):
        bc.publish(user, "n", str(i))  # ids 1..n
    return bc, user


@given(
    n=st.integers(min_value=0, max_value=30),
    max_events=st.integers(min_value=1, max_value=8),
    last_id=st.integers(min_value=-3, max_value=35),
)
@example(n=5, max_events=8, last_id=5)  # last_id == dernier → []
@example(n=0, max_events=3, last_id=0)  # buffer vide
@example(n=10, max_events=3, last_id=1)  # gap (id 1 évincé par overflow) → None
@example(n=4, max_events=8, last_id=-1)  # id forgé négatif → None
def test_replay_after_is_exactly_once(n: int, max_events: int, last_id: int) -> None:
    bc, user = _channel_with(n, max_events)
    # Fenêtre attendue : les `max_events` derniers ids (horloge figée → pas d'éviction TTL).
    buf_ids = list(range(max(1, n - max_events + 1), n + 1)) if n else []

    result = bc.replay_after(user, last_id)  # type: ignore[arg-type]

    if result is None:
        if n == 0:
            # Aucun event publié → pas de channel : un `last_id` présenté ne peut être
            # confirmé contigu → resync (seul `None` non-`last_id` donnerait `[]`).
            assert last_id is not None
        else:
            # `None` UNIQUEMENT en cas de gap réel : des events plus récents que
            # `last_id` existent (`last_id < n`) mais ne sont pas rejouables contigument.
            assert last_id < n
            assert buf_ids and buf_ids[0] > last_id + 1
        return

    ids = [f.id for f in result]
    # (1) monotonie stricte + contiguïté (consécutifs) — pas de trou ni doublon.
    assert ids == sorted(set(ids))
    assert all(b - a == 1 for a, b in zip(ids, ids[1:], strict=False))
    # (2) tous strictement postérieurs à last_id.
    assert all(i > last_id for i in ids)
    # (3) partition EXACTE de la fenêtre : {rejoués} ⊎ {≤ last_id} == fenêtre, sans recouvrement.
    below = {i for i in buf_ids if i <= last_id}
    assert set(ids).isdisjoint(below)
    assert set(ids) | below == set(buf_ids)
    # (4) si non vide, va jusqu'au dernier event (exactly-once jusqu'à la tête).
    if ids:
        assert ids[-1] == n
    # (5) idempotence.
    second = bc.replay_after(user, last_id)  # type: ignore[arg-type]
    assert second is not None
    assert [f.id for f in second] == ids
