"""Verrou de l'invariant « event SSE = signal sans PII » (S17.1, ADR 0003).

⚠️ C'est un **verrou de TYPE, pas de contenu** : on garantit que `SseSignal.data`
est une `str` (un signal/id JSON), pas que la chaîne ne contient pas de PII. La
garde de CONTENU appartient au producteur (futur module `notifications`) — dette
assumée. Ici on verrouille la forme : `data` est une chaîne opaque que le client
re-fetch via REST, jamais un payload riche server-side."""

from __future__ import annotations

from uuid import uuid4

from backend.modules.sse.events import SseSignal


def test_sse_signal_data_is_a_string() -> None:
    sig = SseSignal(user_id=uuid4(), event="notification", data='{"id": "abc"}')
    assert isinstance(sig.data, str)
    assert isinstance(sig.event, str)
