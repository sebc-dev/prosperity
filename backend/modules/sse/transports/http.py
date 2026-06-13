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

from typing import Annotated

from fastapi import APIRouter, Depends

from backend.config import Settings, get_settings
from backend.modules.auth.public import User, get_current_user, issue_sse_token

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
