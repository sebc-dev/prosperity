"""Integration tests for `/auth/refresh` and `/auth/logout` (S02.4, P02.4.2).

Exercises rotation, replay detection, family invalidation, and the
uniform 401 / idempotent 204 mappings via the real HTTP stack.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.modules.auth.models import RefreshToken, User
from backend.modules.auth.service.jwt import verify_access_token
from backend.modules.auth.service.refresh_tokens import (
    hash_refresh_token,
)
from backend.modules.auth.service.refresh_tokens import (
    issue as issue_refresh,
)

_settings = get_settings()

UserMaker = Callable[..., Awaitable[User]]


async def _login(client: AsyncClient, email: str, password: str) -> tuple[str, str]:
    resp = await client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return body["access_token"], body["refresh_token"]


# -----------------------------------------------------------------------------
# /auth/refresh
# -----------------------------------------------------------------------------


async def test_refresh_happy_path_returns_new_pair(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="alice@example.com", password="pw")
    _, refresh_token = await _login(async_client, "alice@example.com", "pw")

    resp = await async_client.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["refresh_token"] != refresh_token
    # New access token decodes back to the same user.
    assert verify_access_token(body["access_token"], settings=_settings) == user.id


async def test_refresh_preserves_family_and_chains_parent_id(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="bob@example.com", password="pw")
    _, refresh_token = await _login(async_client, "bob@example.com", "pw")
    parent = (
        await auth_schema.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_refresh_token(refresh_token, settings=_settings)
            )
        )
    ).scalar_one()

    resp = await async_client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    new_refresh = resp.json()["refresh_token"]

    child = (
        await auth_schema.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_refresh_token(new_refresh, settings=_settings)
            )
        )
    ).scalar_one()
    assert child.family_id == parent.family_id
    assert child.parent_id == parent.id
    assert child.user_id == user.id


async def test_refresh_reuse_returns_401_and_invalidates_family(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    """Presenting the same refresh token twice = replay → family torched.

    After the second attempt the new child returned by the first rotation
    must also be revoked: the legitimate user loses their session — that
    is the cost of replay detection and is the intended behaviour.

    Note on isolation: `auth_schema` shares the test connection with the
    request session (via `join_transaction_mode="create_savepoint"` in
    `conftest.py:_override_get_db`), so the family read below sees the
    commit `rotate()` performs through that savepoint. The true
    cross-connection pinning for ADR 0015 (family commit survives a
    caller-side rollback against an independent connection) lives in
    `test_refresh_tokens_race.py::test_rotate_replay_family_invalidation_persists_across_sessions`.
    """
    await bound_user_factory(email="carol@example.com", password="pw")
    _, refresh_token = await _login(async_client, "carol@example.com", "pw")

    first = await async_client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert first.status_code == 200
    new_refresh = first.json()["refresh_token"]
    family_id = (
        await auth_schema.execute(
            select(RefreshToken.family_id).where(
                RefreshToken.token_hash == hash_refresh_token(refresh_token, settings=_settings)
            )
        )
    ).scalar_one()

    # Replay the original token: must 401 + nuke the family.
    replay = await async_client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert replay.status_code == 401
    assert replay.json()["detail"] == "Invalid refresh token"

    # Every row in the family must now be revoked (the new child included).
    rows = (
        await auth_schema.execute(
            select(RefreshToken.revoked_at).where(RefreshToken.family_id == family_id)
        )
    ).all()
    assert all(row.revoked_at is not None for row in rows)

    # The replacement token issued by the first rotation must also fail.
    aftermath = await async_client.post("/auth/refresh", json={"refresh_token": new_refresh})
    assert aftermath.status_code == 401


async def test_refresh_unknown_token_returns_401(async_client: AsyncClient) -> None:
    resp = await async_client.post("/auth/refresh", json={"refresh_token": "never-existed"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid refresh token"


async def test_refresh_expired_token_returns_401(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="dora@example.com", password="pw")
    raw = "expired-refresh-target"
    now = datetime.now(tz=UTC)
    auth_schema.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw, settings=_settings),
            issued_at=now - timedelta(days=31),
            expires_at=now - timedelta(seconds=1),
        )
    )
    await auth_schema.flush()

    resp = await async_client.post("/auth/refresh", json={"refresh_token": raw})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid refresh token"


async def test_refresh_revoked_token_returns_401(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="erin@example.com", password="pw")
    raw = await issue_refresh(auth_schema, user.id, settings=_settings)
    # Revoke directly (skipping rotate's path).
    await auth_schema.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(raw, settings=_settings))
        .values(revoked_at=datetime.now(tz=UTC))
    )
    await auth_schema.flush()

    resp = await async_client.post("/auth/refresh", json={"refresh_token": raw})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid refresh token"


async def test_refresh_empty_token_returns_422(async_client: AsyncClient) -> None:
    """Pydantic `min_length=1` short-circuits before the service is touched.

    422 (not 401) is the deliberate distinction: the request body itself
    is malformed, so the client gets a validation error rather than the
    generic auth failure mapping.
    """
    resp = await async_client.post("/auth/refresh", json={"refresh_token": ""})
    assert resp.status_code == 422


# -----------------------------------------------------------------------------
# /auth/logout
# -----------------------------------------------------------------------------


async def test_logout_revokes_then_subsequent_refresh_fails(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
) -> None:
    await bound_user_factory(email="frank@example.com", password="pw")
    _, refresh_token = await _login(async_client, "frank@example.com", "pw")

    logout = await async_client.post("/auth/logout", json={"refresh_token": refresh_token})
    assert logout.status_code == 204

    follow_up = await async_client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert follow_up.status_code == 401


async def test_logout_unknown_token_returns_204(async_client: AsyncClient) -> None:
    """Idempotent: no row → still 204, no enumeration signal."""
    resp = await async_client.post("/auth/logout", json={"refresh_token": "never-existed"})
    assert resp.status_code == 204


async def test_logout_already_revoked_token_returns_204(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
) -> None:
    await bound_user_factory(email="gina@example.com", password="pw")
    _, refresh_token = await _login(async_client, "gina@example.com", "pw")

    first = await async_client.post("/auth/logout", json={"refresh_token": refresh_token})
    assert first.status_code == 204

    second = await async_client.post("/auth/logout", json={"refresh_token": refresh_token})
    assert second.status_code == 204


async def test_logout_empty_token_returns_422(async_client: AsyncClient) -> None:
    resp = await async_client.post("/auth/logout", json={"refresh_token": ""})
    assert resp.status_code == 422
