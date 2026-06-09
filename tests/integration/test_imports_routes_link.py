"""Integration tests for `POST /imports/ofx/link-account` (S12.4, P12.4.2).

Drives the link route over httpx (`async_client`, savepoint mode — `link` is
flush-only and the route never commits, so the savepoint round-trip is enough to
read the mapping back through `/preview`). Covers: the accessibility gate (404
non-disclosure BEFORE `link`, admin NOT exempt, D8), the typed conflicts
(`AccountAlreadyLinkedError` → 409, `UnknownProviderError` → 422), and the
end-to-end effect (a linked ref no longer reports `account_not_linked`).

The "inaccessible → 404" body is byte-identical to a non-existent account (the
route never reveals another user's account exists). No internal account is ever
created by `/link-account` (the FK guarantees existence; the route only links).
Seeding goes through the shared `seed_personal_account`/`bound_user_factory`
fixtures and `_imports_helpers` (review S12.4).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from backend.modules.auth.domain import UserRole
from backend.modules.auth.models import User
from tests.integration._imports_helpers import BOURSO_REF, bearer, files

pytestmark = pytest.mark.usefixtures("household_singleton")

SeedAccount = Callable[..., Awaitable[tuple[UUID, UUID]]]
UserMaker = Callable[..., Awaitable[User]]


def _link_body(
    account_id: UUID, *, external_ref: str = BOURSO_REF, provider: str = "ofx"
) -> dict[str, str]:
    return {
        "external_ref": external_ref,
        "internal_account_id": str(account_id),
        "provider": provider,
    }


async def test_link_returns_created_mapping(
    async_client: AsyncClient, seed_personal_account: SeedAccount
) -> None:
    user_id, account_id = await seed_personal_account()

    resp = await async_client.post(
        "/imports/ofx/link-account", json=_link_body(account_id), headers=bearer(user_id)
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["external_ref"] == BOURSO_REF
    assert body["internal_account_id"] == str(account_id)
    assert body["provider"] == "ofx"
    assert UUID(body["id"])  # a real mapping id


async def test_link_then_preview_no_longer_account_not_linked(
    async_client: AsyncClient, seed_personal_account: SeedAccount
) -> None:
    user_id, account_id = await seed_personal_account()

    # Before linking, preview reports the ref as not linked.
    before = await async_client.post(
        "/imports/ofx/preview", files=files("boursorama_export_2026.ofx"), headers=bearer(user_id)
    )
    assert before.status_code == 422
    assert before.json()["detail"]["code"] == "account_not_linked"

    link_resp = await async_client.post(
        "/imports/ofx/link-account", json=_link_body(account_id), headers=bearer(user_id)
    )
    assert link_resp.status_code == 201, link_resp.text

    after = await async_client.post(
        "/imports/ofx/preview", files=files("boursorama_export_2026.ofx"), headers=bearer(user_id)
    )
    assert after.status_code == 200, after.text


async def test_double_link_conflict_409(
    async_client: AsyncClient, seed_personal_account: SeedAccount
) -> None:
    user_id, account_id = await seed_personal_account()

    first = await async_client.post(
        "/imports/ofx/link-account", json=_link_body(account_id), headers=bearer(user_id)
    )
    assert first.status_code == 201, first.text

    second = await async_client.post(
        "/imports/ofx/link-account", json=_link_body(account_id), headers=bearer(user_id)
    )
    assert second.status_code == 409, second.text
    assert second.json()["detail"]["code"] == "account_already_linked"


async def test_link_inaccessible_internal_account_404(
    async_client: AsyncClient,
    seed_personal_account: SeedAccount,
    bound_user_factory: UserMaker,
) -> None:
    # Account owned by ANOTHER user → 404 (non-disclosure, D8). No mapping created.
    _other_id, other_account = await seed_personal_account()
    caller = await bound_user_factory()

    resp = await async_client.post(
        "/imports/ofx/link-account", json=_link_body(other_account), headers=bearer(caller.id)
    )

    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"]["code"] == "account_not_found"


async def test_link_unknown_account_404(
    async_client: AsyncClient, bound_user_factory: UserMaker
) -> None:
    # A random non-existent account id is byte-identical to an inaccessible one.
    caller = await bound_user_factory()
    resp = await async_client.post(
        "/imports/ofx/link-account", json=_link_body(uuid4()), headers=bearer(caller.id)
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"]["code"] == "account_not_found"


async def test_link_admin_not_exempt_404(
    async_client: AsyncClient,
    seed_personal_account: SeedAccount,
    bound_user_factory: UserMaker,
) -> None:
    # F03: an admin linking another user's personal account is NOT exempt → 404.
    _member_id, member_account = await seed_personal_account()
    admin = await bound_user_factory(role=UserRole.ADMIN)

    resp = await async_client.post(
        "/imports/ofx/link-account", json=_link_body(member_account), headers=bearer(admin.id)
    )

    assert resp.status_code == 404, resp.text


async def test_link_unknown_provider_422(
    async_client: AsyncClient, seed_personal_account: SeedAccount
) -> None:
    user_id, account_id = await seed_personal_account()

    resp = await async_client.post(
        "/imports/ofx/link-account",
        json=_link_body(account_id, provider="sftp"),
        headers=bearer(user_id),
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "unknown_provider"


async def test_link_anonymous_401(async_client: AsyncClient) -> None:
    resp = await async_client.post("/imports/ofx/link-account", json=_link_body(uuid4()))
    assert resp.status_code == 401, resp.text
