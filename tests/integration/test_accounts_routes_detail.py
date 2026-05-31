"""Integration tests for `GET/PATCH/DELETE /accounts/{id}` (S05.3, P05.3.3).

Drives the per-account routes over httpx. The invariants under test:

- `GET /{id}` is a uniform **404** (never 403) for an inaccessible / archived
  / unknown account — admin included (D4 non-disclosure);
- `PATCH /{id}` edits `name` only; `currency`/`type` in the body are a 422
  (`extra="forbid"`, D6); an empty name is a 422 (C-TEST-3);
- `DELETE /{id}` is a soft delete (sets `archived_at`, never a hard delete):
  the row stays, drops out of the accessible reads, and a second delete is a
  404 (D7).

Accounts are seeded via the bound factories; the GET/PATCH/DELETE paths never
call `get_household`, so no household cache bracketing is needed (the FK target
comes from `household_singleton`). A malformed-UUID path param is a FastAPI 422
(C-TEST-2), distinct from the service-level 404.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.modules.accounts.models import Account
from backend.modules.auth.domain import UserRole
from backend.modules.auth.service.jwt import issue_access_token

_settings = get_settings()

FactoryBundle = Callable[[], Awaitable[tuple[type, type, type]]]


def _bearer(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


async def _fetch_account(session: AsyncSession, account_id: UUID) -> Account:
    """Read an account fresh from the DB (`populate_existing` bypasses stale copy)."""
    return (
        await session.execute(
            select(Account)
            .where(Account.id == account_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


# ---------------------------------------------------------------------------
# GET /accounts/{id}
# ---------------------------------------------------------------------------


async def test_get_by_id_owner_200(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="owner@example.com")
        acc = account_factory(owner_id=owner.id, name="Mine")
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get(f"/accounts/{acc_id}", headers=_bearer(owner_id))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(acc_id)
    # S05.4: GET /{id} now returns the detail view; a personal account has no
    # members.
    assert body["members"] == []


async def test_get_by_id_member_200(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, member_factory = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        u1 = user_factory(email="mem1@example.com")
        u2 = user_factory(email="mem2@example.com")
        shared = account_factory(owner_id=None, name="Commun")
        member_factory(account_id=shared.id, user_id=u1.id)
        member_factory(account_id=shared.id, user_id=u2.id)
        return u1.id, shared.id

    u1_id, shared_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get(f"/accounts/{shared_id}", headers=_bearer(u1_id))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(shared_id)
    # S05.4: the shared account's roster is exposed (the caller is one of the two
    # members) and sums to 1.
    members = body["members"]
    assert len(members) == 2
    assert str(u1_id) in {m["user_id"] for m in members}
    assert sum(Decimal(str(m["default_share_ratio"])) for m in members) == Decimal("1.0")


async def test_get_by_id_member_on_admin_personal_404(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # F03 direction (b), explicit integration cover (C-TEST-1): owner = admin,
    # caller = member → 404 (the member never sees the admin's personal acct).
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        admin = user_factory(email="admin@example.com", role=UserRole.ADMIN)
        member = user_factory(email="member@example.com")
        acc = account_factory(owner_id=admin.id, name="Admin perso")
        return member.id, acc.id

    member_id, acc_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get(f"/accounts/{acc_id}", headers=_bearer(member_id))
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Account not found."


async def test_get_by_id_admin_not_exempt_404(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # The reverse direction (D4/F03): an admin on a member's personal account
    # → 404. The admin is not exempt, and the 404 hides the account's existence.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        admin = user_factory(email="admin2@example.com", role=UserRole.ADMIN)
        member = user_factory(email="member2@example.com")
        acc = account_factory(owner_id=member.id, name="Member perso")
        return admin.id, acc.id

    admin_id, acc_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get(f"/accounts/{acc_id}", headers=_bearer(admin_id))
    assert resp.status_code == 404


async def test_get_by_id_archived_404(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="arch@example.com")
        acc = account_factory(owner_id=owner.id, name="Archived", archived_at=datetime.now(tz=UTC))
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get(f"/accounts/{acc_id}", headers=_bearer(owner_id))
    assert resp.status_code == 404


async def test_get_by_id_unknown_uuid_404(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, _, _ = await bound_account_factories()

    def _seed(_s: Session) -> UUID:
        return user_factory(email="ghost@example.com").id

    user_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get(f"/accounts/{uuid4()}", headers=_bearer(user_id))
    assert resp.status_code == 404


async def test_get_by_id_malformed_uuid_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # The `UUID` path param is validated by FastAPI before the handler runs →
    # 422 (C-TEST-2), distinct from the service-level 404.
    user_factory, _, _ = await bound_account_factories()

    def _seed(_s: Session) -> UUID:
        return user_factory(email="baduuid@example.com").id

    user_id = await household_singleton.run_sync(_seed)

    resp = await async_client.get("/accounts/not-a-uuid", headers=_bearer(user_id))
    assert resp.status_code == 422


async def test_get_by_id_401_anonymous(
    async_client: AsyncClient, household_singleton: AsyncSession
) -> None:
    resp = await async_client.get(f"/accounts/{uuid4()}")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /accounts/{id}
# ---------------------------------------------------------------------------


async def test_patch_renames_name_200(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="rename@example.com")
        acc = account_factory(owner_id=owner.id, name="Old", currency="EUR")
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    resp = await async_client.patch(
        f"/accounts/{acc_id}", json={"name": "New"}, headers=_bearer(owner_id)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "New"
    # `currency`/`type` untouched in the DB.
    persisted = await _fetch_account(household_singleton, acc_id)
    assert persisted.name == "New"
    assert persisted.currency == "EUR"


async def test_patch_rejects_currency_change_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="freeze@example.com")
        acc = account_factory(owner_id=owner.id, name="Freeze", currency="EUR")
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    resp = await async_client.patch(
        f"/accounts/{acc_id}",
        json={"name": "New", "currency": "USD"},
        headers=_bearer(owner_id),
    )
    assert resp.status_code == 422, resp.text
    # Unchanged in the DB (the whole request was rejected before any write).
    persisted = await _fetch_account(household_singleton, acc_id)
    assert persisted.name == "Freeze"
    assert persisted.currency == "EUR"


async def test_patch_rejects_type_change_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="type@example.com")
        acc = account_factory(owner_id=owner.id, name="Typed")
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    resp = await async_client.patch(
        f"/accounts/{acc_id}",
        json={"name": "New", "type": "livret"},
        headers=_bearer(owner_id),
    )
    assert resp.status_code == 422


async def test_patch_rejects_empty_name_422(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # `name` has `min_length=1`: an empty string is a 422 (C-TEST-3).
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="empty@example.com")
        acc = account_factory(owner_id=owner.id, name="NonEmpty")
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    resp = await async_client.patch(
        f"/accounts/{acc_id}", json={"name": ""}, headers=_bearer(owner_id)
    )
    assert resp.status_code == 422


async def test_patch_not_accessible_404(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # An admin on a member's personal account → 404, name unchanged.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        admin = user_factory(email="admin3@example.com", role=UserRole.ADMIN)
        member = user_factory(email="member3@example.com")
        acc = account_factory(owner_id=member.id, name="Untouchable")
        return admin.id, acc.id

    admin_id, acc_id = await household_singleton.run_sync(_seed)

    resp = await async_client.patch(
        f"/accounts/{acc_id}", json={"name": "Hacked"}, headers=_bearer(admin_id)
    )
    assert resp.status_code == 404
    persisted = await _fetch_account(household_singleton, acc_id)
    assert persisted.name == "Untouchable"


async def test_patch_archived_404(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="patcharch@example.com")
        acc = account_factory(owner_id=owner.id, name="Archived", archived_at=datetime.now(tz=UTC))
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    resp = await async_client.patch(
        f"/accounts/{acc_id}", json={"name": "New"}, headers=_bearer(owner_id)
    )
    assert resp.status_code == 404


async def test_patch_401_anonymous(
    async_client: AsyncClient, household_singleton: AsyncSession
) -> None:
    resp = await async_client.patch(f"/accounts/{uuid4()}", json={"name": "X"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /accounts/{id}
# ---------------------------------------------------------------------------


async def test_delete_archives_204(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="del@example.com")
        acc = account_factory(owner_id=owner.id, name="ToArchive")
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    resp = await async_client.delete(f"/accounts/{acc_id}", headers=_bearer(owner_id))
    assert resp.status_code == 204, resp.text
    # Row preserved, `archived_at` now set.
    persisted = await _fetch_account(household_singleton, acc_id)
    assert persisted.archived_at is not None


async def test_delete_then_absent_from_list(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="dellist@example.com")
        acc = account_factory(owner_id=owner.id, name="Vanishing")
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    assert (
        await async_client.delete(f"/accounts/{acc_id}", headers=_bearer(owner_id))
    ).status_code == 204
    listing = await async_client.get("/accounts", headers=_bearer(owner_id))
    assert listing.status_code == 200
    assert listing.json() == []


async def test_delete_then_get_by_id_404(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="delget@example.com")
        acc = account_factory(owner_id=owner.id, name="Gone")
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    assert (
        await async_client.delete(f"/accounts/{acc_id}", headers=_bearer(owner_id))
    ).status_code == 204
    assert (
        await async_client.get(f"/accounts/{acc_id}", headers=_bearer(owner_id))
    ).status_code == 404


async def test_delete_already_archived_404(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # A second delete finds nothing accessible → 404 (D7): `_accessible`
    # already excludes archived rows, so there is no 204-replay oracle.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="twice@example.com")
        acc = account_factory(owner_id=owner.id, name="Twice")
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    assert (
        await async_client.delete(f"/accounts/{acc_id}", headers=_bearer(owner_id))
    ).status_code == 204
    assert (
        await async_client.delete(f"/accounts/{acc_id}", headers=_bearer(owner_id))
    ).status_code == 404


async def test_delete_not_accessible_404(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # An admin on a member's personal account → 404, nothing archived.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        admin = user_factory(email="admin4@example.com", role=UserRole.ADMIN)
        member = user_factory(email="member4@example.com")
        acc = account_factory(owner_id=member.id, name="Safe")
        return admin.id, acc.id

    admin_id, acc_id = await household_singleton.run_sync(_seed)

    resp = await async_client.delete(f"/accounts/{acc_id}", headers=_bearer(admin_id))
    assert resp.status_code == 404
    persisted = await _fetch_account(household_singleton, acc_id)
    assert persisted.archived_at is None


async def test_delete_no_hard_delete(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # Archive is not a hard delete: the row count is unchanged before/after.
    user_factory, account_factory, _ = await bound_account_factories()

    def _seed(_s: Session) -> tuple[UUID, UUID]:
        owner = user_factory(email="count@example.com")
        acc = account_factory(owner_id=owner.id, name="Counted")
        return owner.id, acc.id

    owner_id, acc_id = await household_singleton.run_sync(_seed)

    before = (
        await household_singleton.execute(select(func.count()).select_from(Account))
    ).scalar_one()
    assert (
        await async_client.delete(f"/accounts/{acc_id}", headers=_bearer(owner_id))
    ).status_code == 204
    after = (
        await household_singleton.execute(
            select(func.count()).select_from(Account).execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert before == after == 1


async def test_delete_401_anonymous(
    async_client: AsyncClient, household_singleton: AsyncSession
) -> None:
    resp = await async_client.delete(f"/accounts/{uuid4()}")
    assert resp.status_code == 401
