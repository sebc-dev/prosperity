"""Events SSE produits sur le mini-bus (S17.1, ADR 0012/0003).

`SseSignal` est dispatché *in-transaction* (`shared.events.dispatch`) par un
producteur (le futur module `notifications`) et collecté par
`sse.service.delivery` pour diffusion **post-commit** (jamais avant — une
transaction rollbackée ne diffuse rien).

⚠️ INVARIANT (ADR 0003) : `data` ne transporte qu'un **signal/id** (JSON), **JAMAIS
de PII**. Le client réveillé re-fetch la donnée sensible via l'API REST authentifiée
(la donnée reste server-only / derrière l'API ; la SSE ne pousse que le « réveil »).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from backend.shared.events import DomainEvent


@dataclass(frozen=True, slots=True)
class SseSignal(DomainEvent):
    """Un signal à pousser à `user_id` (`event` = type, `data` = JSON signal sans PII)."""

    user_id: UUID
    event: str
    data: str
