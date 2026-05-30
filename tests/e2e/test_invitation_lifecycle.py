"""E2E Parcours 2 — Invitation lifecycle, covers E04 (admin routes + anti-enum).

One black-box HTTP chain over an invitation's admin life: create →
duplicate-pending 409 → regenerate (old link dies, new one works) → revoke
(link gone on GET and POST) → pending-list exclusion, with a DB
side-channel assertion on the ordered, admin-attributed audit trail.

Per D2 this asserts **state transitions** (token rotation, revocation
propagation), not the per-endpoint contracts already covered in
`tests/integration/`.
"""

import pytest

from tests.e2e._helpers import (
    auth_headers,
    bootstrap_admin,
    create_invitation,
    fetch_audit_rows,
    user_id_by_email,
)

pytestmark = [pytest.mark.e2e, pytest.mark.usefixtures("_clean_committed_db")]

INVITEE_EMAIL = "x@example.com"
MEMBER_PASSWORD = "member-password-123"


async def test_invitation_lifecycle(committed_client, committed_sessionmaker):
    client = committed_client
    admin_access, _refresh, admin_email = await bootstrap_admin(client)
    headers = auth_headers(admin_access)

    # 2. Create invitation for email X → 201 (token A).
    inv = await create_invitation(client, admin_access, INVITEE_EMAIL)
    inv_id, token_a = inv["id"], inv["token"]

    # 3. Same email X while one is still pending → 409.
    dup = await client.post("/invitations", json={"email": INVITEE_EMAIL}, headers=headers)
    assert dup.status_code == 409

    # 4. Regenerate → 200 (token B); link A dies, link B works.
    regen = await client.post(f"/invitations/{inv_id}/regenerate", headers=headers)
    assert regen.status_code == 200
    token_b = regen.json()["token"]
    assert token_b != token_a
    assert (await client.get("/accept-invite", params={"token": token_a})).status_code == 410
    assert (await client.get("/accept-invite", params={"token": token_b})).status_code == 200

    # 5. Revoke → 204; link B is gone on both GET and POST.
    assert (await client.delete(f"/invitations/{inv_id}", headers=headers)).status_code == 204
    assert (await client.get("/accept-invite", params={"token": token_b})).status_code == 410
    assert (
        await client.post(
            "/accept-invite",
            json={"token": token_b, "password": MEMBER_PASSWORD, "display_name": "M"},
        )
    ).status_code == 410

    # 6. The pending list no longer contains the revoked invitation.
    listing = await client.get("/invitations", headers=headers)
    assert listing.status_code == 200
    assert all(row["id"] != inv_id for row in listing.json())

    # 7. Audit (side-channel D3): sent → regenerated → revoked, all by admin (D11).
    admin_id = await user_id_by_email(committed_sessionmaker, admin_email)
    rows = await fetch_audit_rows(committed_sessionmaker)
    assert [r[0] for r in rows] == ["invite_sent", "invite_regenerated", "invite_revoked"]
    assert all(r[1] == admin_id for r in rows)
