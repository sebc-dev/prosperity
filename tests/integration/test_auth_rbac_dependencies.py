"""Integration tests for the RBAC guards `require_admin` / `require_member`
(story S04.1, P04.1.2).

Registers throwaway admin-gated and member-gated routes on the
production `app` and drives the full HTTP → `get_current_user` → role
check chain. Authentication failures (anonymous / disabled) are relayed
by `get_current_user` as a uniform 401; an authenticated-but-wrong-role
request is a 403 with a constant `{"detail": "Forbidden"}` body that
never names the required role (anti-enumeration).

The 401 causes themselves (expired/forged/unknown token) are already
pinned exhaustively by `test_auth_get_current_user.py` and are not
duplicated here — we only assert that the *anonymous* case still 401s
through the guard, confirming the layering.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Annotated
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.main import app
from backend.modules.auth.public import (
    User,
    UserRole,
    get_current_user,
    require_admin,
    require_member,
)
from backend.modules.auth.service.jwt import issue_access_token

_settings = get_settings()

_EXPECTED_403_BODY = {"detail": "Forbidden"}

UserMaker = Callable[..., Awaitable[User]]


def _assert_forbidden(resp) -> None:
    assert resp.status_code == 403
    # Exact body: the guard never leaks which role was required, so an
    # authenticated member cannot enumerate admin-gated endpoints.
    assert resp.json() == _EXPECTED_403_BODY


def _bearer(user_id) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


def _ensure_rbac_routes_registered(app_: FastAPI) -> None:
    """Add `GET /test/admin-only` + `/test/member-only` once per process.

    Mirrors `_ensure_protected_route_registered` in the
    `get_current_user` tests: the routes live on the production `app` so
    they reuse the `dependency_overrides` wired by `async_client`.
    """
    paths = {getattr(r, "path", None) for r in app_.routes}

    if "/test/admin-only" not in paths:

        async def _admin_only(
            user: Annotated[User, Depends(require_admin)],
        ) -> dict[str, str]:
            return {"id": str(user.id)}

        app_.add_api_route("/test/admin-only", _admin_only, methods=["GET"])

    if "/test/member-only" not in paths:

        async def _member_only(
            user: Annotated[User, Depends(require_member)],
        ) -> dict[str, str]:
            return {"id": str(user.id)}

        app_.add_api_route("/test/member-only", _member_only, methods=["GET"])


_ensure_rbac_routes_registered(app)


async def test_admin_only_allows_admin(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)

    resp = await async_client.get("/test/admin-only", headers=_bearer(admin.id))

    assert resp.status_code == 200
    assert resp.json() == {"id": str(admin.id)}


async def test_admin_only_forbids_member(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
) -> None:
    member = await bound_user_factory(email="member@example.com", role=UserRole.MEMBER)

    resp = await async_client.get("/test/admin-only", headers=_bearer(member.id))

    _assert_forbidden(resp)


async def test_admin_only_rejects_anonymous_with_401(
    async_client: AsyncClient,
) -> None:
    """No credentials → `get_current_user` 401s *before* the role check.

    Confirms the guard layers on top of authentication rather than
    masking the anonymous case as a 403.
    """
    resp = await async_client.get("/test/admin-only")

    assert resp.status_code == 401


async def test_admin_only_rejects_disabled_admin_with_401(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    """A disabled admin is a 401 (relayed by `get_current_user`), not 403.

    Disabling happens after the token is issued; `get_current_user`
    rejects the now-disabled user before `require_admin` ever sees a
    role, so the response is the uniform 401, not the RBAC 403.
    """
    admin = await bound_user_factory(email="disabled-admin@example.com", role=UserRole.ADMIN)
    headers = _bearer(admin.id)

    admin.disabled_at = datetime.now(tz=UTC)
    await auth_schema.flush()

    resp = await async_client.get("/test/admin-only", headers=headers)

    assert resp.status_code == 401


async def test_member_only_allows_admin(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
) -> None:
    """Admins are a superset of members — they pass the member gate too."""
    admin = await bound_user_factory(email="admin-as-member@example.com", role=UserRole.ADMIN)

    resp = await async_client.get("/test/member-only", headers=_bearer(admin.id))

    assert resp.status_code == 200


async def test_member_only_allows_member(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
) -> None:
    member = await bound_user_factory(email="plain-member@example.com", role=UserRole.MEMBER)

    resp = await async_client.get("/test/member-only", headers=_bearer(member.id))

    assert resp.status_code == 200


async def test_member_only_rejects_anonymous_with_401(
    async_client: AsyncClient,
) -> None:
    resp = await async_client.get("/test/member-only")

    assert resp.status_code == 401


async def test_member_only_is_fail_closed_for_unexpected_role(
    async_client: AsyncClient,
) -> None:
    """A role outside `{ADMIN, MEMBER}` is rejected, not silently allowed.

    `UserRole` has only two members today, so a third role cannot be
    persisted. We exercise the defensive branch directly by overriding
    `get_current_user` to yield a user whose `role` is outside the
    allow-list — pinning that `require_member` fails closed (403) rather
    than treating "unknown role" as member-equivalent. Without this the
    branch would be dead code: present, untested, unprotected.
    """
    bogus_user = SimpleNamespace(id=uuid4(), role="superadmin")
    app.dependency_overrides[get_current_user] = lambda: bogus_user
    try:
        resp = await async_client.get("/test/member-only")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    _assert_forbidden(resp)


async def test_rbac_rejection_log_omits_email_and_required_role(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The `rbac_rejected` log must not leak the email nor the required role.

    The constant 403 body already hides the required role from the
    client; this pins the *server-side* half of that discipline. Without
    it, a regression adding `email` (or the required role) to the log
    `extra` would pass every other test green — the leak only shows up
    here.
    """
    member = await bound_user_factory(email="leaky@example.com", role=UserRole.MEMBER)

    deps_logger = "backend.modules.auth.transports.dependencies"
    with caplog.at_level(logging.WARNING, logger=deps_logger):
        resp = await async_client.get("/test/admin-only", headers=_bearer(member.id))

    _assert_forbidden(resp)

    rejections = [
        r for r in caplog.records if r.name == deps_logger and r.msg == "rbac_rejected"
    ]
    assert len(rejections) == 1
    fields = rejections[0].__dict__  # `extra=` lands here as attributes
    # Carries the safe, ops-only fields...
    assert fields["reason"] == "role_not_admin"
    assert fields["user_id"] == str(member.id)
    assert "client_ip" in fields
    # ...and never the email nor a field naming the required role.
    assert "email" not in fields
    assert "role" not in fields
    assert "leaky@example.com" not in caplog.text
