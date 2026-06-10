"""Integration tests for `POST /setup` (S03.2 P03.2.2).

Covers the happy path (creates admin + initialises household + returns
auto-login TokenPair), the lock-after-init branches (404 on user
exists OR household initialised), Pydantic validation surface, and
the OWASP `no-store` headers.

Idempotence / replay tests in `test_setup_idempotence.py`; concurrency
in `test_setup_race.py`; SQLSTATE discrimination in
`test_setup_unexpected_integrity.py`; cache invalidation in
`test_setup_invalidation.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from httpx import AsyncClient
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.modules.accounts.models import HOUSEHOLD_SINGLETON_UUID, Household
from backend.modules.auth.models import RefreshToken, User, UserRole
from backend.modules.auth.service.jwt import verify_access_token
from backend.modules.auth.service.refresh_tokens import verify_readonly

_HASHER = PasswordHash.recommended()


def _setup_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "email": "admin@example.com",
        "password": "correct-horse-battery-staple",
        "display_name": "Admin",
        "household_name": "Foyer Dupont",
    }
    base.update(overrides)
    return base


async def test_post_setup_happy_path_persists_admin_and_household(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
) -> None:
    resp = await async_client.post("/setup", json=_setup_payload())
    assert resp.status_code == 200

    body = resp.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and body["access_token"]
    assert isinstance(body["refresh_token"], str) and body["refresh_token"]

    # Verify household: exactly one row, fixed singleton UUID,
    # initialized_at set, name matches input, base_currency = EUR.
    households = (await auth_schema.execute(select(Household))).scalars().all()
    assert len(households) == 1
    h = households[0]
    assert h.id == HOUSEHOLD_SINGLETON_UUID
    assert h.name == "Foyer Dupont"
    assert h.base_currency == "EUR"
    assert h.initialized_at is not None

    # Verify user: exactly one admin, email lowercased, Argon2id hash
    # verifies the plaintext, role == admin.
    users = (await auth_schema.execute(select(User))).scalars().all()
    assert len(users) == 1
    u = users[0]
    assert u.email == "admin@example.com"
    assert u.role is UserRole.ADMIN
    assert u.password_hash.startswith("$argon2id$")
    assert _HASHER.verify("correct-horse-battery-staple", u.password_hash)


async def test_post_setup_persists_lowercase_email(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
) -> None:
    """`User._normalize_email` validator must trigger via `create_user`."""
    resp = await async_client.post("/setup", json=_setup_payload(email="Admin@Example.COM"))
    assert resp.status_code == 200
    user = (await auth_schema.execute(select(User))).scalar_one()
    assert user.email == "admin@example.com"


async def test_post_setup_returns_valid_token_pair(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
) -> None:
    """Auto-login (Q7): the access + refresh tokens both verify back to the admin."""
    settings = get_settings()
    resp = await async_client.post("/setup", json=_setup_payload())
    assert resp.status_code == 200
    body = resp.json()

    admin = (
        await auth_schema.execute(select(User).where(User.role == UserRole.ADMIN))
    ).scalar_one()

    assert verify_access_token(body["access_token"], settings=settings) == admin.id
    assert (
        await verify_readonly(auth_schema, body["refresh_token"], settings=settings)
    ) == admin.id


async def test_post_setup_persists_device_label_from_user_agent(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
) -> None:
    ua = "Mozilla/5.0 (X11; Linux x86_64)"
    resp = await async_client.post("/setup", json=_setup_payload(), headers={"user-agent": ua})
    assert resp.status_code == 200
    record = (await auth_schema.execute(select(RefreshToken))).scalar_one()
    assert record.device_label == ua


async def test_post_setup_response_carries_no_store_cache_headers(
    async_client: AsyncClient,
    auth_schema: AsyncSession,  # noqa: ARG001
) -> None:
    """OWASP ASVS V8.3.4 — token-bearing responses must not be cached."""
    resp = await async_client.post("/setup", json=_setup_payload())
    assert resp.status_code == 200
    assert resp.headers.get("Cache-Control") == "no-store"
    assert resp.headers.get("Pragma") == "no-cache"


async def test_post_setup_returns_404_when_household_already_initialized(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
) -> None:
    auth_schema.add(
        Household(
            name="Existing",
            base_currency="EUR",
            initialized_at=datetime.now(tz=UTC),
        )
    )
    await auth_schema.flush()
    resp = await async_client.post("/setup", json=_setup_payload())
    assert resp.status_code == 404


async def test_post_setup_returns_404_when_user_already_exists(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
) -> None:
    auth_schema.add(
        User(
            email="existing@example.com",
            password_hash="x" * 60,
            display_name="Existing",
            role=UserRole.ADMIN,
        )
    )
    await auth_schema.flush()
    resp = await async_client.post("/setup", json=_setup_payload())
    assert resp.status_code == 404


async def test_post_setup_validates_password_min_length(
    async_client: AsyncClient,
    auth_schema: AsyncSession,  # noqa: ARG001
) -> None:
    resp = await async_client.post("/setup", json=_setup_payload(password="short"))
    assert resp.status_code == 422


async def test_post_setup_validates_email_format(
    async_client: AsyncClient,
    auth_schema: AsyncSession,  # noqa: ARG001
) -> None:
    resp = await async_client.post("/setup", json=_setup_payload(email="not-an-email"))
    assert resp.status_code == 422


async def test_post_setup_validates_display_name_not_empty(
    async_client: AsyncClient,
    auth_schema: AsyncSession,  # noqa: ARG001
) -> None:
    resp = await async_client.post("/setup", json=_setup_payload(display_name=""))
    assert resp.status_code == 422


async def test_post_setup_validates_household_name_not_empty(
    async_client: AsyncClient,
    auth_schema: AsyncSession,  # noqa: ARG001
) -> None:
    resp = await async_client.post("/setup", json=_setup_payload(household_name=""))
    assert resp.status_code == 422


async def test_post_setup_second_call_after_init_returns_404(
    async_client: AsyncClient,
    auth_schema: AsyncSession,  # noqa: ARG001
) -> None:
    """Lock-after-init: a successful POST is followed by a permanent 404."""
    first = await async_client.post("/setup", json=_setup_payload())
    assert first.status_code == 200

    # Same payload — must still 404.
    second = await async_client.post("/setup", json=_setup_payload())
    assert second.status_code == 404

    # Different payload — must still 404 (no signal of "already taken").
    third = await async_client.post("/setup", json=_setup_payload(email="other@example.com"))
    assert third.status_code == 404
