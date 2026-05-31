"""Integration tests for the DomainEvents emitted by member mutations (P05.4.3).

A spy subscriber registered on the in-process mini-bus proves that each member
mutation publishes the right event, with the right payload, **inside the request
transaction** (the synchronous `publish` runs before `get_db` releases the
savepoint, so the spy captures the event during request handling).

What this pins:
- POST → `AccountMemberAdded(account_id, user_id=newcomer, share_ratio)`;
- PATCH → `ShareRatioUpdated(account_id, user_id, old_ratio, new_ratio)` (exact
  Decimals);
- DELETE → `AccountMemberRemoved(account_id, user_id=removed)`;
- a rejected mutation (422 / 404) publishes **nothing** (publish is after the
  validation + flush, and never reached on a 404);
- dispatch is by exact type (an `AccountMemberAdded` subscriber is silent on a
  DELETE/PATCH).

Note (transaction nuance): this proves *publish-before-request-commit ordering*
and the flushed payload — not the atomicity of a subscriber side effect (there
is no subscriber in V1; that is out of scope, deferred to E08). The bus is
process-global mutable state, so an autouse fixture clears it around each test.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from decimal import Decimal
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.modules.accounts.events import (
    AccountMemberAdded,
    AccountMemberRemoved,
    ShareRatioUpdated,
)
from backend.modules.auth.service.jwt import issue_access_token
from backend.shared.events import DomainEvent, clear_subscribers, subscribe

_settings = get_settings()

FactoryBundle = Callable[[], Awaitable[tuple[type, type, type]]]


@pytest.fixture(autouse=True)
def _reset_event_bus() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Cold bus around every test (the registry is process-global)."""
    clear_subscribers()
    yield
    clear_subscribers()


def _bearer(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


def _roster(*pairs: tuple[UUID, str]) -> dict[str, object]:
    return {"members": [{"user_id": str(uid), "default_share_ratio": r} for uid, r in pairs]}


async def _seed(household_singleton: AsyncSession, factories: FactoryBundle) -> dict[str, UUID]:
    """A 2-member shared account (m1/m2, 0.5/0.5) + a spare real user m3."""
    user_factory, account_factory, member_factory = await factories()

    def _do(_s: Session) -> dict[str, UUID]:
        m1 = user_factory(email="ev1@example.com")
        m2 = user_factory(email="ev2@example.com")
        m3 = user_factory(email="ev3@example.com")
        shared = account_factory(owner_id=None, name="Commun")
        member_factory(account_id=shared.id, user_id=m1.id, default_share_ratio=Decimal("0.5000"))
        member_factory(account_id=shared.id, user_id=m2.id, default_share_ratio=Decimal("0.5000"))
        return {"account": shared.id, "m1": m1.id, "m2": m2.id, "m3": m3.id}

    return await household_singleton.run_sync(_do)


async def test_post_publishes_member_added(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    ids = await _seed(household_singleton, bound_account_factories)
    captured: list[AccountMemberAdded] = []
    subscribe(AccountMemberAdded, captured.append)

    resp = await async_client.post(
        f"/accounts/{ids['account']}/members",
        json=_roster((ids["m1"], "0.33"), (ids["m2"], "0.33"), (ids["m3"], "0.34")),
        headers=_bearer(ids["m1"]),
    )
    assert resp.status_code == 201, resp.text

    assert len(captured) == 1
    evt = captured[0]
    assert evt.account_id == ids["account"]
    assert evt.user_id == ids["m3"]
    assert evt.share_ratio == Decimal("0.34")


async def test_patch_publishes_share_ratio_updated(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    ids = await _seed(household_singleton, bound_account_factories)
    captured: list[ShareRatioUpdated] = []
    subscribe(ShareRatioUpdated, captured.append)

    resp = await async_client.patch(
        f"/accounts/{ids['account']}/members/{ids['m1']}",
        json=_roster((ids["m1"], "0.7"), (ids["m2"], "0.3")),
        headers=_bearer(ids["m1"]),
    )
    assert resp.status_code == 200, resp.text

    assert len(captured) == 1
    evt = captured[0]
    assert evt.account_id == ids["account"]
    assert evt.user_id == ids["m1"]
    assert evt.old_ratio == Decimal("0.5000")
    assert evt.new_ratio == Decimal("0.7")


async def test_delete_publishes_member_removed(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    ids = await _seed(household_singleton, bound_account_factories)
    # Grow to 3 so a removal leaves a legal >= 2.
    assert (
        await async_client.post(
            f"/accounts/{ids['account']}/members",
            json=_roster((ids["m1"], "0.33"), (ids["m2"], "0.33"), (ids["m3"], "0.34")),
            headers=_bearer(ids["m1"]),
        )
    ).status_code == 201

    captured: list[AccountMemberRemoved] = []
    subscribe(AccountMemberRemoved, captured.append)

    resp = await async_client.request(
        "DELETE",
        f"/accounts/{ids['account']}/members/{ids['m3']}",
        json=_roster((ids["m1"], "0.5"), (ids["m2"], "0.5")),
        headers=_bearer(ids["m1"]),
    )
    assert resp.status_code == 204, resp.text

    assert len(captured) == 1
    evt = captured[0]
    assert evt.account_id == ids["account"]
    assert evt.user_id == ids["m3"]


async def test_rejected_mutation_publishes_nothing(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    ids = await _seed(household_singleton, bound_account_factories)
    captured: list[DomainEvent] = []
    for event_type in (AccountMemberAdded, AccountMemberRemoved, ShareRatioUpdated):
        subscribe(event_type, captured.append)

    # 422: Σ ≠ 1.
    bad = await async_client.post(
        f"/accounts/{ids['account']}/members",
        json=_roster((ids["m1"], "0.5"), (ids["m2"], "0.4"), (ids["m3"], "0.4")),
        headers=_bearer(ids["m1"]),
    )
    assert bad.status_code == 422
    # 404: a non-member (here m3, not a member) cannot mutate.
    forbidden = await async_client.post(
        f"/accounts/{ids['account']}/members",
        json=_roster((ids["m1"], "0.33"), (ids["m2"], "0.33"), (ids["m3"], "0.34")),
        headers=_bearer(ids["m3"]),
    )
    assert forbidden.status_code == 404

    assert captured == []


async def test_dispatch_is_by_exact_type(
    async_client: AsyncClient,
    household_singleton: AsyncSession,
    bound_account_factories: FactoryBundle,
) -> None:
    # A subscriber to AccountMemberAdded must not fire on a PATCH (ShareRatioUpdated).
    ids = await _seed(household_singleton, bound_account_factories)
    added: list[AccountMemberAdded] = []
    subscribe(AccountMemberAdded, added.append)

    resp = await async_client.patch(
        f"/accounts/{ids['account']}/members/{ids['m1']}",
        json=_roster((ids["m1"], "0.7"), (ids["m2"], "0.3")),
        headers=_bearer(ids["m1"]),
    )
    assert resp.status_code == 200

    assert added == []
