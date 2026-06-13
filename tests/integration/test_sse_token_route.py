"""Intégration — `POST /sse/token` (S17.1, ADR 0012).

Échange le JWT bearer normal contre un token SSE scopé. Gabarit
`test_accounts_routes_list.py` (`async_client` + `Bearer issue_access_token`)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.modules.auth.models import User
from backend.modules.auth.service.jwt import issue_access_token, verify_sse_token

_settings = get_settings()
UserMaker = Callable[..., Awaitable[User]]


def _bearer(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


async def test_post_token_requires_auth(
    async_client: AsyncClient, auth_schema: AsyncSession
) -> None:
    resp = await async_client.post("/sse/token")
    assert resp.status_code == 401


async def test_post_token_returns_scoped_sse_token(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    user = await bound_user_factory(email="sse-token@ex.com")
    resp = await async_client.post("/sse/token", headers=_bearer(user.id))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["expires_in"] == 300  # noqa: PLR2004 — TTL SSE (5 min)
    # Le token renvoyé est un VRAI token SSE pour ce user (audience prosperity-sse).
    verified_id, _exp = verify_sse_token(body["token"], settings=_settings)
    assert verified_id == user.id
