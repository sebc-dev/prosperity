"""Shared building blocks for the E2E API user journeys.

Plain `async` functions (not fixtures, D9): a journey is an ordered
sequence of HTTP calls, and inline helper calls keep that order explicit
and the per-test statement count under ruff's `PLR0915` ceiling (D10).

The audit helpers read `admin_audit_logs` through a side-channel DB query
(D3): there is no audit-read endpoint yet, so the trail is verified
directly against the `committed_sessionmaker`. Replace with an HTTP call
once such an endpoint exists.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.modules.auth.models import AdminAuditLog, User

# Default admin credentials reused across journeys. The password is ≥12
# chars (SetupRequest / OWASP ASVS V2.1.*); journeys that re-login against
# the admin must use this exact value.
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "correct horse battery staple"


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def bootstrap_admin(
    client: AsyncClient,
    *,
    email: str = ADMIN_EMAIL,
    password: str = ADMIN_PASSWORD,
    display_name: str = "Admin",
    household_name: str = "Foyer Test",
) -> tuple[str, str, str]:
    """POST /setup → (access, refresh, email).

    Creates the first admin + household and locks `/setup` (404 after).
    Asserts 200 — a failure here is a broken precondition for the calling
    journey, not the behaviour under test.
    """
    resp = await client.post(
        "/setup",
        json={
            "email": email,
            "password": password,
            "display_name": display_name,
            "household_name": household_name,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return body["access_token"], body["refresh_token"], email


async def create_invitation(client: AsyncClient, admin_access: str, email: str) -> dict[str, Any]:
    """POST /invitations (Bearer admin) → full body.

    Returns `{id, email, expires_at, token, accept_url}`; the raw token is
    captured from the body (D4), never scraped from logs. Asserts 201.
    """
    resp = await client.post(
        "/invitations",
        json={"email": email},
        headers=auth_headers(admin_access),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def fetch_audit_rows(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> list[tuple[str, object, object]]:
    """Side-channel (D3): `[(action, actor_user_id, target_user_id), …]`.

    Ordered by `created_at`. The order is strict because every audited
    action lives in its own HTTP transaction → its own Postgres `now()`
    (D11). If two audited actions ever share one transaction, add a
    tie-breaker here.
    """
    async with sessionmaker() as session:
        rows = (
            await session.execute(
                select(
                    AdminAuditLog.action,
                    AdminAuditLog.actor_user_id,
                    AdminAuditLog.target_user_id,
                ).order_by(AdminAuditLog.created_at)
            )
        ).all()
    return [(r[0], r[1], r[2]) for r in rows]


async def user_id_by_email(
    sessionmaker: async_sessionmaker[AsyncSession], email: str
) -> object | None:
    """Side-channel (D3): resolve a user's id by email, or None if absent."""
    async with sessionmaker() as session:
        return (
            await session.execute(select(User.id).where(User.email == email))
        ).scalar_one_or_none()
