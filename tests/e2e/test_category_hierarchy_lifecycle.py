"""E2E Parcours 3 — Category hierarchy lifecycle, covers E06 (S06.1→S06.3).

One black-box HTTP chain over a category tree's life: build A › B › C → an
indirect cycle is refused (tree unchanged, no audit row) → archiving the
intermediate node does NOT cascade (its parent AND its child stay active, the
child is not re-parented) → a legitimate re-parent is audited (CATEGORY_MOVED,
read side-channel) → the include_archived filter behaves → a non-admin member
manages categories too (household-scoped, no per-resource filter — contrast
accounts F03, which are watertight by owner).

Per §12 this asserts **state transitions and propagation** (REST → domain →
audit, non-cascade end-to-end), not the per-endpoint contracts already covered
in `tests/integration/test_budget_routes_*` (S06.3). The 401-anonymous boundary
("household-global ≠ public") is one such per-endpoint contract — pinned on
every route by `test_{post,get,move,delete}_401_anonymous` — so it is delegated
to integration, not re-driven here.
"""

from typing import Any

import pytest

from tests.e2e._helpers import (
    auth_headers,
    bootstrap_admin,
    create_category,
    fetch_audit_by_action,
    onboard_member,
    user_id_by_email,
)

pytestmark = [pytest.mark.e2e, pytest.mark.usefixtures("_clean_committed_db")]

MEMBER_EMAIL = "category-member@example.com"
MEMBER_PASSWORD = "member-password-123"


def _parent_map(listing: list[dict[str, Any]]) -> dict[str, str | None]:
    return {row["name"]: row["parent_id"] for row in listing}


def _names(listing: list[dict[str, Any]]) -> set[str]:
    return {row["name"] for row in listing}


async def test_category_hierarchy_lifecycle(  # noqa: PLR0915 — E2E journey is deliberately long
    committed_client, committed_sessionmaker
):
    client = committed_client
    admin_access, _refresh, admin_email = await bootstrap_admin(client)
    admin_headers = auth_headers(admin_access)

    # 1. Build A › B › C (root → child → grandchild).
    a = await create_category(client, admin_access, name="A")
    b = await create_category(client, admin_access, name="B", parent_id=a["id"])
    c = await create_category(client, admin_access, name="C", parent_id=b["id"])

    # 2. Indirect cycle refused: move A under its own descendant C → 422, and the
    #    tree is unchanged (verified by GET, not just by the status code). The
    #    cycle raises BEFORE any write, so it left NO audit row (D6 S06.3) — the
    #    negative half of the audit oracle, observed end-to-end.
    cycle = await client.patch(
        f"/categories/{a['id']}/parent", json={"parent_id": c["id"]}, headers=admin_headers
    )
    assert cycle.status_code == 422, cycle.text
    listing = (await client.get("/categories", headers=admin_headers)).json()
    assert _parent_map(listing) == {"A": None, "B": a["id"], "C": b["id"]}
    assert await fetch_audit_by_action(committed_sessionmaker, action="category_moved") == []

    # 3. Archive the intermediate node without cascade: DELETE B → 204. B has a
    #    parent (A) AND a child (C); both stay active, and C is NOT auto-reparented
    #    (CONTEXT.md "pas de cascade, pas de re-parentage automatique"). This is the
    #    full non-cascade property — ascendant and descendant — observed via the API.
    assert (await client.delete(f"/categories/{b['id']}", headers=admin_headers)).status_code == 204
    after_archive = (await client.get("/categories", headers=admin_headers)).json()
    assert _names(after_archive) == {"A", "C"}  # B drops out of the default listing
    assert all(row["archived_at"] is None for row in after_archive)  # A and C stay active
    assert _parent_map(after_archive) == {
        "A": None,
        "C": b["id"],
    }  # C still points at the tombstone

    # 4. Listing filter: default excludes B; include_archived=true re-includes it
    #    as a tombstone (same entity, archived_at non-null — not a fortuitous
    #    presence/absence).
    with_archived = (
        await client.get("/categories", params={"include_archived": "true"}, headers=admin_headers)
    ).json()
    assert _names(with_archived) == {"A", "B", "C"}
    b_row = next(row for row in with_archived if row["name"] == "B")
    assert b_row["archived_at"] is not None

    # 5. Legitimate move audited: re-home C from the archived B onto A → 200 (C is
    #    active, so it remains movable). Exactly one CATEGORY_MOVED row in the
    #    move+audit transaction (D5/D6 S06.3), read side-channel (D3): actor=admin,
    #    target NULL, metadata correlating the 200 with from=B / to=A.
    moved = await client.patch(
        f"/categories/{c['id']}/parent", json={"parent_id": a["id"]}, headers=admin_headers
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["parent_id"] == a["id"]

    admin_id = await user_id_by_email(committed_sessionmaker, admin_email)
    moves = await fetch_audit_by_action(committed_sessionmaker, action="category_moved")
    assert len(moves) == 1
    actor, target, meta = moves[0]
    assert actor == admin_id  # actor = the admin who issued the move
    assert target is None  # target NULL: the moved thing is a category, not a user
    assert meta == {"category_id": c["id"], "from_parent_id": b["id"], "to_parent_id": a["id"]}

    # 6. Household-scope: a non-admin member creates AND moves categories (no 403,
    #    no per-resource filter — contrast accounts F03), and the admin sees them.
    member_access = await onboard_member(client, admin_access, MEMBER_EMAIL, MEMBER_PASSWORD)
    member_id = await user_id_by_email(committed_sessionmaker, MEMBER_EMAIL)
    m_parent = await create_category(client, member_access, name="M-parent")
    m_child = await create_category(client, member_access, name="M-child", parent_id=m_parent["id"])
    member_move = await client.patch(
        f"/categories/{m_child['id']}/parent",
        json={"parent_id": None},  # promote to root — any member may re-parent
        headers=auth_headers(member_access),
    )
    assert member_move.status_code == 200, member_move.text

    # The admin sees the member's categories (household-global, no owner filter).
    admin_view = (await client.get("/categories", headers=admin_headers)).json()
    assert {"M-parent", "M-child"} <= _names(admin_view)

    # The member's move is audited under the member's actor (audit = household
    # journal — every member is imputed). Asserted by content + actor on the
    # action-filtered oracle, so the interleaved invite_* rows from onboarding do
    # not perturb it, and the root-promotion `to_parent_id: None` branch is pinned.
    moves = await fetch_audit_by_action(committed_sessionmaker, action="category_moved")
    assert len(moves) == 2  # admin's C→A, then the member's M-child→root
    actor, target, meta = moves[1]
    assert actor == member_id  # the member is imputed for their own move
    assert target is None
    assert meta == {
        "category_id": m_child["id"],
        "from_parent_id": m_parent["id"],
        "to_parent_id": None,
    }
