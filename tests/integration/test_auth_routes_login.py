"""Integration tests for `POST /auth/login` (story S02.4, P02.4.1).

Drives the real httpx → FastAPI → SQLAlchemy stack against a Postgres
testcontainer. `async_client` (cf. `tests/integration/conftest.py`)
overrides `get_db` to yield the test's transactional `db_session`, so
state created by routes is visible to in-test assertions and rolled
back on teardown.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.modules.auth.models import RefreshToken, User
from backend.modules.auth.schemas import DEVICE_LABEL_MAX
from backend.modules.auth.service.jwt import verify_access_token
from backend.modules.auth.service.refresh_tokens import (
    verify as verify_refresh,
)

_settings = get_settings()

UserMaker = Callable[..., Awaitable[User]]


async def test_login_happy_path_returns_token_pair(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(
        email="alice@example.com", password="correct-horse-battery-staple"
    )

    resp = await async_client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "correct-horse-battery-staple"},
        headers={"user-agent": "pytest-client/1.0"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"

    # Access token must verify back to the same user.
    assert verify_access_token(body["access_token"], settings=_settings) == user.id

    # Refresh token must resolve to the user via verify().
    assert await verify_refresh(auth_schema, body["refresh_token"], settings=_settings) == user.id


async def test_login_persists_sanitized_device_label(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="bob@example.com", password="pw")
    ua = "Mozilla/5.0 (X11; Linux x86_64)"

    resp = await async_client.post(
        "/auth/login",
        json={"email": "bob@example.com", "password": "pw"},
        headers={"user-agent": ua},
    )
    assert resp.status_code == 200

    record = (
        await auth_schema.execute(
            select(RefreshToken).where(RefreshToken.user_id == user.id)
        )
    ).scalar_one()
    assert record.device_label == ua


async def test_login_device_label_truncated_at_120_chars(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    """A pathologically long User-Agent is truncated, not rejected."""
    user = await bound_user_factory(email="carla@example.com", password="pw")
    long_ua = "X" * 500

    resp = await async_client.post(
        "/auth/login",
        json={"email": "carla@example.com", "password": "pw"},
        headers={"user-agent": long_ua},
    )
    assert resp.status_code == 200

    record = (
        await auth_schema.execute(
            select(RefreshToken).where(RefreshToken.user_id == user.id)
        )
    ).scalar_one()
    assert record.device_label is not None
    assert len(record.device_label) == DEVICE_LABEL_MAX


async def test_login_strips_bidi_and_zwj_from_device_label(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="dora@example.com", password="pw")
    bidi = "\u202e"  # LEFT-TO-RIGHT OVERRIDE
    zwj = "\u200d"  # ZERO WIDTH JOINER
    # httpx refuses str headers with non-ASCII; bytes are passed through
    # verbatim and the Starlette stack decodes them as latin-1 so the
    # bytes round-trip cleanly into the `Request.headers` `str` value.
    raw_ua = f"Firefox{bidi}/120.0{zwj}".encode()
    # httpx accepts `bytes` header values at runtime; the typeshed stub
    # is too narrow here (it lists only str|str mappings).
    resp = await async_client.post(
        "/auth/login",
        json={"email": "dora@example.com", "password": "pw"},
        headers={"user-agent": raw_ua},  # pyright: ignore[reportArgumentType]
    )
    assert resp.status_code == 200

    record = (
        await auth_schema.execute(
            select(RefreshToken).where(RefreshToken.user_id == user.id)
        )
    ).scalar_one()
    assert record.device_label == "Firefox/120.0"


async def test_login_device_label_none_when_no_user_agent_header(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    """httpx requires an explicit `None` to suppress its default UA."""
    user = await bound_user_factory(email="eve@example.com", password="pw")

    resp = await async_client.post(
        "/auth/login",
        json={"email": "eve@example.com", "password": "pw"},
        headers={"user-agent": ""},
    )
    assert resp.status_code == 200

    record = (
        await auth_schema.execute(
            select(RefreshToken).where(RefreshToken.user_id == user.id)
        )
    ).scalar_one()
    # Empty UA header → sanitize returns None.
    assert record.device_label is None


async def test_login_is_case_insensitive_on_email(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
) -> None:
    """`Alice@example.com` matches a row stored as `alice@example.com`."""
    await bound_user_factory(email="alice@example.com", password="pw")

    resp = await async_client.post(
        "/auth/login",
        json={"email": "Alice@EXAMPLE.com", "password": "pw"},
    )
    assert resp.status_code == 200


async def test_login_rejects_wrong_password(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
) -> None:
    await bound_user_factory(email="fred@example.com", password="real-password")

    resp = await async_client.post(
        "/auth/login",
        json={"email": "fred@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


async def test_login_rejects_unknown_user(async_client: AsyncClient) -> None:
    """Same status and body as wrong-password: no enumeration signal."""
    resp = await async_client.post(
        "/auth/login",
        json={"email": "ghost@example.com", "password": "pw"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


async def test_login_rejects_disabled_user(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    user = await bound_user_factory(email="hank@example.com", password="pw")
    user.disabled_at = datetime.now(tz=UTC)
    await auth_schema.flush()

    resp = await async_client.post(
        "/auth/login",
        json={"email": "hank@example.com", "password": "pw"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


async def test_login_rejects_malformed_email_with_422(
    async_client: AsyncClient,
) -> None:
    resp = await async_client.post(
        "/auth/login",
        json={"email": "not-an-email", "password": "pw"},
    )
    assert resp.status_code == 422


async def test_login_rejects_empty_password_with_422(
    async_client: AsyncClient,
) -> None:
    resp = await async_client.post(
        "/auth/login",
        json={"email": "ivy@example.com", "password": ""},
    )
    assert resp.status_code == 422
