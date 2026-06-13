"""Intégration httpx — `GET /sse/stream` (S17.1, P17.1.4).

Couvre le **câblage HTTP** : 401/422 (token), 429 (plafond), ouverture du flux en
`200 text/event-stream`. La LOGIQUE du flux (livraison, heartbeat, expiration,
resync, désinscription) est couverte de façon déterministe au Niveau 1
(`test_sse_stream_generator`) — `is_disconnected()` n'étant pas fiable sous
`ASGITransport`, on ne teste pas la livraison live via httpx ici.

Une fixture autouse restaure le singleton broadcaster après chaque test (la couture
`set_broadcaster` est un état global mutable, cf. D9)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings, get_settings
from backend.main import app
from backend.modules.auth.models import User
from backend.modules.auth.service.jwt import issue_access_token, issue_sse_token
from backend.modules.sse.service.broadcaster import Broadcaster, get_broadcaster, set_broadcaster

_settings = get_settings()
UserMaker = Callable[..., Awaitable[User]]


@pytest.fixture(autouse=True)
def _restore_broadcaster() -> AsyncIterator[None]:  # type: ignore[misc]
    """Restaure le singleton broadcaster d'origine après chaque test (anti-fuite d'état)."""
    original = get_broadcaster()
    yield  # type: ignore[misc]
    set_broadcaster(original)


async def test_stream_without_token_is_422(
    async_client: AsyncClient, auth_schema: AsyncSession
) -> None:
    resp = await async_client.get("/sse/stream")  # token requis manquant
    assert resp.status_code == 422


async def test_stream_with_malformed_token_is_401(
    async_client: AsyncClient, auth_schema: AsyncSession
) -> None:
    resp = await async_client.get("/sse/stream", params={"token": "not.a.jwt"})
    assert resp.status_code == 401


async def test_stream_with_access_token_is_401_wrong_audience(
    async_client: AsyncClient, auth_schema: AsyncSession
) -> None:
    # Un access token (aud=prosperity-api) ne peut pas ouvrir le stream (aud=prosperity-sse).
    access = issue_access_token(uuid4(), settings=_settings)
    resp = await async_client.get("/sse/stream", params={"token": access})
    assert resp.status_code == 401


async def test_stream_with_expired_token_is_401(
    async_client: AsyncClient, auth_schema: AsyncSession
) -> None:
    expired = issue_sse_token(uuid4(), settings=Settings(jwt_sse_ttl_seconds=-60))
    resp = await async_client.get("/sse/stream", params={"token": expired})
    assert resp.status_code == 401


async def test_stream_over_connection_cap_is_429(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    set_broadcaster(Broadcaster(max_conns=0))  # le plafond est atteint d'emblée
    user = await bound_user_factory(email="sse-429@ex.com")
    token = issue_sse_token(user.id, settings=_settings)
    resp = await async_client.get("/sse/stream", params={"token": token})
    assert resp.status_code == 429


async def test_stream_opens_with_event_stream_content_type(
    auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    """Câblage transport : un token SSE valide ouvre le flux en `200 text/event-stream`.

    On ne teste PAS la livraison live ici : sous `ASGITransport`,
    `request.is_disconnected()` n'est pas fiable (le générateur peut se terminer
    aussitôt) — la livraison/heartbeat/expiration/désinscription sont couverts de
    façon DÉTERMINISTE au Niveau 1 (`test_sse_stream_generator`). Le token est
    court-lived (1 s) pour que le flux se draine vite (`close-on-exp`)."""
    set_broadcaster(Broadcaster())
    user = await bound_user_factory(email="sse-open@ex.com")
    token = issue_sse_token(user.id, settings=Settings(jwt_sse_ttl_seconds=1))
    app.dependency_overrides[get_settings] = lambda: Settings(
        jwt_sse_ttl_seconds=1, sse_heartbeat_seconds=0.05
    )
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:

            async def _open_and_drain() -> tuple[int, str]:
                async with client.stream("GET", "/sse/stream", params={"token": token}) as resp:
                    status_code, ctype = resp.status_code, resp.headers["content-type"]
                    async for (
                        _line
                    ) in resp.aiter_lines():  # draine jusqu'à fin (≤ 1 s, close-on-exp)
                        pass
                    return status_code, ctype

            status_code, ctype = await asyncio.wait_for(_open_and_drain(), timeout=8.0)
            assert status_code == 200
            assert ctype.startswith("text/event-stream")
    finally:
        app.dependency_overrides.pop(get_settings, None)
