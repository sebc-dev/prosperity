"""HTTP transport du canal SSE (S17.1, ADR 0012).

`POST /sse/token` échange le JWT bearer normal (auth `get_current_user`) contre un
token SSE **scopé** (audience dédiée `prosperity-sse`, TTL 5 min) que le client
passe ensuite en query param à `GET /sse/stream?token=…` (l'API `EventSource` ne
peut pas envoyer de header `Authorization`).

Interne au module `sse` ; importe `auth.public` (token + dépendance d'auth) et la
config — directions légales (contrat `2-sse`, second-hops `auth.public → auth.X`
déjà ignorés). Le routeur n'applique **aucune** politique CORS permissive : le
stream n'est protégé que par le token query (pas de header custom requis).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from backend.config import Settings, get_settings
from backend.modules.auth.public import (
    InvalidTokenError,
    User,
    get_current_user,
    issue_sse_token,
    verify_sse_token,
)
from backend.modules.sse.service.broadcaster import (
    Broadcaster,
    SseFrame,
    TooManyConnections,
    get_broadcaster,
)

sse_router = APIRouter(prefix="/sse", tags=["sse"])

CurrentUser = Annotated[User, Depends(get_current_user)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@sse_router.post("/token")
async def issue_token(user: CurrentUser, settings: SettingsDep) -> dict[str, object]:
    """Émet un token SSE scopé 5 min pour le user authentifié (ADR 0012).

    Le client ouvre ensuite `GET /sse/stream?token=<token>`. Le token a l'audience
    `prosperity-sse` (cloisonnée de l'access token, ADR 0016) et expire en 5 min.
    """
    return {
        "token": issue_sse_token(user.id, settings=settings),
        "expires_in": settings.jwt_sse_ttl_seconds,
    }


def _format(frame: SseFrame) -> str:
    """Sérialise une frame au format wire SSE (`id:`/`event:`/`data:` + ligne vide)."""
    return f"id: {frame.id}\nevent: {frame.event}\ndata: {frame.data}\n\n"


def _parse_last_event_id(raw: str | None) -> int | None:
    """`Last-Event-ID` défensif : un id malformé/forgé → `None` (traité en connexion
    fraîche, live only) ; jamais d'exception. L'`EventSource` standard renvoie l'`id:`
    entier que nous avons émis, donc un non-entier ne vient que d'un client forgé."""
    if raw is None:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


async def _event_stream(  # noqa: PLR0913 — générateur pur paramétré pour la testabilité (D9)
    request: Request,
    user_id: UUID,
    conn: asyncio.Queue[SseFrame],
    exp_ts: int,
    *,
    broadcaster: Broadcaster,
    now_fn: Callable[[], int],
    heartbeat_s: float,
    replay: list[SseFrame] | None,
) -> AsyncIterator[str]:
    """Générateur `text/event-stream`. PUR et paramétré (D9) : testable hors HTTP avec
    un `request` espion (`is_disconnected` contrôlable), un `broadcaster`/`now_fn`
    injectés. Rejoue `replay` (ou un frame `resync` si hors fenêtre), puis stream live
    avec heartbeat ; se ferme au disconnect OU à l'expiration du token (anti slow-loris).
    `finally: disconnect` garantit la désinscription même sur `aclose()` (anti-fuite)."""
    try:
        if replay is None:
            yield "event: resync\ndata: {}\n\n"  # hors fenêtre → le client re-sync REST
        else:
            for frame in replay:
                yield _format(frame)
        while not await request.is_disconnected():
            remaining = exp_ts - now_fn()
            if remaining <= 0:
                break  # token expiré → fermeture du flux (durée de vie ≤ TTL)
            try:
                frame = await asyncio.wait_for(conn.get(), timeout=min(heartbeat_s, remaining))
                yield _format(frame)
            except TimeoutError:
                yield ": heartbeat\n\n"  # commentaire SSE = heartbeat (sous l'idle timeout)
    finally:
        broadcaster.disconnect(user_id, conn)


@sse_router.get("/stream")
async def stream(
    request: Request, settings: SettingsDep, token: Annotated[str, Query()]
) -> StreamingResponse:
    """Flux SSE authentifié par le token query (ADR 0012). 401 si token invalide,
    429 si le user dépasse son plafond de connexions (vérifié AVANT de streamer)."""
    try:
        user_id, exp_ts = verify_sse_token(token, settings=settings)
    except InvalidTokenError as exc:  # couvre ExpiredTokenError (sous-classe)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid SSE token") from exc
    broadcaster = get_broadcaster()
    last_id = _parse_last_event_id(request.headers.get("last-event-id"))
    try:
        conn = broadcaster.connect(user_id)  # plafond → 429 fail-closed, avant le stream
    except TooManyConnections as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many SSE streams") from exc
    replay = broadcaster.replay_after(user_id, last_id)
    return StreamingResponse(
        _event_stream(
            request,
            user_id,
            conn,
            exp_ts,
            broadcaster=broadcaster,
            now_fn=lambda: int(datetime.now(tz=UTC).timestamp()),
            heartbeat_s=settings.sse_heartbeat_seconds,
            replay=replay,
        ),
        media_type="text/event-stream",
    )
