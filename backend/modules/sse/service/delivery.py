"""Livraison POST-COMMIT des signaux SSE (S17.1, P17.1.5, ADR 0015).

Le mini-bus (`shared.events`) dispatche **in-transaction** — aucun hook post-commit
n'existe. On ne peut PAS diffuser depuis l'intérieur de la transaction (un rollback
diffuserait un event fantôme). Mécanisme (gabarit `accounts/service/setup.py:154`) :
un subscriber async `_collect` empile les `SseSignal` produits dans `session.info`
et arme un listener SQLAlchemy **`after_commit`** qui les flush au broadcaster APRÈS
commit ; un **`after_rollback`** jette la file (rollback → AUCUNE diffusion).

Le broadcaster est résolu via `get_broadcaster()` **au moment du flush** (pas à
l'arming) : un test qui substitue le singleton (`set_broadcaster`) avant le commit
est ainsi pris en compte.
"""

from __future__ import annotations

from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.sse.events import SseSignal
from backend.modules.sse.service.broadcaster import get_broadcaster
from backend.shared.events import subscribe_async

_PENDING = "_sse_pending"


async def _collect(session: AsyncSession, signal: SseSignal) -> None:
    """Subscriber async (in-transaction) : empile + arme la diffusion post-commit.

    Le listener vit DANS `_collect` (par transaction), pas à l'enregistrement global :
    son `once=True` se désarme après le flush, donc la transaction suivante (même
    session) le ré-arme (`if not pending`). `session.info` est porté par la session.
    """
    pending: list[SseSignal] = session.info.setdefault(_PENDING, [])
    if not pending:  # première frame de CETTE transaction → arme le flush/discard

        @sa_event.listens_for(session.sync_session, "after_commit", once=True)
        def _flush(_sync: object) -> None:  # pyright: ignore[reportUnusedFunction]
            broadcaster = get_broadcaster()  # résolu au flush (couture de test, D9)
            for sig in session.info.pop(_PENDING, []):
                broadcaster.publish(sig.user_id, sig.event, sig.data)

        @sa_event.listens_for(session.sync_session, "after_rollback", once=True)
        def _discard(_sync: object) -> None:  # pyright: ignore[reportUnusedFunction]
            session.info.pop(_PENDING, None)  # rollback → rien n'est diffusé

    pending.append(signal)


def register_sse_delivery() -> None:
    """Enregistre la livraison SSE sur le mini-bus (composition root `main.py`, idempotent)."""
    subscribe_async(SseSignal, _collect)
