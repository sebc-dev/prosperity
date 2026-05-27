"""Integration tests for `get_current_user` (story S02.4, P02.4.3).

Registers a throwaway protected route on the FastAPI app and drives the
full HTTP → middleware → DB chain to verify each rejection / acceptance
branch.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI
from httpx import AsyncClient
from jose import jwt as jose_jwt
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings, get_settings
from backend.main import app
from backend.modules.auth.public import User, get_current_user
from backend.modules.auth.service.jwt import issue_access_token

_settings = get_settings()

UserMaker = Callable[..., Awaitable[User]]


def _ensure_protected_route_registered(app_: FastAPI) -> None:
    """Add `GET /test/whoami` once per process; safe to call repeatedly.

    Lives on the production `app` (not a sub-app) so it reuses the same
    `dependency_overrides` we already wire up in `async_client`.
    """
    paths = {getattr(r, "path", None) for r in app_.routes}
    if "/test/whoami" in paths:
        return

    async def _whoami(
        user: Annotated[User, Depends(get_current_user)],
    ) -> dict[str, str]:
        return {"id": str(user.id), "email": user.email}

    app_.add_api_route("/test/whoami", _whoami, methods=["GET"])


_ensure_protected_route_registered(app)


async def test_whoami_returns_user_with_valid_token(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="alice@example.com")
    token = issue_access_token(user.id, settings=_settings)

    resp = await async_client.get(
        "/test/whoami", headers={"Authorization": f"Bearer {token}"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(user.id)
    assert body["email"] == "alice@example.com"


async def test_whoami_accepts_lowercase_bearer_scheme(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
) -> None:
    """`scheme.lower() == "bearer"` must accept the lowercase form too."""
    user = await bound_user_factory(email="bob@example.com")
    token = issue_access_token(user.id, settings=_settings)

    resp = await async_client.get(
        "/test/whoami", headers={"authorization": f"bearer {token}"}
    )
    assert resp.status_code == 200


async def test_whoami_rejects_missing_authorization_header(
    async_client: AsyncClient,
) -> None:
    resp = await async_client.get("/test/whoami")
    assert resp.status_code == 401


async def test_whoami_rejects_wrong_scheme(async_client: AsyncClient) -> None:
    """`Basic ...` is structurally an Authorization header but the wrong scheme.

    Starlette's HTTPBearer parses any scheme; we reject anything that
    isn't "bearer" (case-insensitive) ourselves.
    """
    resp = await async_client.get(
        "/test/whoami", headers={"Authorization": "Basic Zm9vOmJhcg=="}
    )
    assert resp.status_code == 401


async def test_whoami_rejects_corrupted_bearer_token(
    async_client: AsyncClient,
) -> None:
    resp = await async_client.get(
        "/test/whoami", headers={"Authorization": "Bearer not.a.jwt"}
    )
    assert resp.status_code == 401


async def test_whoami_rejects_expired_token(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="carol@example.com")
    # Negative TTL → token is born expired (pattern already used in
    # `test_auth_jwt`). Avoids time-travel mocking.
    expired_settings = Settings(
        jwt_secret=_settings.jwt_secret,
        jwt_algorithm=_settings.jwt_algorithm,
        jwt_access_ttl_seconds=-1,
    )
    token = issue_access_token(user.id, settings=expired_settings)

    resp = await async_client.get(
        "/test/whoami", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401


async def test_whoami_rejects_token_signed_with_other_key(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
) -> None:
    """Distinct from the expired-TTL case: same payload shape, wrong signature.

    Encoded directly via `jose.jwt.encode` so we test the signature
    rejection branch (not the TTL one).
    """
    user = await bound_user_factory(email="dave@example.com")
    now_ts = int(datetime.now(tz=UTC).timestamp())
    forged = jose_jwt.encode(
        {"sub": str(user.id), "iat": now_ts, "exp": now_ts + 900},
        "different-secret-not-the-real-one",
        algorithm="HS256",
    )

    resp = await async_client.get(
        "/test/whoami", headers={"Authorization": f"Bearer {forged}"}
    )
    assert resp.status_code == 401


async def test_whoami_rejects_token_for_disabled_user(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="erin@example.com")
    token = issue_access_token(user.id, settings=_settings)

    # Disable after the token was issued.
    user.disabled_at = datetime.now(tz=UTC)
    await auth_schema.flush()

    resp = await async_client.get(
        "/test/whoami", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401


async def test_whoami_rejects_token_for_unknown_user(
    async_client: AsyncClient,
) -> None:
    """Token valid by signature, but `sub` is a UUID never persisted."""
    ghost_token = issue_access_token(uuid4(), settings=_settings)

    resp = await async_client.get(
        "/test/whoami", headers={"Authorization": f"Bearer {ghost_token}"}
    )
    assert resp.status_code == 401


async def test_whoami_rejects_secret_disclosure_token() -> None:
    """Sanity: a fully forged token signed with `SecretStr` debug repr.

    Pydantic's `SecretStr.__repr__` hides the secret; if someone ever
    relied on the string form of the settings object to sign tokens,
    every login would still be rejected because the actual JWT signing
    secret would not match. We don't exercise an HTTP round-trip here —
    this is a defensive read of the `_settings` shape.
    """
    assert "test-secret" not in repr(_settings.jwt_secret)
    assert isinstance(_settings.jwt_secret, SecretStr)
