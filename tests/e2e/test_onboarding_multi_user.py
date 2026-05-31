"""E2E Parcours 1 — Onboarding multi-user (golden path), covers E02+E03+E04.

One black-box HTTP chain from an empty deployment to a working member
account: bootstrap → lock-after-init → admin login → invitation →
preview → accept → single-use consumption → RBAC → member login, plus the
anti-poisoning and anti-enumeration invariants and the audit trail.

Per D2 this asserts **state transitions and propagation**, not the
per-endpoint contracts already covered in `tests/integration/`.
"""

import pytest
from sqlalchemy import select

from backend.modules.auth.domain import UserRole
from backend.modules.auth.models import User
from tests.e2e._helpers import (
    ADMIN_PASSWORD,
    auth_headers,
    bootstrap_admin,
    create_invitation,
    fetch_audit_rows,
    onboard_member,
    user_id_by_email,
)

pytestmark = [pytest.mark.e2e, pytest.mark.usefixtures("_clean_committed_db")]

INVITEE_EMAIL = "invitee@example.com"
MEMBER_PASSWORD = "member-password-123"
ATTACKER_EMAIL = "attacker@evil.example.com"

ACCOUNTS_MEMBER_EMAIL = "accounts-member@example.com"


def _account_ids(payload: list[dict[str, object]]) -> set[str]:
    return {row["id"] for row in payload}  # type: ignore[misc]


async def test_onboarding_multi_user(committed_client, committed_sessionmaker):  # noqa: PLR0915 — E2E journey is deliberately long (D10)
    client = committed_client

    # 1. /setup open on a fresh DB.
    assert (await client.get("/setup")).status_code == 200

    # 2. Bootstrap the first admin → TokenPair.
    admin_access, _admin_refresh, admin_email = await bootstrap_admin(client)

    # 3. Lock-after-init: GET /setup → 404 (cache invalidated via after_commit).
    assert (await client.get("/setup")).status_code == 404
    # 4. Replaying POST /setup → 404.
    replay_setup = await client.post(
        "/setup",
        json={
            "email": "other@example.com",
            "password": "x" * 16,
            "display_name": "X",
            "household_name": "Y",
        },
    )
    assert replay_setup.status_code == 404

    # 5. Admin login: wrong password → 401, correct → 200.
    assert (
        await client.post("/auth/login", json={"email": admin_email, "password": "wrong"})
    ).status_code == 401
    relogin = await client.post(
        "/auth/login", json={"email": admin_email, "password": ADMIN_PASSWORD}
    )
    assert relogin.status_code == 200

    # 6. Invitation (Bearer admin) → 201; raw token captured from the body (D4).
    inv = await create_invitation(client, admin_access, INVITEE_EMAIL)
    raw_token = inv["token"]
    assert inv["accept_url"].endswith(f"token={raw_token}")

    # 7. Preview (GET) → 200, does NOT consume the token.
    preview = await client.get("/accept-invite", params={"token": raw_token})
    assert preview.status_code == 200
    assert preview.json()["email"] == INVITEE_EMAIL

    # 8. Accept (POST) with a poisoned role/email body → ignored (anti-poisoning).
    accept = await client.post(
        "/accept-invite",
        json={
            "token": raw_token,
            "password": MEMBER_PASSWORD,
            "display_name": "Member",
            "role": "admin",  # dropped server-side
            "email": ATTACKER_EMAIL,  # dropped server-side
        },
    )
    assert accept.status_code == 200
    member_access = accept.json()["access_token"]

    # 9. Replaying the same token → 410 (consumed exactly once).
    assert (
        await client.post(
            "/accept-invite",
            json={"token": raw_token, "password": MEMBER_PASSWORD, "display_name": "Member"},
        )
    ).status_code == 410

    # 10-11. RBAC: a member is not an admin → 403 on admin routes.
    assert (
        await client.post(
            "/invitations", json={"email": "z@example.com"}, headers=auth_headers(member_access)
        )
    ).status_code == 403
    assert (
        await client.get("/invitations", headers=auth_headers(member_access))
    ).status_code == 403

    # 12. The member account works independently (direct login).
    assert (
        await client.post("/auth/login", json={"email": INVITEE_EMAIL, "password": MEMBER_PASSWORD})
    ).status_code == 200

    # 13. Anti-poisoning verified against the DB: role is member, the body's
    #     email created no user.
    async with committed_sessionmaker() as session:
        member = (
            await session.execute(select(User).where(User.email == INVITEE_EMAIL))
        ).scalar_one()
    assert member.role == UserRole.MEMBER
    assert await user_id_by_email(committed_sessionmaker, ATTACKER_EMAIL) is None

    # 14. Audit trail (side-channel D3): invite_sent (actor=admin) THEN
    #     invite_accepted (actor-less, target=member), in order (D11).
    admin_id = await user_id_by_email(committed_sessionmaker, admin_email)
    member_id = await user_id_by_email(committed_sessionmaker, INVITEE_EMAIL)
    rows = await fetch_audit_rows(committed_sessionmaker)
    assert [r[0] for r in rows] == ["invite_sent", "invite_accepted"]
    assert rows[0][1] == admin_id and rows[0][2] is None  # sent: by admin, no target
    assert rows[1][1] is None and rows[1][2] == member_id  # accepted: actor-less


async def test_onboarding_accounts_etancheite(committed_client, committed_sessionmaker):
    """Parcours 1 extension (S05.3): accounts watertightness F03, end-to-end.

    Bootstrap admin → onboard a member → admin creates a personal + a shared
    account → `GET /accounts` reflects the RBAC filter (a member never sees the
    admin's personal account; the admin is NOT exempt from a member's personal
    account) → a business rejection (currency ≠ EUR, then Σ ratios ≠ 1) is a
    clean 422 end-to-end. Proves the propagation household currency →
    `AccountValidator` → HTTP, and the cross-endpoint role filter that neither
    the unit nor the integration tier exercises inter-role end-to-end (D2/F03).
    """
    client = committed_client

    # 1. Bootstrap admin (household EUR initialised) + onboard a member.
    admin_access, _admin_refresh, admin_email = await bootstrap_admin(client)
    member_access = await onboard_member(
        client, admin_access, ACCOUNTS_MEMBER_EMAIL, MEMBER_PASSWORD
    )
    admin_id = await user_id_by_email(committed_sessionmaker, admin_email)
    member_id = await user_id_by_email(committed_sessionmaker, ACCOUNTS_MEMBER_EMAIL)

    # 2. Admin creates a personal account.
    admin_personal = await client.post(
        "/accounts/personal",
        json={"name": "Admin perso", "type": "courant", "currency": "EUR"},
        headers=auth_headers(admin_access),
    )
    assert admin_personal.status_code == 201, admin_personal.text
    admin_personal_id = admin_personal.json()["id"]

    # 3. Admin creates a shared account including both users (0.5 / 0.5).
    shared = await client.post(
        "/accounts/shared",
        json={
            "name": "Foyer commun",
            "type": "courant",
            "currency": "EUR",
            "members": [
                {"user_id": str(admin_id), "default_share_ratio": "0.5"},
                {"user_id": str(member_id), "default_share_ratio": "0.5"},
            ],
        },
        headers=auth_headers(admin_access),
    )
    assert shared.status_code == 201, shared.text
    shared_id = shared.json()["id"]

    # 4. RBAC filter (F03): admin sees personal + shared; the member sees ONLY
    #    the shared account — never the admin's personal account.
    admin_list = await client.get("/accounts", headers=auth_headers(admin_access))
    assert admin_list.status_code == 200
    assert _account_ids(admin_list.json()) == {admin_personal_id, shared_id}

    member_list = await client.get("/accounts", headers=auth_headers(member_access))
    assert member_list.status_code == 200
    assert _account_ids(member_list.json()) == {shared_id}

    # 5. The member creates a personal account; the admin is NOT exempt — it
    #    does not appear in the admin's listing (F03, the load-bearing cover).
    member_personal = await client.post(
        "/accounts/personal",
        json={"name": "Member perso", "type": "livret", "currency": "EUR"},
        headers=auth_headers(member_access),
    )
    assert member_personal.status_code == 201, member_personal.text
    member_personal_id = member_personal.json()["id"]

    admin_list_after = await client.get("/accounts", headers=auth_headers(admin_access))
    assert member_personal_id not in _account_ids(admin_list_after.json())

    # 6. Business rejections propagate to a clean 422 end-to-end.
    bad_currency = await client.post(
        "/accounts/shared",
        json={
            "name": "Mauvaise devise",
            "type": "courant",
            "currency": "USD",  # ≠ household base EUR
            "members": [
                {"user_id": str(admin_id), "default_share_ratio": "0.5"},
                {"user_id": str(member_id), "default_share_ratio": "0.5"},
            ],
        },
        headers=auth_headers(admin_access),
    )
    assert bad_currency.status_code == 422, bad_currency.text

    bad_sum = await client.post(
        "/accounts/shared",
        json={
            "name": "Mauvaise somme",
            "type": "courant",
            "currency": "EUR",
            "members": [
                {"user_id": str(admin_id), "default_share_ratio": "0.5"},
                {"user_id": str(member_id), "default_share_ratio": "0.4"},
            ],
        },
        headers=auth_headers(admin_access),
    )
    assert bad_sum.status_code == 422, bad_sum.text
