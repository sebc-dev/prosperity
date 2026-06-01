"""Integration tests for the category CRUD routes (S06.3, P06.3.2).

Drives `POST /categories`, `GET /categories`, `PATCH /categories/{id}` over
httpx against a real Postgres (`async_client` + `auth_schema` share one
connection/transaction; the per-test rollback reverts everything). Covers:

- the server-side id (a client-supplied `id` → 422, #104);
- `color` validated at the boundary (`^#[0-9A-Fa-f]{6}$` → 422 otherwise);
- an unknown `parent_id` → 422 via the FK 23503 path, nothing persisted;
- `include_archived` default (archived excluded) vs explicit `true`;
- the edit route rejecting a `parent_id` (re-parenting is a distinct route)
  and 404-ing an archived category;
- 401 for anonymous callers (`get_current_user`), with NO `require_admin` —
  any member manages categories (D3).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.modules.auth.models import User
from backend.modules.auth.service.jwt import issue_access_token
from backend.modules.budget.models import Category

_settings = get_settings()

UserMaker = Callable[..., Awaitable[User]]


def _bearer(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


async def _count(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(Category))).scalar_one()


# ---------------------------------------------------------------------------
# POST /categories
# ---------------------------------------------------------------------------


async def test_post_201_root(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    user = await bound_user_factory(email="m1@example.com")

    resp = await async_client.post(
        "/categories", json={"name": "Logement"}, headers=_bearer(user.id)
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Logement"
    assert body["parent_id"] is None
    assert body["archived_at"] is None
    assert UUID(body["id"])  # server-generated


async def test_post_201_with_parent(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    user = await bound_user_factory(email="m2@example.com")
    root = await async_client.post("/categories", json={"name": "Root"}, headers=_bearer(user.id))
    root_id = root.json()["id"]

    resp = await async_client.post(
        "/categories",
        json={"name": "Sub", "parent_id": root_id, "color": "#1A2B3C", "icon": "home"},
        headers=_bearer(user.id),
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["parent_id"] == root_id
    assert body["color"] == "#1A2B3C"
    assert body["icon"] == "home"


async def test_post_401_anonymous(async_client: AsyncClient, auth_schema: AsyncSession) -> None:
    resp = await async_client.post("/categories", json={"name": "X"})
    assert resp.status_code == 401


async def test_post_422_invalid_color(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    user = await bound_user_factory(email="m3@example.com")

    resp = await async_client.post(
        "/categories", json={"name": "X", "color": "red"}, headers=_bearer(user.id)
    )

    assert resp.status_code == 422
    assert await _count(auth_schema) == 0


async def test_post_422_client_supplied_id(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    # #104: the id is server-side; `extra="forbid"` rejects a client id.
    user = await bound_user_factory(email="m4@example.com")

    resp = await async_client.post(
        "/categories",
        json={"name": "X", "id": str(uuid4())},
        headers=_bearer(user.id),
    )

    assert resp.status_code == 422
    assert await _count(auth_schema) == 0


async def test_post_422_unknown_parent(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    # Detector OK (empty chain) → flush → self-FK 23503 → curated 422, not 500.
    user = await bound_user_factory(email="m5@example.com")

    resp = await async_client.post(
        "/categories",
        json={"name": "Orphan", "parent_id": str(uuid4())},
        headers=_bearer(user.id),
    )

    assert resp.status_code == 422, resp.text
    assert await _count(auth_schema) == 0


# ---------------------------------------------------------------------------
# GET /categories
# ---------------------------------------------------------------------------


async def test_get_default_excludes_archived(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    user = await bound_user_factory(email="g1@example.com")
    active = Category(name="Active", parent_id=None)
    archived = Category(name="Archived", parent_id=None, archived_at=datetime.now(UTC))
    auth_schema.add_all([active, archived])
    await auth_schema.flush()

    resp = await async_client.get("/categories", headers=_bearer(user.id))

    assert resp.status_code == 200, resp.text
    names = {c["name"] for c in resp.json()}
    assert names == {"Active"}


async def test_get_include_archived_true_includes(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    user = await bound_user_factory(email="g2@example.com")
    archived = Category(name="Archived", parent_id=None, archived_at=datetime.now(UTC))
    auth_schema.add(archived)
    await auth_schema.flush()

    resp = await async_client.get(
        "/categories", params={"include_archived": "true"}, headers=_bearer(user.id)
    )

    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["name"] == "Archived"
    assert rows[0]["archived_at"] is not None  # exposed (unlike AccountResponse)


async def test_get_401_anonymous(async_client: AsyncClient, auth_schema: AsyncSession) -> None:
    resp = await async_client.get("/categories")
    assert resp.status_code == 401


async def test_get_order_is_deterministic_by_id_tiebreaker(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    # Two rows inserted in the SAME transaction share `created_at` (server-side
    # `func.now()` = transaction start), so only the `(created_at, id)`
    # tie-breaker makes the order deterministic. Explicit out-of-order ids
    # (`hi` added before `lo`) prove the ORDER BY is applied, not insertion order.
    user = await bound_user_factory(email="order@example.com")
    lo = Category(id=UUID(int=1), name="Lo", parent_id=None)
    hi = Category(id=UUID(int=2), name="Hi", parent_id=None)
    auth_schema.add_all([hi, lo])
    await auth_schema.flush()

    resp = await async_client.get("/categories", headers=_bearer(user.id))

    assert resp.status_code == 200, resp.text
    ids = [row["id"] for row in resp.json()]
    assert ids == [str(UUID(int=1)), str(UUID(int=2))]  # ascending id, stable


async def test_get_response_shape(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    user = await bound_user_factory(email="g3@example.com")
    await async_client.post(
        "/categories",
        json={"name": "Shape", "color": "#abcdef", "icon": "tag"},
        headers=_bearer(user.id),
    )

    resp = await async_client.get("/categories", headers=_bearer(user.id))

    assert resp.status_code == 200
    row = resp.json()[0]
    assert set(row) == {
        "id",
        "name",
        "color",
        "icon",
        "parent_id",
        "created_at",
        "archived_at",
    }


# ---------------------------------------------------------------------------
# PATCH /categories/{id}  (edit name/color/icon)
# ---------------------------------------------------------------------------


async def test_patch_200_edits_name(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    user = await bound_user_factory(email="p1@example.com")
    created = await async_client.post("/categories", json={"name": "Old"}, headers=_bearer(user.id))
    cid = created.json()["id"]

    resp = await async_client.patch(
        f"/categories/{cid}", json={"name": "New"}, headers=_bearer(user.id)
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "New"


async def test_patch_200_edits_color_icon(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    user = await bound_user_factory(email="p2@example.com")
    created = await async_client.post("/categories", json={"name": "C"}, headers=_bearer(user.id))
    cid = created.json()["id"]

    resp = await async_client.patch(
        f"/categories/{cid}",
        json={"color": "#0a0b0c", "icon": "wallet"},
        headers=_bearer(user.id),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["color"] == "#0a0b0c"
    assert body["icon"] == "wallet"
    assert body["name"] == "C"  # untouched


async def test_patch_422_invalid_color(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    user = await bound_user_factory(email="p3@example.com")
    created = await async_client.post("/categories", json={"name": "C"}, headers=_bearer(user.id))
    cid = created.json()["id"]

    resp = await async_client.patch(
        f"/categories/{cid}", json={"color": "nope"}, headers=_bearer(user.id)
    )

    assert resp.status_code == 422


async def test_patch_422_parent_id_forbidden(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    # Re-parenting is a distinct route; a `parent_id` in the edit body → 422.
    user = await bound_user_factory(email="p4@example.com")
    created = await async_client.post("/categories", json={"name": "C"}, headers=_bearer(user.id))
    cid = created.json()["id"]

    resp = await async_client.patch(
        f"/categories/{cid}",
        json={"parent_id": str(uuid4())},
        headers=_bearer(user.id),
    )

    assert resp.status_code == 422


async def test_patch_404_unknown(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    user = await bound_user_factory(email="p5@example.com")

    resp = await async_client.patch(
        f"/categories/{uuid4()}", json={"name": "X"}, headers=_bearer(user.id)
    )

    assert resp.status_code == 404


async def test_patch_404_archived(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    # An archived category is invisible → 404 (D10).
    user = await bound_user_factory(email="p6@example.com")
    archived = Category(name="Gone", parent_id=None, archived_at=datetime.now(UTC))
    auth_schema.add(archived)
    await auth_schema.flush()
    cid = archived.id

    resp = await async_client.patch(
        f"/categories/{cid}", json={"name": "X"}, headers=_bearer(user.id)
    )

    assert resp.status_code == 404


async def test_patch_401_anonymous(async_client: AsyncClient, auth_schema: AsyncSession) -> None:
    resp = await async_client.patch(f"/categories/{uuid4()}", json={"name": "X"})
    assert resp.status_code == 401
