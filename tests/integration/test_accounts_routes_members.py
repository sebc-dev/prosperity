"""Integration tests for the member-management routes (S05.4, P05.4.2).

Drives `POST /accounts/{id}/members`, `PATCH /accounts/{id}/members/{user_id}`
and `DELETE /accounts/{id}/members/{user_id}` over httpx against a real Postgres.
The invariants under test:

- authorisation is **membership** (any current member, admin not exempt); a
  non-member — admin included — is a uniform 404 (D5 non-disclosure);
- 🔒 the membership check runs **before** roster validation: a non-member with an
  invalid roster gets 404, never 422 (no existence oracle);
- the roster is a **total re-balance** validated by `AccountValidator`: Σ=1, ≥ 2
  members, no duplicate, every ratio > 0 (→ 422), and the roster shape must match
  the verb (POST adds exactly one, PATCH keeps membership, DELETE drops exactly
  the target) — else 422;
- removing the second-to-last member is refused (a shared account keeps ≥ 2);
- an unknown member `user_id` on POST → 422 via FK 23503, nothing persisted;
- 401 for anonymous callers.

Accounts/members are seeded via the bound factories; the routes never call
`get_household`, so no household-cache bracketing is needed.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.modules.accounts.models import AccountMember
from backend.modules.auth.domain import UserRole
from backend.modules.auth.service.jwt import issue_access_token

_settings = get_settings()

FactoryBundle = Callable[[], Awaitable[tuple[type, type, type]]]


def _bearer(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


def _ratios(body: dict[str, object]) -> dict[str, Decimal]:
    """Map user_id → Decimal(default_share_ratio) from a detail-response body."""
    members = body["members"]  # type: ignore[index]
    return {m["user_id"]: Decimal(str(m["default_share_ratio"])) for m in members}  # type: ignore[index,union-attr]


async def _seed_world(
    household_singleton: AsyncSession, factories: FactoryBundle
) -> dict[str, UUID]:
    """A 2-member shared account (m1/m2, 0.5/0.5) + spare users.

    Returns a dict of named ids: `account`, `m1`, `m2` (members), `m3` (a real
    user, not yet a member), `outsider` (non-member), `admin` (non-member admin),
    and `personal` (a personal account owned by `m1`).
    """
    user_factory, account_factory, member_factory = await factories()

    def _seed(_s: Session) -> dict[str, UUID]:
        m1 = user_factory(email="m1@example.com")
        m2 = user_factory(email="m2@example.com")
        m3 = user_factory(email="m3@example.com")
        outsider = user_factory(email="outsider@example.com")
        admin = user_factory(email="admin@example.com", role=UserRole.ADMIN)
        shared = account_factory(owner_id=None, name="Commun")
        member_factory(account_id=shared.id, user_id=m1.id, default_share_ratio=Decimal("0.5000"))
        member_factory(account_id=shared.id, user_id=m2.id, default_share_ratio=Decimal("0.5000"))
        personal = account_factory(owner_id=m1.id, name="Perso")
        return {
            "account": shared.id,
            "m1": m1.id,
            "m2": m2.id,
            "m3": m3.id,
            "outsider": outsider.id,
            "admin": admin.id,
            "personal": personal.id,
        }

    return await household_singleton.run_sync(_seed)


async def _member_count(session: AsyncSession, account_id: UUID) -> int:
    rows = (
        (
            await session.execute(
                select(AccountMember)
                .where(AccountMember.account_id == account_id)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    return len(rows)


def _roster(*pairs: tuple[UUID, str]) -> dict[str, object]:
    return {"members": [{"user_id": str(uid), "default_share_ratio": r} for uid, r in pairs]}


# ---------------------------------------------------------------------------
# POST /accounts/{id}/members
# ---------------------------------------------------------------------------


async def test_post_member_201_by_current_member(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    ids = await _seed_world(household_singleton, bound_account_factories)

    resp = await async_client.post(
        f"/accounts/{ids['account']}/members",
        json=_roster((ids["m1"], "0.33"), (ids["m2"], "0.33"), (ids["m3"], "0.34")),
        headers=_bearer(ids["m1"]),
    )

    assert resp.status_code == 201, resp.text
    ratios = _ratios(resp.json())
    assert set(ratios) == {str(ids["m1"]), str(ids["m2"]), str(ids["m3"])}
    assert sum(ratios.values()) == Decimal("1.00")
    assert await _member_count(household_singleton, ids["account"]) == 3


async def test_post_member_404_for_non_member(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    ids = await _seed_world(household_singleton, bound_account_factories)

    resp = await async_client.post(
        f"/accounts/{ids['account']}/members",
        json=_roster((ids["m1"], "0.33"), (ids["m2"], "0.33"), (ids["m3"], "0.34")),
        headers=_bearer(ids["outsider"]),
    )
    assert resp.status_code == 404
    assert await _member_count(household_singleton, ids["account"]) == 2


async def test_post_member_404_for_admin_non_member(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # The admin is NOT exempt: not a member → 404 (D5).
    ids = await _seed_world(household_singleton, bound_account_factories)

    resp = await async_client.post(
        f"/accounts/{ids['account']}/members",
        json=_roster((ids["m1"], "0.33"), (ids["m2"], "0.33"), (ids["m3"], "0.34")),
        headers=_bearer(ids["admin"]),
    )
    assert resp.status_code == 404


async def test_post_member_404_non_member_with_invalid_roster(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # 🔒 Non-disclosure: a non-member sending a Σ≠1 roster gets 404, NOT 422.
    ids = await _seed_world(household_singleton, bound_account_factories)

    resp = await async_client.post(
        f"/accounts/{ids['account']}/members",
        json=_roster((ids["m1"], "0.5"), (ids["m2"], "0.4"), (ids["m3"], "0.4")),
        headers=_bearer(ids["outsider"]),
    )
    assert resp.status_code == 404


async def test_post_member_422_sum_not_one(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    ids = await _seed_world(household_singleton, bound_account_factories)

    resp = await async_client.post(
        f"/accounts/{ids['account']}/members",
        json=_roster((ids["m1"], "0.5"), (ids["m2"], "0.4"), (ids["m3"], "0.4")),
        headers=_bearer(ids["m1"]),
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "Member share ratios must sum to 1."
    assert await _member_count(household_singleton, ids["account"]) == 2


async def test_post_member_422_adds_none(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # A roster that adds no new member (just re-balances the current two) is not
    # a valid POST — exactly one addition is required.
    ids = await _seed_world(household_singleton, bound_account_factories)

    resp = await async_client.post(
        f"/accounts/{ids['account']}/members",
        json=_roster((ids["m1"], "0.7"), (ids["m2"], "0.3")),
        headers=_bearer(ids["m1"]),
    )
    assert resp.status_code == 422
    assert await _member_count(household_singleton, ids["account"]) == 2


async def test_post_member_422_removes_existing(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # POST is not a removal channel: a roster that drops a current member (m2)
    # while adding m3 is rejected.
    ids = await _seed_world(household_singleton, bound_account_factories)

    resp = await async_client.post(
        f"/accounts/{ids['account']}/members",
        json=_roster((ids["m1"], "0.5"), (ids["m3"], "0.5")),
        headers=_bearer(ids["m1"]),
    )
    assert resp.status_code == 422
    assert await _member_count(household_singleton, ids["account"]) == 2


async def test_post_member_422_unknown_user(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # A user_id with no users row trips the FK (23503) → 422, nothing persisted.
    ids = await _seed_world(household_singleton, bound_account_factories)

    resp = await async_client.post(
        f"/accounts/{ids['account']}/members",
        json=_roster((ids["m1"], "0.33"), (ids["m2"], "0.33"), (uuid4(), "0.34")),
        headers=_bearer(ids["m1"]),
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "A referenced member does not exist."
    assert await _member_count(household_singleton, ids["account"]) == 2


async def test_post_member_404_on_personal_account(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # A personal account has no roster; its owner is not a `account_members` row.
    ids = await _seed_world(household_singleton, bound_account_factories)

    resp = await async_client.post(
        f"/accounts/{ids['personal']}/members",
        json=_roster((ids["m1"], "0.5"), (ids["m3"], "0.5")),
        headers=_bearer(ids["m1"]),
    )
    assert resp.status_code == 404


async def test_post_member_404_on_unknown_account(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    ids = await _seed_world(household_singleton, bound_account_factories)

    resp = await async_client.post(
        f"/accounts/{uuid4()}/members",
        json=_roster((ids["m1"], "0.5"), (ids["m3"], "0.5")),
        headers=_bearer(ids["m1"]),
    )
    assert resp.status_code == 404


async def test_post_member_401_anonymous(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    ids = await _seed_world(household_singleton, bound_account_factories)
    resp = await async_client.post(
        f"/accounts/{ids['account']}/members",
        json=_roster((ids["m1"], "0.33"), (ids["m2"], "0.33"), (ids["m3"], "0.34")),
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /accounts/{id}/members/{user_id}
# ---------------------------------------------------------------------------


async def test_patch_member_200_rebalances(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    ids = await _seed_world(household_singleton, bound_account_factories)

    resp = await async_client.patch(
        f"/accounts/{ids['account']}/members/{ids['m1']}",
        json=_roster((ids["m1"], "0.7"), (ids["m2"], "0.3")),
        headers=_bearer(ids["m2"]),
    )
    assert resp.status_code == 200, resp.text
    ratios = _ratios(resp.json())
    assert ratios[str(ids["m1"])] == Decimal("0.7")
    assert ratios[str(ids["m2"])] == Decimal("0.3")
    assert sum(ratios.values()) == Decimal("1.0")


async def test_patch_member_422_sum_not_one(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    ids = await _seed_world(household_singleton, bound_account_factories)

    resp = await async_client.patch(
        f"/accounts/{ids['account']}/members/{ids['m1']}",
        json=_roster((ids["m1"], "0.7"), (ids["m2"], "0.4")),
        headers=_bearer(ids["m1"]),
    )
    assert resp.status_code == 422


async def test_patch_member_422_changes_membership(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # PATCH must not add/remove members (that's POST/DELETE).
    ids = await _seed_world(household_singleton, bound_account_factories)

    resp = await async_client.patch(
        f"/accounts/{ids['account']}/members/{ids['m1']}",
        json=_roster((ids["m1"], "0.5"), (ids["m3"], "0.5")),
        headers=_bearer(ids["m1"]),
    )
    assert resp.status_code == 422


async def test_patch_member_404_target_not_member(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    ids = await _seed_world(household_singleton, bound_account_factories)

    resp = await async_client.patch(
        f"/accounts/{ids['account']}/members/{ids['m3']}",
        json=_roster((ids["m1"], "0.5"), (ids["m2"], "0.5")),
        headers=_bearer(ids["m1"]),
    )
    assert resp.status_code == 404


async def test_patch_member_404_by_non_member(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    ids = await _seed_world(household_singleton, bound_account_factories)

    resp = await async_client.patch(
        f"/accounts/{ids['account']}/members/{ids['m1']}",
        json=_roster((ids["m1"], "0.7"), (ids["m2"], "0.3")),
        headers=_bearer(ids["outsider"]),
    )
    assert resp.status_code == 404


async def test_patch_member_404_non_member_with_invalid_roster(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # 🔒 Non-member + Σ≠1 roster → 404, not 422.
    ids = await _seed_world(household_singleton, bound_account_factories)

    resp = await async_client.patch(
        f"/accounts/{ids['account']}/members/{ids['m1']}",
        json=_roster((ids["m1"], "0.7"), (ids["m2"], "0.4")),
        headers=_bearer(ids["outsider"]),
    )
    assert resp.status_code == 404


async def test_patch_member_404_target_not_member_invalid_roster(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # 🔒 Target-not-member is checked before validation → 404, not 422.
    ids = await _seed_world(household_singleton, bound_account_factories)

    resp = await async_client.patch(
        f"/accounts/{ids['account']}/members/{ids['m3']}",
        json=_roster((ids["m1"], "0.7"), (ids["m2"], "0.4")),
        headers=_bearer(ids["m1"]),
    )
    assert resp.status_code == 404


async def test_patch_member_401_anonymous(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    ids = await _seed_world(household_singleton, bound_account_factories)
    resp = await async_client.patch(
        f"/accounts/{ids['account']}/members/{ids['m1']}",
        json=_roster((ids["m1"], "0.7"), (ids["m2"], "0.3")),
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /accounts/{id}/members/{user_id}
# ---------------------------------------------------------------------------


async def test_delete_member_204_from_three(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    ids = await _seed_world(household_singleton, bound_account_factories)
    # Grow to 3 first so a removal leaves a legal ≥ 2.
    assert (
        await async_client.post(
            f"/accounts/{ids['account']}/members",
            json=_roster((ids["m1"], "0.33"), (ids["m2"], "0.33"), (ids["m3"], "0.34")),
            headers=_bearer(ids["m1"]),
        )
    ).status_code == 201

    resp = await async_client.request(
        "DELETE",
        f"/accounts/{ids['account']}/members/{ids['m3']}",
        json=_roster((ids["m1"], "0.5"), (ids["m2"], "0.5")),
        headers=_bearer(ids["m1"]),
    )
    assert resp.status_code == 204, resp.text
    assert await _member_count(household_singleton, ids["account"]) == 2


async def test_delete_member_422_second_to_last(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # Removing from a 2-member account would leave 1 → refused (≥ 2 invariant).
    ids = await _seed_world(household_singleton, bound_account_factories)

    # The survivor roster has a single member: `AccountMemberInput` caps ratio at
    # `lt=1`, so a one-member roster cannot carry 1.0 — we send an in-bounds 0.5
    # and rely on the domain floor (`validate_member_set` → TooFewMembersError)
    # to reject the < 2 cardinality, before any write.
    resp = await async_client.request(
        "DELETE",
        f"/accounts/{ids['account']}/members/{ids['m2']}",
        json=_roster((ids["m1"], "0.5")),
        headers=_bearer(ids["m1"]),
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "A shared account needs at least two members."
    assert await _member_count(household_singleton, ids["account"]) == 2


async def test_delete_member_422_incoherent_roster(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # 🔒 DELETE is not an arbitrary membership-edit channel: a roster that does
    # not equal `current \ {target}` (here it keeps m3 instead of dropping it,
    # while also re-adding nobody coherent) is a 422.
    ids = await _seed_world(household_singleton, bound_account_factories)
    assert (
        await async_client.post(
            f"/accounts/{ids['account']}/members",
            json=_roster((ids["m1"], "0.33"), (ids["m2"], "0.33"), (ids["m3"], "0.34")),
            headers=_bearer(ids["m1"]),
        )
    ).status_code == 201

    # Asked to delete m3 but the roster still lists m3 (does not drop the target).
    resp = await async_client.request(
        "DELETE",
        f"/accounts/{ids['account']}/members/{ids['m3']}",
        json=_roster((ids["m1"], "0.33"), (ids["m2"], "0.33"), (ids["m3"], "0.34")),
        headers=_bearer(ids["m1"]),
    )
    assert resp.status_code == 422
    assert await _member_count(household_singleton, ids["account"]) == 3


async def test_delete_member_404_target_not_member(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    ids = await _seed_world(household_singleton, bound_account_factories)

    resp = await async_client.request(
        "DELETE",
        f"/accounts/{ids['account']}/members/{ids['m3']}",
        json=_roster((ids["m1"], "0.5"), (ids["m2"], "0.5")),
        headers=_bearer(ids["m1"]),
    )
    assert resp.status_code == 404


async def test_delete_member_404_by_non_member(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    ids = await _seed_world(household_singleton, bound_account_factories)

    # Structurally valid body (each ratio in (0,1)) so it reaches the handler:
    # the membership check then returns 404. Pydantic's structural 422 is not an
    # existence oracle (D5), but here the body is well-formed, so the 404 is the
    # membership verdict, not a schema rejection.
    resp = await async_client.request(
        "DELETE",
        f"/accounts/{ids['account']}/members/{ids['m2']}",
        json=_roster((ids["m1"], "0.5"), (ids["m2"], "0.5")),
        headers=_bearer(ids["outsider"]),
    )
    assert resp.status_code == 404


async def test_delete_member_404_non_member_with_invalid_roster(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # 🔒 Non-member + invalid roster → 404, not 422.
    ids = await _seed_world(household_singleton, bound_account_factories)

    resp = await async_client.request(
        "DELETE",
        f"/accounts/{ids['account']}/members/{ids['m2']}",
        json=_roster((ids["m1"], "0.5"), (ids["m2"], "0.9")),
        headers=_bearer(ids["outsider"]),
    )
    assert resp.status_code == 404


async def test_delete_member_401_anonymous(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    ids = await _seed_world(household_singleton, bound_account_factories)
    resp = await async_client.request(
        "DELETE",
        f"/accounts/{ids['account']}/members/{ids['m2']}",
        json=_roster((ids["m1"], "1.0")),
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /accounts/{id} now exposes the roster (S05.4 / dette D9)
# ---------------------------------------------------------------------------


async def test_get_detail_exposes_members(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    ids = await _seed_world(household_singleton, bound_account_factories)

    resp = await async_client.get(f"/accounts/{ids['account']}", headers=_bearer(ids["m1"]))
    assert resp.status_code == 200, resp.text
    ratios = _ratios(resp.json())
    assert set(ratios) == {str(ids["m1"]), str(ids["m2"])}
    assert sum(ratios.values()) == Decimal("1.0")


async def test_get_detail_personal_has_empty_members(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    ids = await _seed_world(household_singleton, bound_account_factories)

    resp = await async_client.get(f"/accounts/{ids['personal']}", headers=_bearer(ids["m1"]))
    assert resp.status_code == 200, resp.text
    assert resp.json()["members"] == []
