"""Integration tests for the admin invitation routes (story S04.4).

Drives the full HTTP → `require_admin` → `service.invitations` → audit
chain over httpx against a real Postgres (`auth_schema`). Covers the four
routes (`POST /invitations`, `GET /invitations`,
`POST /invitations/{id}/regenerate`, `DELETE /invitations/{id}`):

- RBAC: admin succeeds, member 403, anonymous 401 (relayed by
  `get_current_user`);
- the raw token is returned **once** and the response/list never carry
  `token_hash`;
- one `admin_audit_logs` row per successful mutation, with
  `{"invitation_id", "email"}` metadata and never the raw token;
- error mapping (409 duplicate / terminal, 404 unknown, 204 revoke);
- the MVP transmission warning (`invitation_link_issued`) carrying the
  raw token (P04.4.3) — the documented self-hosted exception.

`async_client` and `auth_schema` share one connection/transaction, so a
request's savepoint-committed writes are visible to the test session and
the per-test rollback reverts everything.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.main import app
from backend.modules.auth.domain import UserRole
from backend.modules.auth.models import AdminAuditLog, Invitation, User
from backend.modules.auth.service import invitations as invitation_service
from backend.modules.auth.service.invitations import hash_invitation_token
from backend.modules.auth.service.jwt import issue_access_token

_settings = get_settings()

UserMaker = Callable[..., Awaitable[User]]


def _bearer(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, settings=_settings)}"}


async def _fetch_invitation(session: AsyncSession, invitation_id: UUID) -> Invitation:
    """Read an invitation fresh from the DB.

    `populate_existing` overwrites any stale identity-map copy with the
    current DB row (HTTP requests mutate via their own sessions on the same
    connection) — without expiring *other* live objects the test still
    holds (which would trigger illegal lazy IO in this async context).
    """
    return (
        await session.execute(
            select(Invitation)
            .where(Invitation.id == invitation_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def _all_invitations(session: AsyncSession) -> list[Invitation]:
    return list(
        (await session.execute(select(Invitation).execution_options(populate_existing=True)))
        .scalars()
        .all()
    )


async def _audit_rows(session: AsyncSession) -> list[AdminAuditLog]:
    return list(
        (await session.execute(select(AdminAuditLog).execution_options(populate_existing=True)))
        .scalars()
        .all()
    )


# ---------------------------------------------------------------------------
# POST /invitations
# ---------------------------------------------------------------------------


async def test_create_invitation_as_admin_returns_token_once(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)

    resp = await async_client.post(
        "/invitations", json={"email": "invite@example.com"}, headers=_bearer(admin.id)
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["token"]
    assert body["email"] == "invite@example.com"
    assert UUID(body["id"])
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert abs((expires_at - datetime.now(tz=UTC)) - timedelta(days=7)) < timedelta(minutes=5)
    # No hash field, and the actual hash value never appears in the body.
    assert "token_hash" not in body
    assert hash_invitation_token(body["token"]) not in resp.text


async def test_create_returned_token_matches_db_hash(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)

    resp = await async_client.post(
        "/invitations", json={"email": "invite@example.com"}, headers=_bearer(admin.id)
    )

    body = resp.json()
    inv = await _fetch_invitation(auth_schema, UUID(body["id"]))
    assert inv.token_hash == hash_invitation_token(body["token"])


async def test_create_accept_url_uses_base_url(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)

    resp = await async_client.post(
        "/invitations", json={"email": "invite@example.com"}, headers=_bearer(admin.id)
    )

    body = resp.json()
    assert body["accept_url"] == f"{_settings.app_base_url}/accept-invite?token={body['token']}"


async def test_create_normalizes_email(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)

    resp = await async_client.post(
        "/invitations", json={"email": "Alice@X.com "}, headers=_bearer(admin.id)
    )

    body = resp.json()
    assert body["email"] == "alice@x.com"
    inv = await _fetch_invitation(auth_schema, UUID(body["id"]))
    assert inv.email == "alice@x.com"
    audit = (await _audit_rows(auth_schema))[0]
    assert audit.event_metadata == {"invitation_id": str(inv.id), "email": "alice@x.com"}


async def test_create_forbidden_for_member(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    member = await bound_user_factory(email="member@example.com", role=UserRole.MEMBER)

    resp = await async_client.post(
        "/invitations", json={"email": "invite@example.com"}, headers=_bearer(member.id)
    )

    assert resp.status_code == 403
    assert resp.json() == {"detail": "Forbidden"}
    assert await _all_invitations(auth_schema) == []
    assert await _audit_rows(auth_schema) == []


async def test_create_unauthenticated_401(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
) -> None:
    resp = await async_client.post("/invitations", json={"email": "invite@example.com"})

    assert resp.status_code == 401
    assert await _all_invitations(auth_schema) == []
    assert await _audit_rows(auth_schema) == []


async def test_create_duplicate_pending_returns_409(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    headers = _bearer(admin.id)

    first = await async_client.post(
        "/invitations", json={"email": "invite@example.com"}, headers=headers
    )
    assert first.status_code == 201

    second = await async_client.post(
        "/invitations", json={"email": "invite@example.com"}, headers=headers
    )

    assert second.status_code == 409  # not 500
    assert len(await _all_invitations(auth_schema)) == 1
    assert len(await _audit_rows(auth_schema)) == 1


async def test_create_writes_audit_invite_sent(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)

    resp = await async_client.post(
        "/invitations", json={"email": "invite@example.com"}, headers=_bearer(admin.id)
    )
    body = resp.json()

    rows = await _audit_rows(auth_schema)
    assert len(rows) == 1
    audit = rows[0]
    assert audit.action == "invite_sent"
    assert audit.actor_user_id == admin.id
    assert audit.target_user_id is None
    assert audit.event_metadata == {"invitation_id": body["id"], "email": "invite@example.com"}


async def test_create_audit_metadata_omits_raw_token(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)

    resp = await async_client.post(
        "/invitations", json={"email": "invite@example.com"}, headers=_bearer(admin.id)
    )
    raw = resp.json()["token"]

    audit = (await _audit_rows(auth_schema))[0]
    assert raw not in str(audit.event_metadata)


async def test_create_sets_no_store_headers(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)

    resp = await async_client.post(
        "/invitations", json={"email": "invite@example.com"}, headers=_bearer(admin.id)
    )

    assert resp.headers["cache-control"] == "no-store"
    assert resp.headers["pragma"] == "no-cache"


class _FakeUniqueViolation(Exception):
    """Stand-in for asyncpg's unique-violation, exposing `.sqlstate`.

    `.sqlstate` (not `.pgcode`) is the attribute asyncpg actually exposes on
    `exc.orig`, and the same one the handler reads — matching the prod pattern
    already exercised against a real Postgres in
    `accounts.transports.http.setup_submit` (SQLSTATE-based race discrimination).
    """

    sqlstate = "23505"


class _FakeCheckViolation(Exception):
    sqlstate = "23514"


async def test_create_concurrent_duplicate_integrityerror_maps_to_409(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact concurrent double-create race (partial-index 23505) → 409.

    The sequential case is the service pre-check; this pins the defensive
    `IntegrityError` catch for the race the pre-check can't see — it must
    be a 409, never a 500.
    """
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)

    async def _raise_unique(*_args: object, **_kwargs: object) -> str:
        raise IntegrityError("INSERT", {}, _FakeUniqueViolation())

    monkeypatch.setattr(invitation_service, "create", _raise_unique)

    resp = await async_client.post(
        "/invitations", json={"email": "invite@example.com"}, headers=_bearer(admin.id)
    )

    assert resp.status_code == 409


async def test_create_non_unique_integrityerror_is_not_masked(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-23505 IntegrityError is an app bug → it must re-raise, not 409.

    Only the unique-violation SQLSTATE collapses to 409; anything else
    (here a check-violation) bubbles up so a real defect surfaces as 500.
    """
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)

    async def _raise_check(*_args: object, **_kwargs: object) -> str:
        raise IntegrityError("INSERT", {}, _FakeCheckViolation())

    monkeypatch.setattr(invitation_service, "create", _raise_check)

    with pytest.raises(IntegrityError):
        await async_client.post(
            "/invitations", json={"email": "invite@example.com"}, headers=_bearer(admin.id)
        )


# ---------------------------------------------------------------------------
# GET /invitations
# ---------------------------------------------------------------------------


async def _seed_invitation(
    session: AsyncSession,
    *,
    invited_by: UUID,
    email: str,
    state: str = "pending",  # "pending" | "accepted" | "revoked"
    invited_at: datetime | None = None,
) -> Invitation:
    now = invited_at or datetime.now(tz=UTC)
    inv = Invitation(
        email=email,
        invited_by=invited_by,
        invited_at=now,
        expires_at=now + timedelta(days=7),
        token_hash=hash_invitation_token(f"seed-{email}-{uuid4()}"),
        accepted_at=now if state == "accepted" else None,
        revoked_at=now if state == "revoked" else None,
    )
    session.add(inv)
    await session.flush()
    return inv


async def test_list_returns_only_pending(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    pending = await _seed_invitation(auth_schema, invited_by=admin.id, email="pending@example.com")
    await _seed_invitation(
        auth_schema, invited_by=admin.id, email="revoked@example.com", state="revoked"
    )
    await _seed_invitation(
        auth_schema, invited_by=admin.id, email="accepted@example.com", state="accepted"
    )

    resp = await async_client.get("/invitations", headers=_bearer(admin.id))

    assert resp.status_code == 200
    body = resp.json()
    assert [item["email"] for item in body] == ["pending@example.com"]
    assert body[0]["id"] == str(pending.id)


async def test_list_excludes_token_hash(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    inv = await _seed_invitation(auth_schema, invited_by=admin.id, email="pending@example.com")

    resp = await async_client.get("/invitations", headers=_bearer(admin.id))

    item = resp.json()[0]
    assert set(item) == {"id", "email", "invited_at", "expires_at", "invited_by"}
    assert "token_hash" not in item
    assert inv.token_hash not in resp.text


async def test_list_ordered_by_invited_at_desc(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    base = datetime.now(tz=UTC)
    await _seed_invitation(
        auth_schema,
        invited_by=admin.id,
        email="older@example.com",
        invited_at=base - timedelta(hours=2),
    )
    await _seed_invitation(
        auth_schema,
        invited_by=admin.id,
        email="newer@example.com",
        invited_at=base - timedelta(hours=1),
    )

    resp = await async_client.get("/invitations", headers=_bearer(admin.id))

    assert [item["email"] for item in resp.json()] == [
        "newer@example.com",
        "older@example.com",
    ]


async def test_list_empty_returns_200_empty(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)

    resp = await async_client.get("/invitations", headers=_bearer(admin.id))

    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_forbidden_for_member(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
) -> None:
    member = await bound_user_factory(email="member@example.com", role=UserRole.MEMBER)

    resp = await async_client.get("/invitations", headers=_bearer(member.id))

    assert resp.status_code == 403


async def test_list_unauthenticated_401(async_client: AsyncClient) -> None:
    resp = await async_client.get("/invitations")
    assert resp.status_code == 401


async def test_list_writes_no_audit(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    await _seed_invitation(auth_schema, invited_by=admin.id, email="pending@example.com")

    await async_client.get("/invitations", headers=_bearer(admin.id))

    assert await _audit_rows(auth_schema) == []


# ---------------------------------------------------------------------------
# POST /invitations/{id}/regenerate
# ---------------------------------------------------------------------------


async def test_regenerate_returns_new_token(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    headers = _bearer(admin.id)
    created = (
        await async_client.post(
            "/invitations", json={"email": "invite@example.com"}, headers=headers
        )
    ).json()
    invitation_id = UUID(created["id"])
    old_hash = (await _fetch_invitation(auth_schema, invitation_id)).token_hash
    original_invited_at = (await _fetch_invitation(auth_schema, invitation_id)).invited_at
    # Age the expiry so the reset is unambiguous (not a same-instant tie).
    await auth_schema.execute(
        update(Invitation)
        .where(Invitation.id == invitation_id)
        .values(expires_at=datetime.now(tz=UTC) - timedelta(days=1))
    )
    await auth_schema.flush()

    resp = await async_client.post(f"/invitations/{invitation_id}/regenerate", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["token"] != created["token"]
    inv = await _fetch_invitation(auth_schema, invitation_id)
    assert inv.token_hash == hash_invitation_token(body["token"])
    assert inv.token_hash != old_hash
    assert inv.expires_at > datetime.now(tz=UTC)  # reset to now + TTL
    assert inv.invited_at == original_invited_at  # immutable


async def test_regenerate_sets_no_store_headers(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    headers = _bearer(admin.id)
    created = (
        await async_client.post(
            "/invitations", json={"email": "invite@example.com"}, headers=headers
        )
    ).json()

    resp = await async_client.post(f"/invitations/{created['id']}/regenerate", headers=headers)

    assert resp.headers["cache-control"] == "no-store"
    assert resp.headers["pragma"] == "no-cache"


async def test_regenerate_unknown_id_404(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)

    resp = await async_client.post(f"/invitations/{uuid4()}/regenerate", headers=_bearer(admin.id))

    assert resp.status_code == 404


async def test_regenerate_on_accepted_returns_409(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    inv = await _seed_invitation(
        auth_schema, invited_by=admin.id, email="accepted@example.com", state="accepted"
    )

    resp = await async_client.post(f"/invitations/{inv.id}/regenerate", headers=_bearer(admin.id))

    assert resp.status_code == 409


async def test_regenerate_on_revoked_returns_409(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    inv = await _seed_invitation(
        auth_schema, invited_by=admin.id, email="revoked@example.com", state="revoked"
    )

    resp = await async_client.post(f"/invitations/{inv.id}/regenerate", headers=_bearer(admin.id))

    # D6: terminal states are 409, not 410 (410 is reserved for S04.5).
    assert resp.status_code == 409


async def test_regenerate_forbidden_for_member(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    member = await bound_user_factory(email="member@example.com", role=UserRole.MEMBER)
    inv = await _seed_invitation(auth_schema, invited_by=admin.id, email="pending@example.com")
    old_hash = inv.token_hash

    resp = await async_client.post(f"/invitations/{inv.id}/regenerate", headers=_bearer(member.id))

    assert resp.status_code == 403
    assert (await _fetch_invitation(auth_schema, inv.id)).token_hash == old_hash
    assert await _audit_rows(auth_schema) == []


async def test_regenerate_unauthenticated_401(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    inv = await _seed_invitation(auth_schema, invited_by=admin.id, email="pending@example.com")
    old_hash = inv.token_hash

    resp = await async_client.post(f"/invitations/{inv.id}/regenerate")

    assert resp.status_code == 401
    assert (await _fetch_invitation(auth_schema, inv.id)).token_hash == old_hash
    assert await _audit_rows(auth_schema) == []


async def test_regenerate_writes_audit_invite_regenerated(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    headers = _bearer(admin.id)
    created = (
        await async_client.post(
            "/invitations", json={"email": "invite@example.com"}, headers=headers
        )
    ).json()

    await async_client.post(f"/invitations/{created['id']}/regenerate", headers=headers)

    rows = await _audit_rows(auth_schema)
    # Exactly two rows total — the create's `invite_sent` plus this
    # regenerate's `invite_regenerated` — no parasitic extra audit.
    assert sorted(r.action for r in rows) == ["invite_regenerated", "invite_sent"]
    regenerated = [r for r in rows if r.action == "invite_regenerated"]
    assert len(regenerated) == 1
    assert regenerated[0].actor_user_id == admin.id
    assert regenerated[0].event_metadata == {
        "invitation_id": created["id"],
        "email": "invite@example.com",
    }


async def test_regenerate_audit_omits_raw_token(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    headers = _bearer(admin.id)
    created = (
        await async_client.post(
            "/invitations", json={"email": "invite@example.com"}, headers=headers
        )
    ).json()

    resp = await async_client.post(f"/invitations/{created['id']}/regenerate", headers=headers)
    raw = resp.json()["token"]

    for row in await _audit_rows(auth_schema):
        assert raw not in str(row.event_metadata)


# ---------------------------------------------------------------------------
# DELETE /invitations/{id}
# ---------------------------------------------------------------------------


async def test_revoke_sets_revoked_at_204(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    headers = _bearer(admin.id)
    created = (
        await async_client.post(
            "/invitations", json={"email": "invite@example.com"}, headers=headers
        )
    ).json()

    resp = await async_client.delete(f"/invitations/{created['id']}", headers=headers)

    assert resp.status_code == 204
    inv = await _fetch_invitation(auth_schema, UUID(created["id"]))
    assert inv.revoked_at is not None
    # Gone from the pending list.
    listed = (await async_client.get("/invitations", headers=headers)).json()
    assert created["id"] not in [item["id"] for item in listed]


async def test_revoke_unknown_id_404(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)

    resp = await async_client.delete(f"/invitations/{uuid4()}", headers=_bearer(admin.id))

    assert resp.status_code == 404


async def test_revoke_on_accepted_returns_409(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    inv = await _seed_invitation(
        auth_schema, invited_by=admin.id, email="accepted@example.com", state="accepted"
    )

    resp = await async_client.delete(f"/invitations/{inv.id}", headers=_bearer(admin.id))

    assert resp.status_code == 409


async def test_revoke_idempotent_on_already_revoked_204(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    headers = _bearer(admin.id)
    created = (
        await async_client.post(
            "/invitations", json={"email": "invite@example.com"}, headers=headers
        )
    ).json()

    first = await async_client.delete(f"/invitations/{created['id']}", headers=headers)
    assert first.status_code == 204
    revoked_at = (await _fetch_invitation(auth_schema, UUID(created["id"]))).revoked_at

    second = await async_client.delete(f"/invitations/{created['id']}", headers=headers)

    assert second.status_code == 204
    # The timestamp is unchanged — the re-revoke is a no-op on the row.
    assert (await _fetch_invitation(auth_schema, UUID(created["id"]))).revoked_at == revoked_at


async def test_revoke_forbidden_for_member(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    member = await bound_user_factory(email="member@example.com", role=UserRole.MEMBER)
    inv = await _seed_invitation(auth_schema, invited_by=admin.id, email="pending@example.com")

    resp = await async_client.delete(f"/invitations/{inv.id}", headers=_bearer(member.id))

    assert resp.status_code == 403
    assert (await _fetch_invitation(auth_schema, inv.id)).revoked_at is None
    assert await _audit_rows(auth_schema) == []


async def test_revoke_unauthenticated_401(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    inv = await _seed_invitation(auth_schema, invited_by=admin.id, email="pending@example.com")

    resp = await async_client.delete(f"/invitations/{inv.id}")

    assert resp.status_code == 401
    assert (await _fetch_invitation(auth_schema, inv.id)).revoked_at is None
    assert await _audit_rows(auth_schema) == []


async def test_revoke_writes_audit_invite_revoked(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    headers = _bearer(admin.id)
    created = (
        await async_client.post(
            "/invitations", json={"email": "invite@example.com"}, headers=headers
        )
    ).json()

    await async_client.delete(f"/invitations/{created['id']}", headers=headers)

    revoked = [r for r in await _audit_rows(auth_schema) if r.action == "invite_revoked"]
    assert len(revoked) == 1
    assert revoked[0].actor_user_id == admin.id
    assert revoked[0].event_metadata == {
        "invitation_id": created["id"],
        "email": "invite@example.com",
    }


async def test_double_revoke_writes_second_audit(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    bound_user_factory: UserMaker,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    headers = _bearer(admin.id)
    created = (
        await async_client.post(
            "/invitations", json={"email": "invite@example.com"}, headers=headers
        )
    ).json()

    await async_client.delete(f"/invitations/{created['id']}", headers=headers)
    await async_client.delete(f"/invitations/{created['id']}", headers=headers)

    # D9: every successful HTTP DELETE audits, including the idempotent
    # re-revoke — two identical INVITE_REVOKED rows.
    revoked = [r for r in await _audit_rows(auth_schema) if r.action == "invite_revoked"]
    assert len(revoked) == 2


# ---------------------------------------------------------------------------
# P04.4.3 — MVP transmission warning (raw token in logs, documented exception)
# ---------------------------------------------------------------------------

_HTTP_LOGGER = "backend.modules.auth.transports.http"


async def test_create_logs_invitation_link_warning(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)

    with caplog.at_level(logging.WARNING, logger=_HTTP_LOGGER):
        resp = await async_client.post(
            "/invitations", json={"email": "invite@example.com"}, headers=_bearer(admin.id)
        )

    body = resp.json()
    records = [
        r for r in caplog.records if r.name == _HTTP_LOGGER and r.msg == "invitation_link_issued"
    ]
    assert len(records) == 1
    fields = records[0].__dict__
    assert fields["email"] == "invite@example.com"
    # The MVP exception: the link (hence the raw token) is logged in clear.
    assert fields["accept_url"] == body["accept_url"]
    assert body["token"] in fields["accept_url"]


async def test_regenerate_logs_invitation_link_warning(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    headers = _bearer(admin.id)
    created = (
        await async_client.post(
            "/invitations", json={"email": "invite@example.com"}, headers=headers
        )
    ).json()

    # Drop the create's warning so only the regenerate's record remains.
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=_HTTP_LOGGER):
        resp = await async_client.post(f"/invitations/{created['id']}/regenerate", headers=headers)

    body = resp.json()
    records = [
        r for r in caplog.records if r.name == _HTTP_LOGGER and r.msg == "invitation_link_issued"
    ]
    assert len(records) == 1
    # The warning carries the *new* token.
    assert body["token"] in records[0].__dict__["accept_url"]
    assert created["token"] not in records[0].__dict__["accept_url"]


async def test_invitation_link_respects_base_url_override(
    async_client: AsyncClient,
    bound_user_factory: UserMaker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    admin = await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)
    # Override `get_settings` at the FastAPI dependency layer with a *copy*
    # carrying the new base URL — rather than mutating the shared cached
    # singleton (which would leak across tests and depends on lru_cache
    # state). `model_copy` keeps every other field (JWT secret, etc.) so the
    # auth chain still resolves.
    overridden = get_settings().model_copy(update={"app_base_url": "https://prosperity.example"})
    app.dependency_overrides[get_settings] = lambda: overridden
    try:
        with caplog.at_level(logging.WARNING, logger=_HTTP_LOGGER):
            resp = await async_client.post(
                "/invitations", json={"email": "invite@example.com"}, headers=_bearer(admin.id)
            )
    finally:
        app.dependency_overrides.pop(get_settings, None)

    body = resp.json()
    assert body["accept_url"].startswith("https://prosperity.example/accept-invite?token=")
    record = next(
        r for r in caplog.records if r.name == _HTTP_LOGGER and r.msg == "invitation_link_issued"
    )
    assert record.__dict__["accept_url"] == body["accept_url"]
