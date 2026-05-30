"""Integration tests for the accept-invite routes (S04.5, P04.5.3/4).

Drives `GET /accept-invite` and `POST /accept-invite` over httpx against a
real Postgres. Covers:

- GET: 200 + {email, expires_at} when usable; uniform 410 for every
  invalid case (unknown/expired/accepted/revoked); no-store headers; no
  consumption; no audit;
- POST: creates a `member` (never admin, email from the invitation, id
  server-side), marks the invitation accepted, writes one actor-less
  `invite_accepted` audit row, and auto-logs in with a `TokenPair`;
- anti-poisoning (`role`/`email` in the body are ignored);
- uniform 410 for every invalid case + idempotency (second POST → 410);
- D11 email-already-user → uniform 410 with the claim rolled back
  (`committed_client`);
- a barrier-pinned concurrency race proving the loser's 410 came through
  the 40001 backstop (`committed_client`).

`async_client` and `auth_schema` share one connection/transaction (savepoint
isolation); the `committed_*` fixtures give real cross-session commits for
the rollback and race tests.
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.config import get_settings
from backend.modules.auth.domain import AdminAction, UserRole
from backend.modules.auth.models import AdminAuditLog, Invitation, RefreshToken, User
from backend.modules.auth.service import invitations as invitation_service
from backend.modules.auth.service.invitations import hash_invitation_token
from backend.modules.auth.service.jwt import verify_access_token

_settings = get_settings()

# Must stay byte-identical to `auth.transports.http._GONE_DETAIL`: the
# uniform-body assertions below are the anti-enumeration guarantee, so a
# drift here should fail the test rather than be papered over by importing
# the private constant.
_GONE_DETAIL = "This invitation link is no longer valid."

UserMaker = Callable[..., Awaitable[User]]


def _make_invitation(
    *,
    invited_by: User,
    email: str = "invitee@example.com",
    expires_in: timedelta = timedelta(days=7),
    accepted: bool = False,
    revoked: bool = False,
) -> tuple[Invitation, str]:
    """Build an (unpersisted) invitation plus its raw token.

    The S04.4 `_seed_invitation` helper hashes a throwaway string and never
    returns the raw token; the accept flow needs the raw value the client
    sends, so this keeps the pair together. Caller persists it (savepoint
    or committed) to suit the fixture.
    """
    now = datetime.now(tz=UTC)
    raw = secrets.token_urlsafe(32)
    inv = Invitation(
        email=email,
        invited_by=invited_by.id,
        invited_at=now,
        expires_at=now + expires_in,
        token_hash=hash_invitation_token(raw),
        accepted_at=now if accepted else None,
        revoked_at=now if revoked else None,
    )
    return inv, raw


async def _seed_invitation_token(
    session: AsyncSession, *, invited_by: User, **kwargs: object
) -> tuple[Invitation, str]:
    inv, raw = _make_invitation(invited_by=invited_by, **kwargs)  # type: ignore[arg-type]
    session.add(inv)
    await session.flush()
    return inv, raw


@pytest.fixture
async def admin(bound_user_factory: UserMaker) -> User:
    return await bound_user_factory(email="admin@example.com", role=UserRole.ADMIN)


# ---------------------------------------------------------------------------
# GET /accept-invite
# ---------------------------------------------------------------------------


async def test_get_valid_returns_email_and_expiry(
    async_client: AsyncClient, auth_schema: AsyncSession, admin: User
) -> None:
    inv, raw = await _seed_invitation_token(auth_schema, invited_by=admin)

    resp = await async_client.get("/accept-invite", params={"token": raw})

    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"email", "expires_at"}
    assert body["email"] == inv.email
    # The raw token is never echoed back.
    assert raw not in resp.text


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"expires_in": timedelta(days=-1)}, id="expired"),
        pytest.param({"accepted": True}, id="accepted"),
        pytest.param({"revoked": True}, id="revoked"),
    ],
)
async def test_get_invalid_token_410(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    admin: User,
    kwargs: dict[str, object],
) -> None:
    _, raw = await _seed_invitation_token(auth_schema, invited_by=admin, **kwargs)
    resp = await async_client.get("/accept-invite", params={"token": raw})
    assert resp.status_code == 410


async def test_get_unknown_token_410(async_client: AsyncClient, auth_schema: AsyncSession) -> None:
    resp = await async_client.get("/accept-invite", params={"token": "never-issued"})
    assert resp.status_code == 410


async def test_get_invalid_bodies_are_uniform(
    async_client: AsyncClient, auth_schema: AsyncSession, admin: User
) -> None:
    # All four invalidity cases must return the byte-identical 410 body —
    # never "expired" vs "unknown" (anti-enumeration, ADR 0010).
    _, expired = await _seed_invitation_token(
        auth_schema, invited_by=admin, email="a@example.com", expires_in=timedelta(days=-1)
    )
    _, accepted = await _seed_invitation_token(
        auth_schema, invited_by=admin, email="b@example.com", accepted=True
    )
    _, revoked = await _seed_invitation_token(
        auth_schema, invited_by=admin, email="c@example.com", revoked=True
    )
    bodies = []
    for tok in (expired, accepted, revoked, "never-issued"):
        resp = await async_client.get("/accept-invite", params={"token": tok})
        assert resp.status_code == 410
        bodies.append(resp.json())
    assert bodies == [{"detail": _GONE_DETAIL}] * 4


async def test_get_sets_no_store_headers(
    async_client: AsyncClient, auth_schema: AsyncSession, admin: User
) -> None:
    _, raw = await _seed_invitation_token(auth_schema, invited_by=admin)
    resp = await async_client.get("/accept-invite", params={"token": raw})
    assert resp.headers["cache-control"] == "no-store"
    assert resp.headers["pragma"] == "no-cache"


async def test_get_missing_token_422(async_client: AsyncClient, auth_schema: AsyncSession) -> None:
    assert (await async_client.get("/accept-invite")).status_code == 422
    assert (await async_client.get("/accept-invite", params={"token": ""})).status_code == 422


async def test_get_does_not_consume(
    async_client: AsyncClient, auth_schema: AsyncSession, admin: User
) -> None:
    inv, raw = await _seed_invitation_token(auth_schema, invited_by=admin)
    first = await async_client.get("/accept-invite", params={"token": raw})
    assert first.status_code == 200
    await auth_schema.refresh(inv)
    assert inv.accepted_at is None
    # A second GET still resolves — the read never consumed the token.
    assert (await async_client.get("/accept-invite", params={"token": raw})).status_code == 200


async def test_get_writes_no_audit(
    async_client: AsyncClient, auth_schema: AsyncSession, admin: User
) -> None:
    _, raw = await _seed_invitation_token(auth_schema, invited_by=admin)
    await async_client.get("/accept-invite", params={"token": raw})
    count = (
        await auth_schema.execute(select(func.count()).select_from(AdminAuditLog))
    ).scalar_one()
    assert count == 0


# ---------------------------------------------------------------------------
# POST /accept-invite — happy path & security
# ---------------------------------------------------------------------------


def _accept_body(token: str, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "token": token,
        "display_name": "Invitee",
        "password": "correct-horse-battery-staple",
    }
    base.update(overrides)
    return base


async def _fetch_user(session: AsyncSession, email: str) -> User:
    return (await session.execute(select(User).where(User.email == email))).scalar_one()


async def test_post_valid_creates_member_and_logs_in(
    async_client: AsyncClient, auth_schema: AsyncSession, admin: User
) -> None:
    inv, raw = await _seed_invitation_token(auth_schema, invited_by=admin)

    resp = await async_client.post("/accept-invite", json=_accept_body(raw))

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"access_token", "refresh_token", "token_type"}
    assert body["token_type"] == "bearer"

    user = await _fetch_user(auth_schema, "invitee@example.com")
    assert user.role == UserRole.MEMBER
    assert user.email == inv.email
    await auth_schema.refresh(inv)
    assert inv.accepted_at is not None


async def test_post_access_token_resolves_to_new_user(
    async_client: AsyncClient, auth_schema: AsyncSession, admin: User
) -> None:
    _, raw = await _seed_invitation_token(auth_schema, invited_by=admin)
    resp = await async_client.post("/accept-invite", json=_accept_body(raw))
    user = await _fetch_user(auth_schema, "invitee@example.com")

    assert verify_access_token(resp.json()["access_token"], settings=_settings) == user.id
    # The auto-login refresh token is persisted in the same transaction.
    refresh_count = (
        await auth_schema.execute(
            select(func.count()).select_from(RefreshToken).where(RefreshToken.user_id == user.id)
        )
    ).scalar_one()
    assert refresh_count == 1


async def test_post_role_is_member_never_admin(
    async_client: AsyncClient, auth_schema: AsyncSession, admin: User
) -> None:
    # `role: admin` in the body is silently ignored — the created user is a
    # member, the privilege-escalation path is closed by design.
    _, raw = await _seed_invitation_token(auth_schema, invited_by=admin)
    resp = await async_client.post("/accept-invite", json=_accept_body(raw, role="admin"))
    assert resp.status_code == 200
    user = await _fetch_user(auth_schema, "invitee@example.com")
    assert user.role == UserRole.MEMBER


async def test_post_email_from_invitation_not_body(
    async_client: AsyncClient, auth_schema: AsyncSession, admin: User
) -> None:
    # `email` in the body is ignored — the created user's email comes from
    # the invitation (anti-poisoning, ADR 0010).
    inv, raw = await _seed_invitation_token(auth_schema, invited_by=admin)
    resp = await async_client.post(
        "/accept-invite", json=_accept_body(raw, email="attacker@evil.com")
    )
    assert resp.status_code == 200
    # The attacker email never became a user; the invitation email did.
    assert (
        await auth_schema.execute(select(User).where(User.email == "attacker@evil.com"))
    ).scalar_one_or_none() is None
    user = await _fetch_user(auth_schema, inv.email)
    assert user.email == inv.email


async def test_post_email_case_normalised(
    async_client: AsyncClient, auth_schema: AsyncSession, admin: User
) -> None:
    # A mixed-case invitation email is stored lowercase; the created user's
    # email matches it, pinning `uq_users_email_lower`.
    inv, raw = await _seed_invitation_token(
        auth_schema, invited_by=admin, email="Alice@Example.com"
    )
    assert inv.email == "alice@example.com"
    resp = await async_client.post("/accept-invite", json=_accept_body(raw))
    assert resp.status_code == 200
    user = await _fetch_user(auth_schema, "alice@example.com")
    assert user.email == inv.email


async def test_post_id_generated_server_side(
    async_client: AsyncClient, auth_schema: AsyncSession, admin: User
) -> None:
    # No `id` field is accepted from the body; the user's id is a fresh
    # server-side uuid, not the attacker-supplied one.
    forged = "00000000-0000-0000-0000-000000000000"
    _, raw = await _seed_invitation_token(auth_schema, invited_by=admin)
    resp = await async_client.post("/accept-invite", json=_accept_body(raw, id=forged))
    assert resp.status_code == 200
    user = await _fetch_user(auth_schema, "invitee@example.com")
    assert str(user.id) != forged


async def test_post_audit_invite_accepted_actorless(
    async_client: AsyncClient, auth_schema: AsyncSession, admin: User
) -> None:
    inv, raw = await _seed_invitation_token(auth_schema, invited_by=admin)
    await async_client.post("/accept-invite", json=_accept_body(raw))
    user = await _fetch_user(auth_schema, "invitee@example.com")

    logs = (
        (
            await auth_schema.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == AdminAction.INVITE_ACCEPTED.value
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(logs) == 1
    log = logs[0]
    assert log.actor_user_id is None
    assert log.target_user_id == user.id
    # `email` is intentionally NOT in metadata (PII minimisation): it is
    # snapshotted once in the `target_email` column and would otherwise
    # survive its `ON DELETE SET NULL` erasure in the append-only trail.
    assert log.event_metadata == {"invitation_id": str(inv.id)}
    assert log.target_email == inv.email


async def test_post_audit_metadata_omits_raw_token(
    async_client: AsyncClient, auth_schema: AsyncSession, admin: User
) -> None:
    _, raw = await _seed_invitation_token(auth_schema, invited_by=admin)
    await async_client.post("/accept-invite", json=_accept_body(raw))
    log = (
        await auth_schema.execute(
            select(AdminAuditLog).where(AdminAuditLog.action == AdminAction.INVITE_ACCEPTED.value)
        )
    ).scalar_one()
    assert raw not in str(log.event_metadata)


async def test_post_sets_no_store_headers(
    async_client: AsyncClient, auth_schema: AsyncSession, admin: User
) -> None:
    _, raw = await _seed_invitation_token(auth_schema, invited_by=admin)
    resp = await async_client.post("/accept-invite", json=_accept_body(raw))
    assert resp.headers["cache-control"] == "no-store"
    assert resp.headers["pragma"] == "no-cache"


async def test_post_anonymous_succeeds(
    async_client: AsyncClient, auth_schema: AsyncSession, admin: User
) -> None:
    # No Authorization header required — the route is anonymous.
    _, raw = await _seed_invitation_token(auth_schema, invited_by=admin)
    resp = await async_client.post("/accept-invite", json=_accept_body(raw))
    assert resp.status_code == 200
    assert "authorization" not in {k.lower() for k in resp.request.headers}


# ---------------------------------------------------------------------------
# POST /accept-invite — invalidity, idempotence, uniformity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"expires_in": timedelta(days=-1)}, id="expired"),
        pytest.param({"accepted": True}, id="accepted"),
        pytest.param({"revoked": True}, id="revoked"),
    ],
)
async def test_post_invalid_token_410_no_side_effects(
    async_client: AsyncClient,
    auth_schema: AsyncSession,
    admin: User,
    kwargs: dict[str, object],
) -> None:
    _, raw = await _seed_invitation_token(auth_schema, invited_by=admin, **kwargs)
    resp = await async_client.post("/accept-invite", json=_accept_body(raw))
    assert resp.status_code == 410
    # No user created, no audit row written.
    user_count = (
        await auth_schema.execute(
            select(func.count()).select_from(User).where(User.email == "invitee@example.com")
        )
    ).scalar_one()
    assert user_count == 0
    audit_count = (
        await auth_schema.execute(select(func.count()).select_from(AdminAuditLog))
    ).scalar_one()
    assert audit_count == 0


async def test_post_unknown_token_410(async_client: AsyncClient, auth_schema: AsyncSession) -> None:
    resp = await async_client.post("/accept-invite", json=_accept_body("never-issued"))
    assert resp.status_code == 410


async def test_post_invalid_bodies_are_uniform(
    async_client: AsyncClient, auth_schema: AsyncSession, admin: User
) -> None:
    _, expired = await _seed_invitation_token(
        auth_schema, invited_by=admin, email="a@example.com", expires_in=timedelta(days=-1)
    )
    _, accepted = await _seed_invitation_token(
        auth_schema, invited_by=admin, email="b@example.com", accepted=True
    )
    _, revoked = await _seed_invitation_token(
        auth_schema, invited_by=admin, email="c@example.com", revoked=True
    )
    bodies = []
    for tok in (expired, accepted, revoked, "never-issued"):
        resp = await async_client.post("/accept-invite", json=_accept_body(tok))
        assert resp.status_code == 410
        bodies.append(resp.json())
    assert bodies == [{"detail": _GONE_DETAIL}] * 4


async def test_post_twice_same_token(
    async_client: AsyncClient, auth_schema: AsyncSession, admin: User
) -> None:
    # First accept wins (200 + TokenPair); the second sees the invitation
    # already accepted → 410.
    _, raw = await _seed_invitation_token(auth_schema, invited_by=admin)
    first = await async_client.post("/accept-invite", json=_accept_body(raw))
    assert first.status_code == 200
    second = await async_client.post("/accept-invite", json=_accept_body(raw))
    assert second.status_code == 410


class _FakeCheckViolation(Exception):
    # asyncpg exposes the SQLSTATE as `.sqlstate` (not `.pgcode`). 23514 is
    # a check-violation — outside the race-lost set, so the route must NOT
    # mask it as 410.
    sqlstate = "23514"


async def test_post_unexpected_integrity_is_not_masked(
    async_client: AsyncClient, auth_schema: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A non-race SQLSTATE under DBAPIError is an app bug → it must re-raise
    # (surface as 500), never be collapsed to the uniform 410. Mirror of
    # `test_create_non_unique_integrityerror_is_not_masked` (S04.4).
    async def _raise_check(*_args: object, **_kwargs: object) -> Invitation:
        raise IntegrityError("UPDATE", {}, _FakeCheckViolation())

    monkeypatch.setattr(invitation_service, "accept", _raise_check)

    with pytest.raises(IntegrityError):
        await async_client.post("/accept-invite", json=_accept_body("a-token"))


# ---------------------------------------------------------------------------
# POST /accept-invite — Pydantic validation (no DB needed)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"password": "x" * 11}, id="password-too-short"),
        pytest.param({"password": "x" * 129}, id="password-too-long"),
        pytest.param({"display_name": ""}, id="display-name-empty"),
        pytest.param({"token": "x" * 129}, id="token-too-long"),
    ],
)
async def test_post_invalid_body_422(
    async_client: AsyncClient, auth_schema: AsyncSession, overrides: dict[str, object]
) -> None:
    body = _accept_body("a-token")
    body.update(overrides)
    resp = await async_client.post("/accept-invite", json=body)
    assert resp.status_code == 422


async def test_post_missing_token_422(async_client: AsyncClient, auth_schema: AsyncSession) -> None:
    resp = await async_client.post(
        "/accept-invite", json={"display_name": "Invitee", "password": "x" * 12}
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /accept-invite — D11 (email already a user) & real concurrency race
# ---------------------------------------------------------------------------


async def _seed_committed_admin(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> User:
    async with sessionmaker() as session:
        admin = User(
            email="admin@example.com",
            password_hash="$dummy$placeholder$hash",
            display_name="Admin",
            role=UserRole.ADMIN,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        return admin


@pytest.mark.usefixtures("_clean_committed_db")
async def test_post_email_already_user_410_rolls_back_claim(
    committed_client: AsyncClient,
    committed_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    # D11: the invitee's email is already a user. `create_user` hits
    # `uq_users_email_lower` (SQLSTATE 23505) → uniform 410, and `get_db`
    # rolls back the whole transaction so the claim (`accepted_at`) is
    # undone and the invitation reverts to pending. Run under
    # `committed_client` so the rollback is real (savepoint mode would pass
    # the assertion trivially).
    admin = await _seed_committed_admin(committed_sessionmaker)
    inv, raw = _make_invitation(invited_by=admin, email="taken@example.com")
    async with committed_sessionmaker() as session:
        existing = User(
            email="taken@example.com",
            password_hash="$dummy$placeholder$hash",
            display_name="Existing",
            role=UserRole.MEMBER,
        )
        session.add(existing)
        session.add(inv)
        await session.commit()
        inv_id = inv.id

    resp = await committed_client.post("/accept-invite", json=_accept_body(raw))
    assert resp.status_code == 410
    assert resp.json() == {"detail": _GONE_DETAIL}

    async with committed_sessionmaker() as session:
        reread = (
            await session.execute(select(Invitation).where(Invitation.id == inv_id))
        ).scalar_one()
        # The claim was rolled back — the invitation is pending again.
        assert reread.accepted_at is None
        # Exactly one user with that email (the pre-existing one), no new one.
        user_count = (
            await session.execute(
                select(func.count()).select_from(User).where(User.email == "taken@example.com")
            )
        ).scalar_one()
        assert user_count == 1
        audit_count = (
            await session.execute(select(func.count()).select_from(AdminAuditLog))
        ).scalar_one()
        assert audit_count == 0


@pytest.mark.usefixtures("_clean_committed_db")
async def test_post_concurrent_same_token_one_wins(
    committed_client: AsyncClient,
    committed_sessionmaker: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Two simultaneous POSTs of the same token. A barrier on `accept`
    # releases both racers into their `UPDATE` in the same window, forcing
    # the loser onto the SerializationFailure (40001) arm of the backstop —
    # not the sequential window (which the naive `gather` cannot pin, cf.
    # `test_setup_race`). Asserts: exactly one 200 + one 410, one user, one
    # audit row, and a `race_lost` log with sqlstate 40001 proving the 410
    # came through the 40001 branch.
    admin = await _seed_committed_admin(committed_sessionmaker)
    inv, raw = _make_invitation(invited_by=admin, email="racer@example.com")
    async with committed_sessionmaker() as session:
        session.add(inv)
        await session.commit()

    barrier = asyncio.Barrier(2)
    real_accept = invitation_service.accept

    async def _coordinated_accept(
        session: AsyncSession, raw_token: str, **kwargs: object
    ) -> object:
        # Both racers reach the UPDATE in the same window so neither sees
        # the other's committed claim — forcing the 40001 arm.
        await barrier.wait()
        return await real_accept(session, raw_token, **kwargs)  # type: ignore[arg-type]

    with (
        patch(
            "backend.modules.auth.transports.http.invitation_service.accept",
            side_effect=_coordinated_accept,
        ),
        caplog.at_level("WARNING", logger="backend.modules.auth.transports.http"),
    ):
        responses = await asyncio.wait_for(
            asyncio.gather(
                committed_client.post("/accept-invite", json=_accept_body(raw)),
                committed_client.post("/accept-invite", json=_accept_body(raw)),
            ),
            timeout=15.0,
        )

    statuses = sorted(r.status_code for r in responses)
    assert statuses == [200, 410], (
        f"unexpected race outcome: {statuses}; bodies: {[r.text for r in responses]}"
    )

    # The 410 came via the 40001 backstop, not the sequential window.
    race_lost = [
        r
        for r in caplog.records
        if r.message == "accept_invite_race_lost" and getattr(r, "sqlstate", None) == "40001"
    ]
    assert len(race_lost) == 1, (
        f"expected one 40001 race_lost log, got: "
        f"{[(r.message, getattr(r, 'sqlstate', None)) for r in caplog.records]}"
    )

    # Exactly one member created and one audit row.
    async with committed_sessionmaker() as session:
        member_count = (
            await session.execute(
                select(func.count()).select_from(User).where(User.email == "racer@example.com")
            )
        ).scalar_one()
        audit_count = (
            await session.execute(select(func.count()).select_from(AdminAuditLog))
        ).scalar_one()
    assert member_count == 1
    assert audit_count == 1
