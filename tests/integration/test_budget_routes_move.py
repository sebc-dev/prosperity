"""Integration tests for `PATCH /categories/{id}/parent` + `DELETE` (S06.3, P06.3.3).

Drives the re-parent route (with its audit side-effect) and the archive route
over httpx (`async_client` + `auth_schema`, per-test rollback). Covers:

- a successful move writes ONE `CATEGORY_MOVED` audit row (UUID-string
  metadata, `target` NULL, actor = caller) in the same transaction (D5);
- the move records the *previous* parent and a null `to_parent` for a
  move-to-root;
- a cycle is a 422 with NO audit row and NO write (critère #4, D6);
- the inverse atomicity: if the audit INSERT fails, the move is rolled back
  (D6 — closes the loop);
- an archived / unknown node → 404, an unknown new parent → 422, anonymous →
  401;
- `DELETE` archives (row preserved); a category with an active child is
  *archived*, never refused — proving the hard-delete is NOT routed (D8);
  re-DELETE → 404 (D9).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import backend.modules.budget.transports.http as budget_http
from backend.config import get_settings
from backend.modules.auth.models import AdminAuditLog, User
from backend.modules.auth.service.jwt import issue_access_token
from backend.modules.budget.models import Category

_settings = get_settings()

UserMaker = Callable[..., Awaitable[User]]


def _bearer(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


async def _audit_rows(session: AsyncSession) -> list[AdminAuditLog]:
    return list(
        (await session.execute(select(AdminAuditLog).execution_options(populate_existing=True)))
        .scalars()
        .all()
    )


async def _count(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(Category))).scalar_one()


async def _parent_id_of(session: AsyncSession, category_id: UUID) -> UUID | None:
    return (
        await session.execute(select(Category.parent_id).where(Category.id == category_id))
    ).scalar_one()


async def _seed(session: AsyncSession, name: str, parent_id: UUID | None = None) -> Category:
    category = Category(name=name, parent_id=parent_id)
    session.add(category)
    await session.flush()
    return category


# ---------------------------------------------------------------------------
# PATCH /categories/{id}/parent  (move + audit)
# ---------------------------------------------------------------------------


async def test_move_200_writes_audit(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    user = await bound_user_factory(email="mv1@example.com")
    parent = await _seed(auth_schema, "Parent")
    child = await _seed(auth_schema, "Child")
    parent_id, child_id = parent.id, child.id

    resp = await async_client.patch(
        f"/categories/{child_id}/parent",
        json={"parent_id": str(parent_id)},
        headers=_bearer(user.id),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["parent_id"] == str(parent_id)

    rows = await _audit_rows(auth_schema)
    assert len(rows) == 1
    audit = rows[0]
    assert audit.action == "category_moved"
    assert audit.actor_user_id == user.id
    assert audit.target_user_id is None
    assert audit.event_metadata == {
        "category_id": str(child_id),
        "from_parent_id": None,
        "to_parent_id": str(parent_id),
    }


async def test_move_records_previous_parent(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    # A child of B, moved under C ⇒ from_parent_id = B, to_parent_id = C.
    user = await bound_user_factory(email="mv2@example.com")
    b = await _seed(auth_schema, "B")
    c = await _seed(auth_schema, "C")
    a = await _seed(auth_schema, "A", parent_id=b.id)
    a_id, b_id, c_id = a.id, b.id, c.id

    resp = await async_client.patch(
        f"/categories/{a_id}/parent", json={"parent_id": str(c_id)}, headers=_bearer(user.id)
    )

    assert resp.status_code == 200, resp.text
    audit = (await _audit_rows(auth_schema))[0]
    assert audit.event_metadata == {
        "category_id": str(a_id),
        "from_parent_id": str(b_id),
        "to_parent_id": str(c_id),
    }


async def test_move_to_root_records_null_to_parent(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    user = await bound_user_factory(email="mv3@example.com")
    parent = await _seed(auth_schema, "Parent")
    child = await _seed(auth_schema, "Child", parent_id=parent.id)
    parent_id, child_id = parent.id, child.id

    resp = await async_client.patch(
        f"/categories/{child_id}/parent", json={"parent_id": None}, headers=_bearer(user.id)
    )

    assert resp.status_code == 200, resp.text
    assert await _parent_id_of(auth_schema, child_id) is None
    audit = (await _audit_rows(auth_schema))[0]
    assert audit.event_metadata == {
        "category_id": str(child_id),
        "from_parent_id": str(parent_id),
        "to_parent_id": None,  # null, NOT the string "None"
    }


async def test_move_cycle_422_no_audit_no_write(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    # A→B; moving A under its descendant B closes a cycle (critère #4).
    user = await bound_user_factory(email="mv4@example.com")
    a = await _seed(auth_schema, "A")
    b = await _seed(auth_schema, "B", parent_id=a.id)
    a_id, b_id = a.id, b.id

    resp = await async_client.patch(
        f"/categories/{a_id}/parent", json={"parent_id": str(b_id)}, headers=_bearer(user.id)
    )

    assert resp.status_code == 422, resp.text
    assert await _audit_rows(auth_schema) == []  # no audit row
    assert await _parent_id_of(auth_schema, a_id) is None  # A.parent unchanged


async def test_move_audit_failure_rolls_back_move(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Inverse atomicity (D6): the audit INSERT fails AFTER the move flush ⇒ the
    # whole transaction rolls back, so the move does not persist and no audit
    # row survives. Closes the move↔audit atomicity loop.
    user = await bound_user_factory(email="mv5@example.com")
    parent = await _seed(auth_schema, "Parent")
    child = await _seed(auth_schema, "Child")
    parent_id, child_id = parent.id, child.id

    async def _boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("audit exploded")

    monkeypatch.setattr(budget_http, "log_admin_action", _boom)

    with pytest.raises(RuntimeError):
        await async_client.patch(
            f"/categories/{child_id}/parent",
            json={"parent_id": str(parent_id)},
            headers=_bearer(user.id),
        )

    # The request session rolled back; the move did not persist, no audit row.
    auth_schema.expire_all()
    assert await _parent_id_of(auth_schema, child_id) is None
    assert await _audit_rows(auth_schema) == []


async def test_move_404_unknown_node(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    user = await bound_user_factory(email="mv6@example.com")

    resp = await async_client.patch(
        f"/categories/{uuid4()}/parent", json={"parent_id": None}, headers=_bearer(user.id)
    )

    assert resp.status_code == 404
    assert await _audit_rows(auth_schema) == []


async def test_move_404_archived_node(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    # An archived category is invisible → cannot be moved (D10).
    user = await bound_user_factory(email="mv7@example.com")
    parent = await _seed(auth_schema, "Parent")
    archived = Category(name="Gone", parent_id=None, archived_at=datetime.now(UTC))
    auth_schema.add(archived)
    await auth_schema.flush()
    parent_id, archived_id = parent.id, archived.id

    resp = await async_client.patch(
        f"/categories/{archived_id}/parent",
        json={"parent_id": str(parent_id)},
        headers=_bearer(user.id),
    )

    assert resp.status_code == 404
    assert await _audit_rows(auth_schema) == []


async def test_move_422_unknown_new_parent(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    user = await bound_user_factory(email="mv8@example.com")
    child = await _seed(auth_schema, "Child")
    child_id = child.id

    resp = await async_client.patch(
        f"/categories/{child_id}/parent",
        json={"parent_id": str(uuid4())},
        headers=_bearer(user.id),
    )

    assert resp.status_code == 422, resp.text
    assert await _audit_rows(auth_schema) == []


async def test_move_401_anonymous(async_client: AsyncClient, auth_schema: AsyncSession) -> None:
    resp = await async_client.patch(f"/categories/{uuid4()}/parent", json={"parent_id": None})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /categories/{id}  (archive — soft-delete)
# ---------------------------------------------------------------------------


async def test_delete_204_archives_row_preserved(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    user = await bound_user_factory(email="dl1@example.com")
    category = await _seed(auth_schema, "Logement")
    category_id = category.id

    resp = await async_client.delete(f"/categories/{category_id}", headers=_bearer(user.id))

    assert resp.status_code == 204, resp.text
    # Row preserved with archived_at set.
    auth_schema.expire_all()
    assert await _count(auth_schema) == 1
    archived_at = (
        await auth_schema.execute(select(Category.archived_at).where(Category.id == category_id))
    ).scalar_one()
    assert archived_at is not None


async def test_delete_child_parent_archives_not_in_use(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    # Observable proof the hard-delete is NOT routed (D8): DELETE on a category
    # WITH an active child → 204 + archive (the route soft-deletes), never a
    # CategoryInUseError. The child stays active (no cascade).
    user = await bound_user_factory(email="dl2@example.com")
    parent = await _seed(auth_schema, "Parent")
    child = await _seed(auth_schema, "Child", parent_id=parent.id)
    parent_id, child_id = parent.id, child.id

    resp = await async_client.delete(f"/categories/{parent_id}", headers=_bearer(user.id))

    assert resp.status_code == 204, resp.text
    auth_schema.expire_all()
    assert await _count(auth_schema) == 2  # both rows preserved
    child_archived_at = (
        await auth_schema.execute(select(Category.archived_at).where(Category.id == child_id))
    ).scalar_one()
    assert child_archived_at is None  # child untouched (no cascade)


async def test_delete_redelete_404(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    user = await bound_user_factory(email="dl3@example.com")
    category = await _seed(auth_schema, "Logement")
    category_id = category.id

    first = await async_client.delete(f"/categories/{category_id}", headers=_bearer(user.id))
    assert first.status_code == 204

    second = await async_client.delete(f"/categories/{category_id}", headers=_bearer(user.id))
    assert second.status_code == 404  # already archived → 404 (D9)


async def test_delete_404_unknown(
    async_client: AsyncClient, auth_schema: AsyncSession, bound_user_factory: UserMaker
) -> None:
    user = await bound_user_factory(email="dl4@example.com")
    resp = await async_client.delete(f"/categories/{uuid4()}", headers=_bearer(user.id))
    assert resp.status_code == 404


async def test_delete_401_anonymous(async_client: AsyncClient, auth_schema: AsyncSession) -> None:
    resp = await async_client.delete(f"/categories/{uuid4()}")
    assert resp.status_code == 401
