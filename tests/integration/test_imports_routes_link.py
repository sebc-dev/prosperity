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
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.modules.accounts.domain import AccountType
from backend.modules.accounts.models import Account
from backend.modules.auth.models import User, UserRole
from backend.modules.auth.service.jwt import issue_access_token

_settings = get_settings()
_OFX_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ofx"
_BOURSO_REF = "BOURSO-0000-1111"  # boursorama_export_2026.ofx

pytestmark = pytest.mark.usefixtures("household_singleton")


def _bearer(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


def _files(name: str) -> dict[str, tuple[str, bytes, str]]:
    return {"file": (name, (_OFX_DIR / name).read_bytes(), "application/octet-stream")}


async def _make_user(session: AsyncSession, *, role: UserRole = UserRole.MEMBER) -> UUID:
    user = User(
        email=f"{uuid4().hex}@example.com",
        password_hash="x" * 60,
        display_name="importer",
        role=role,
    )
    session.add(user)
    await session.flush()
    return user.id


async def _make_account(session: AsyncSession, owner_id: UUID) -> UUID:
    account = Account(name="Courant", type=AccountType.COURANT, currency="EUR", owner_id=owner_id)
    session.add(account)
    await session.flush()
    return account.id


def _link_body(account_id: UUID, *, external_ref: str = _BOURSO_REF, provider: str = "ofx") -> dict:
    return {
        "external_ref": external_ref,
        "internal_account_id": str(account_id),
        "provider": provider,
    }


async def test_link_returns_created_mapping(
    async_client: AsyncClient, household_singleton: AsyncSession
) -> None:
    user_id = await _make_user(household_singleton)
    account_id = await _make_account(household_singleton, user_id)

    resp = await async_client.post(
        "/imports/ofx/link-account", json=_link_body(account_id), headers=_bearer(user_id)
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["external_ref"] == _BOURSO_REF
    assert body["internal_account_id"] == str(account_id)
    assert body["provider"] == "ofx"
    assert UUID(body["id"])  # a real mapping id


async def test_link_then_preview_no_longer_account_not_linked(
    async_client: AsyncClient, household_singleton: AsyncSession
) -> None:
    user_id = await _make_user(household_singleton)
    account_id = await _make_account(household_singleton, user_id)

    # Before linking, preview reports the ref as not linked.
    before = await async_client.post(
        "/imports/ofx/preview", files=_files("boursorama_export_2026.ofx"), headers=_bearer(user_id)
    )
    assert before.status_code == 422
    assert before.json()["detail"]["code"] == "account_not_linked"

    link_resp = await async_client.post(
        "/imports/ofx/link-account", json=_link_body(account_id), headers=_bearer(user_id)
    )
    assert link_resp.status_code == 201, link_resp.text

    after = await async_client.post(
        "/imports/ofx/preview", files=_files("boursorama_export_2026.ofx"), headers=_bearer(user_id)
    )
    assert after.status_code == 200, after.text


async def test_double_link_conflict_409(
    async_client: AsyncClient, household_singleton: AsyncSession
) -> None:
    user_id = await _make_user(household_singleton)
    account_id = await _make_account(household_singleton, user_id)

    first = await async_client.post(
        "/imports/ofx/link-account", json=_link_body(account_id), headers=_bearer(user_id)
    )
    assert first.status_code == 201, first.text

    second = await async_client.post(
        "/imports/ofx/link-account", json=_link_body(account_id), headers=_bearer(user_id)
    )
    assert second.status_code == 409, second.text
    assert second.json()["detail"]["code"] == "account_already_linked"


async def test_link_inaccessible_internal_account_404(
    async_client: AsyncClient, household_singleton: AsyncSession
) -> None:
    # Account owned by ANOTHER user → 404 (non-disclosure, D8). No mapping created.
    other_id = await _make_user(household_singleton)
    other_account = await _make_account(household_singleton, other_id)
    caller_id = await _make_user(household_singleton)

    resp = await async_client.post(
        "/imports/ofx/link-account", json=_link_body(other_account), headers=_bearer(caller_id)
    )

    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"]["code"] == "account_not_found"


async def test_link_unknown_account_404(
    async_client: AsyncClient, household_singleton: AsyncSession
) -> None:
    # A random non-existent account id is byte-identical to an inaccessible one.
    caller_id = await _make_user(household_singleton)
    resp = await async_client.post(
        "/imports/ofx/link-account", json=_link_body(uuid4()), headers=_bearer(caller_id)
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"]["code"] == "account_not_found"


async def test_link_admin_not_exempt_404(
    async_client: AsyncClient, household_singleton: AsyncSession
) -> None:
    # F03: an admin linking another user's personal account is NOT exempt → 404.
    member_id = await _make_user(household_singleton)
    member_account = await _make_account(household_singleton, member_id)
    admin_id = await _make_user(household_singleton, role=UserRole.ADMIN)

    resp = await async_client.post(
        "/imports/ofx/link-account", json=_link_body(member_account), headers=_bearer(admin_id)
    )

    assert resp.status_code == 404, resp.text


async def test_link_unknown_provider_422(
    async_client: AsyncClient, household_singleton: AsyncSession
) -> None:
    user_id = await _make_user(household_singleton)
    account_id = await _make_account(household_singleton, user_id)

    resp = await async_client.post(
        "/imports/ofx/link-account",
        json=_link_body(account_id, provider="sftp"),
        headers=_bearer(user_id),
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "unknown_provider"


async def test_link_anonymous_401(async_client: AsyncClient) -> None:
    resp = await async_client.post("/imports/ofx/link-account", json=_link_body(uuid4()))
    assert resp.status_code == 401, resp.text
