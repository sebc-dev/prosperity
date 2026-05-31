"""Integration tests for `GET /accounts` — watertight listing (S05.3, P05.3.2).

Drives the filtered list over httpx: a caller sees only their owned personal
accounts ∪ the shared accounts they are a member of, archived excluded. The
load-bearing assertion (F03/D2) is that the **admin is not exempt** — it never
sees another user's personal account through this route.

Accounts are seeded directly via the bound factories (no `POST` round-trip):
the route under test is the read path, so the writes are set up out-of-band.
`household_singleton` provides the FK target row for `accounts.household_id`;
the GET path never calls `get_household`, so no cache bracketing is needed.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.modules.auth.domain import UserRole
from backend.modules.auth.service.jwt import issue_access_token

_settings = get_settings()

FactoryBundle = Callable[[], Awaitable[tuple[type, type, type]]]


def _bearer(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


def _ids(payload: list[dict[str, object]]) -> set[str]:
    return {row["id"] for row in payload}  # type: ignore[misc]


async def test_list_returns_only_owned_personal(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        a = user_factory(email="a@example.com")
        b = user_factory(email="b@example.com")
        a_acc = account_factory(owner_id=a.id, name="A's account")
        account_factory(owner_id=b.id, name="B's account")
        return a.id, a_acc.id

    a_id, a_acc_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get("/accounts", headers=_bearer(a_id))
    assert resp.status_code == 200, resp.text
    assert _ids(resp.json()) == {str(a_acc_id)}


async def test_list_admin_not_exempt_from_personal(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # F03 (D2): an admin calling GET /accounts must NOT see another user's
    # personal account. Watertightness is by filter, not exempted by role.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> UUID:
        admin = user_factory(email="admin@example.com", role=UserRole.ADMIN)
        member = user_factory(email="member@example.com")
        account_factory(owner_id=member.id, name="Member personal")
        return admin.id

    admin_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get("/accounts", headers=_bearer(admin_id))
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test_list_includes_shared_where_member(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        u1 = user_factory(email="u1@example.com")
        u2 = user_factory(email="u2@example.com")
        shared = account_factory(owner_id=None, name="Commun")
        member_factory(account_id=shared.id, user_id=u1.id)
        member_factory(account_id=shared.id, user_id=u2.id)
        return u1.id, shared.id

    u1_id, shared_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get("/accounts", headers=_bearer(u1_id))
    assert resp.status_code == 200, resp.text
    assert _ids(resp.json()) == {str(shared_id)}


async def test_list_excludes_shared_where_not_member(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(_s: Session) -> UUID:
        u1 = user_factory(email="in1@example.com")
        u2 = user_factory(email="in2@example.com")
        outsider = user_factory(email="out@example.com")
        shared = account_factory(owner_id=None, name="Commun")
        member_factory(account_id=shared.id, user_id=u1.id)
        member_factory(account_id=shared.id, user_id=u2.id)
        return outsider.id

    outsider_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get("/accounts", headers=_bearer(outsider_id))
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test_list_excludes_archived(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="arch@example.com")
        live = account_factory(owner_id=owner.id, name="Live")
        account_factory(owner_id=owner.id, name="Archived", archived_at=datetime.now(tz=UTC))
        return owner.id, live.id

    owner_id, live_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get("/accounts", headers=_bearer(owner_id))
    assert resp.status_code == 200, resp.text
    assert _ids(resp.json()) == {str(live_id)}


async def test_list_empty_for_new_user(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, _, _ = await bound_account_factories()

    def _seed(_s: Session) -> UUID:
        return user_factory(email="newbie@example.com").id

    user_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get("/accounts", headers=_bearer(user_id))
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test_list_ordering_recent_first(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()
    now = datetime.now(tz=UTC)

    def _seed(_s: Session) -> tuple[UUID, UUID, UUID]:
        owner = user_factory(email="order@example.com")
        older = account_factory(
            owner_id=owner.id, name="Older", created_at=now - timedelta(hours=1)
        )
        newer = account_factory(owner_id=owner.id, name="Newer", created_at=now)
        return owner.id, newer.id, older.id

    owner_id, newer_id, older_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get("/accounts", headers=_bearer(owner_id))
    assert resp.status_code == 200, resp.text
    ordered = [row["id"] for row in resp.json()]
    assert ordered == [str(newer_id), str(older_id)]


async def test_list_401_anonymous(async_client: AsyncClient) -> None:
    resp = await async_client.get("/accounts")
    assert resp.status_code == 401
