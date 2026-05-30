"""HTTP transport for the auth module (story S02.4).

Exposes `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`.
Internal to `modules.auth`: cross-module callers go through
`modules.auth.public` (no transport symbols are re-exported there).
"""

from __future__ import annotations

import logging
import secrets
from functools import cache
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings, get_settings
from backend.modules.auth.domain import AdminAction, UserRole
from backend.modules.auth.models import Invitation, User
from backend.modules.auth.schemas import (
    AcceptInvitePreviewResponse,
    AcceptInviteRequest,
    InvitationCreatedResponse,
    InvitationCreateRequest,
    InvitationResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenPair,
    sanitize_device_label,
)
from backend.modules.auth.service import invitations as invitation_service
from backend.modules.auth.service._password import password_hasher
from backend.modules.auth.service.audit import log_admin_action
from backend.modules.auth.service.invitations import (
    DuplicatePendingInvitationError,
    InvitationNotFoundError,
    InvitationNotPendingError,
    hash_invitation_token,
)
from backend.modules.auth.service.jwt import issue_access_token
from backend.modules.auth.service.refresh_tokens import (
    InvalidRefreshTokenError,
    hash_refresh_token,
)
from backend.modules.auth.service.refresh_tokens import issue as issue_refresh
from backend.modules.auth.service.refresh_tokens import revoke as revoke_refresh
from backend.modules.auth.service.refresh_tokens import rotate as rotate_refresh
from backend.modules.auth.service.users import create_user
from backend.modules.auth.transports.dependencies import require_admin
from backend.shared.db import get_db
from backend.shared.http import client_ip_for

logger = logging.getLogger(__name__)

# Applied on responses that carry tokens (`/auth/login`, `/auth/refresh`).
# Prevents intermediary proxies (CDN, ALB, corp-proxy) or
# `fetch({cache: 'force-cache'})` from caching the access/refresh pair
# (OWASP ASVS V8.3.4).
_NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@cache
def _dummy_hash() -> str:
    """Pre-computed Argon2id hash used to equalise verify timing.

    Calling `verify(<random>, _dummy_hash())` when the supplied email
    doesn't resolve to a user prevents timing-based account
    enumeration: an attacker can't distinguish "user unknown" from
    "user exists, password wrong" by measuring response latency.

    The pre-image is `secrets.token_urlsafe(32)` (computed once per
    process) rather than a fixed literal so an attacker who obtains
    this exact hash from a memory dump cannot fingerprint it as the
    "unknown user" sentinel — the value differs across processes.
    """
    return password_hasher().hash(secrets.token_urlsafe(32))


@router.post("/login", response_model=TokenPair, status_code=status.HTTP_200_OK)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenPair:
    """Authenticate by email + password; return an access + refresh pair.

    Case-insensitive on the email lookup (uses the functional
    `lower(email)` index on `users`). 401 is returned uniformly for
    unknown user, wrong password, and disabled account so the client
    cannot enumerate which case applies.
    """
    # TODO(S02.5): rate-limit by client IP / email.
    response.headers.update(_NO_STORE_HEADERS)

    user = (
        await session.execute(select(User).where(func.lower(User.email) == body.email.lower()))
    ).scalar_one_or_none()
    password = body.password.get_secret_value()
    client_ip = client_ip_for(request, settings)

    if user is None or user.disabled_at is not None:
        # Run verify() against the dummy hash so the disabled / unknown
        # case takes the same Argon2id wall-clock time as the wrong-
        # password case.
        password_hasher().verify("dummy", _dummy_hash())
        logger.warning(
            "login_failed",
            extra={"reason": "user_unknown_or_disabled", "client_ip": client_ip},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not password_hasher().verify(password, user.password_hash):
        logger.warning(
            "login_failed",
            extra={
                "reason": "bad_password",
                "user_id": str(user.id),
                "client_ip": client_ip,
            },
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    device_label = sanitize_device_label(request.headers.get("user-agent"))
    access = issue_access_token(user.id, settings=settings)
    refresh = await issue_refresh(session, user.id, settings=settings, device_label=device_label)
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenPair, status_code=status.HTTP_200_OK)
async def refresh(
    body: RefreshRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenPair:
    """Rotate a refresh token: revoke the presented one, issue a new pair.

    All refresh-token failure modes (unknown, expired, revoked) collapse
    to a single 401 with a generic body — the distinct exception types
    are preserved for server-side logs but never leak to the client.
    Replay of an already-revoked token triggers family-wide invalidation
    inside `rotate()` (see service docstring).
    """
    # TODO(S02.5): rate-limit by client IP / refresh-token hash prefix.
    response.headers.update(_NO_STORE_HEADERS)
    try:
        user_id, new_refresh = await rotate_refresh(session, body.refresh_token, settings=settings)
    except InvalidRefreshTokenError as exc:
        # Parent class catches Invalid + Expired + Revoked → uniform 401.
        logger.warning(
            "refresh_failed",
            extra={
                "reason": type(exc).__name__,
                "client_ip": client_ip_for(request, settings),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from exc

    access = issue_access_token(user_id, settings=settings)
    return TokenPair(access_token=access, refresh_token=new_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    """Revoke the refresh token. Idempotent: 204 regardless of state.

    Returning 204 even when the hash is unknown (already cleaned up,
    forged value, etc.) keeps the response shape uniform — no
    differential signal that would let a client probe for valid tokens.
    """
    # TODO(S02.5): rate-limit by client IP — currently anyone can spam
    # the route with guessed refresh tokens.
    token_hash = hash_refresh_token(body.refresh_token, settings=settings)
    await revoke_refresh(session, token_hash)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Invitation admin routes (S04.4) ----------------------------------------
#
# A dedicated top-level `/invitations` router (the roadmap lists
# `POST /invitations`, `GET /invitations`, … — not `/auth/invitations`).
# Co-located here in the auth transport because the handlers consume auth
# internals directly (`service.invitations`, `service.audit`, `models`,
# `domain`, `dependencies.require_admin`) — all intra-module imports, so no
# new import-linter exception is needed.
#
# Every handler is admin-only via `require_admin`: anonymous → 401 and
# member → 403 are already enforced upstream (S04.1) before the body runs.
# Each successful mutation writes an `admin_audit_logs` row through
# `log_admin_action` in the **same** transaction as the mutation (committed
# together by `get_db`), so a failed audit rolls back the mutation too.

invitations_router = APIRouter(prefix="/invitations", tags=["invitations"])

AdminDep = Annotated[User, Depends(require_admin)]

# Shared 409 body for "a pending invitation already exists" — emitted both
# by the service pre-check and the concurrent-race IntegrityError fallback.
_DUPLICATE_INVITATION_DETAIL = "A pending invitation already exists for this email."
# Shared 409 body for regenerate/revoke against a terminal (accepted /
# revoked) invitation.
_NOT_PENDING_DETAIL = "Invitation is no longer pending."


def _require_resolved(inv: Invitation | None) -> Invitation:
    """Narrow the post-mutation re-fetch to a non-None row.

    `regenerate`/`revoke` only return without raising `InvitationNotFoundError`
    when the row exists, so the immediate `session.get` in the same
    transaction must resolve it. An explicit guard (rather than `assert`,
    which `python -O` strips) keeps this invariant enforced in every build:
    a `None` here is a genuine server-side invariant breach → 500.
    """
    if inv is None:  # pragma: no cover - impossible after a successful mutation
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invitation vanished after a successful mutation.",
        )
    return inv


def _accept_invite_url(raw_token: str, settings: Settings) -> str:
    """Build the accept link handed to the invitee (consumed by S04.5).

    Base host is configurable via `APP_BASE_URL` (not a secret). The raw
    token only ever travels in the create/regenerate response body and the
    transmission warning log (P04.4.3) — it is never persisted or audited.
    """
    return f"{settings.app_base_url}/accept-invite?token={raw_token}"


def _log_invitation_link(email: str, accept_url: str) -> None:
    # TODO(notifications): replace this log with an email send via the
    # `notifications` module (V1). ASSUMED self-hosted MVP exception: the
    # raw token is logged in clear because there is NO automatic delivery
    # channel yet — the admin re-reads the backend logs to recover the link
    # to transmit out-of-band. This deliberately bypasses the general
    # "never log a raw token" rule (and the `log_admin_action` blacklist);
    # scope is strictly self-hosted V1, the primary channel remains the
    # single-use HTTP response (`_NO_STORE_HEADERS`). The risk (a single-use
    # secret exposed in logs) is documented in `runbooks/invitations.md`.
    #
    # WARNING level is deliberate: the operator must *notice* this line among
    # nominal INFO traffic to recover the link by hand (there is no other
    # channel). The flip side — WARNING typically fans out to alerting /
    # external aggregators — is a real exposure widening. While this log
    # exists, it MUST NOT be shipped to any external log aggregator: the raw
    # token is a single-use secret. This constraint is spelled out in
    # `runbooks/invitations.md` (§"Ne pas exporter ce log").
    # REMOVE this as soon as `notifications` exists.
    logger.warning(
        "invitation_link_issued",
        extra={"email": email, "accept_url": accept_url},
    )


@invitations_router.post(
    "",
    response_model=InvitationCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_invitation(
    body: InvitationCreateRequest,
    admin: AdminDep,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> InvitationCreatedResponse:
    """Create a pending invitation; return the raw token + accept link once.

    Admin-only. The raw token is returned **once** in the body (and logged
    once for manual transmission — see `_log_invitation_link`); only its
    sha256 digest is persisted. A pre-existing pending invitation for the
    same email is a 409 (both on the sequential pre-check and on the
    concurrent partial-index race), never a 500.
    """
    response.headers.update(_NO_STORE_HEADERS)  # ASVS V8.3.4 — raw token
    try:
        raw = await invitation_service.create(session, email=body.email, by_admin_id=admin.id)
    except DuplicatePendingInvitationError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_DUPLICATE_INVITATION_DETAIL) from exc
    except IntegrityError as exc:
        # Defence under the exact concurrent double-create: the partial
        # unique index rejects the loser with SQLSTATE 23505. Map it to the
        # same 409 as the pre-check; anything else is a real bug → re-raise.
        sqlstate = getattr(exc.orig, "sqlstate", None)
        if sqlstate == "23505":
            raise HTTPException(
                status.HTTP_409_CONFLICT, detail=_DUPLICATE_INVITATION_DETAIL
            ) from exc
        # Mirror `accounts.transports.http`: surface the offending SQLSTATE
        # before re-raising so an unexpected integrity error (→ 500) is
        # diagnosable instead of an opaque stack trace.
        logger.error("invitation_unexpected_integrity", extra={"sqlstate": sqlstate})
        raise

    # `create` returns only the raw token (frozen S04.3 contract). Re-resolve
    # the freshly-flushed row by its unique `token_hash` for the audit
    # metadata and the response `id`/`expires_at`.
    inv = (
        await session.execute(
            select(Invitation).where(Invitation.token_hash == hash_invitation_token(raw))
        )
    ).scalar_one()
    await log_admin_action(
        session,
        action=AdminAction.INVITE_SENT,
        by=admin.id,
        metadata={"invitation_id": str(inv.id), "email": inv.email},
    )
    accept_url = _accept_invite_url(raw, settings)
    _log_invitation_link(inv.email, accept_url)
    return InvitationCreatedResponse(
        id=inv.id,
        email=inv.email,
        expires_at=inv.expires_at,
        token=raw,
        accept_url=accept_url,
    )


@invitations_router.get("", response_model=list[InvitationResponse])
async def list_pending_invitations(
    admin: AdminDep,
    session: SessionDep,
) -> list[Invitation]:
    """List pending invitations (`accepted_at IS NULL AND revoked_at IS NULL`).

    Admin-only, newest first. Not audited (a read). `response_model`
    structurally excludes `token_hash` even though the ORM rows are returned
    whole.
    """
    rows = (
        (
            await session.execute(
                select(Invitation)
                .where(Invitation.accepted_at.is_(None), Invitation.revoked_at.is_(None))
                .order_by(Invitation.invited_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


@invitations_router.post(
    "/{invitation_id}/regenerate",
    response_model=InvitationCreatedResponse,
    status_code=status.HTTP_200_OK,
)
async def regenerate_invitation(
    invitation_id: UUID,
    admin: AdminDep,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> InvitationCreatedResponse:
    """Rotate a pending invitation's token; return the new raw token once.

    Admin-only. The old `/accept-invite?token=...` link stops working the
    moment this commits. Unknown id → 404; an accepted or revoked invitation
    → 409 (the 410 is reserved for the token-consumption endpoint in S04.5).
    """
    response.headers.update(_NO_STORE_HEADERS)  # ASVS V8.3.4 — raw token
    try:
        raw = await invitation_service.regenerate(session, invitation_id)
    except InvitationNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invitation not found.") from exc
    except InvitationNotPendingError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_NOT_PENDING_DETAIL) from exc

    inv = _require_resolved(await session.get(Invitation, invitation_id))
    await log_admin_action(
        session,
        action=AdminAction.INVITE_REGENERATED,
        by=admin.id,
        metadata={"invitation_id": str(invitation_id), "email": inv.email},
    )
    accept_url = _accept_invite_url(raw, settings)
    _log_invitation_link(inv.email, accept_url)
    return InvitationCreatedResponse(
        id=inv.id,
        email=inv.email,
        expires_at=inv.expires_at,
        token=raw,
        accept_url=accept_url,
    )


@invitations_router.delete("/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(
    invitation_id: UUID,
    admin: AdminDep,
    session: SessionDep,
) -> Response:
    """Revoke a pending invitation (`revoked_at = now`); 204, admin-only.

    The row stays in the DB (audit). Idempotent on an already-revoked
    invitation (the service is a silent no-op → still 204, and still audited
    — every successful HTTP action writes one row). Unknown id → 404; an
    accepted invitation → 409.
    """
    try:
        await invitation_service.revoke(session, invitation_id)
    except InvitationNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invitation not found.") from exc
    except InvitationNotPendingError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_NOT_PENDING_DETAIL) from exc

    inv = _require_resolved(await session.get(Invitation, invitation_id))
    await log_admin_action(
        session,
        action=AdminAction.INVITE_REVOKED,
        by=admin.id,
        metadata={"invitation_id": str(invitation_id), "email": inv.email},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Accept-invite flow (S04.5) — ANONYMOUS routes (the invitee is not logged in)
# ---------------------------------------------------------------------------
#
# Top-level `/accept-invite` router. Co-located here because both handlers
# consume only auth internals (`service.invitations`, `service.users`,
# `service.audit`, `service.jwt`, `domain`) — all intra-module imports, so
# no new import-linter exception is needed. Unlike `/setup` (placed in
# `accounts` because it touches `Household`), `/accept-invite` never reaches
# an `accounts` aggregate.

accept_invite_router = APIRouter(prefix="/accept-invite", tags=["accept-invite"])

# Uniform 410 body for **every** invalid case (unknown/expired/accepted/
# revoked) AND the race backstop (40001/23505). Never differentiated —
# "expired" vs "unknown", or a third status code, would be an enumeration
# oracle (anti-enumeration, ADR 0010). Defined once at module scope.
_GONE_DETAIL = "This invitation link is no longer valid."

# SQLSTATEs that mean "this token can no longer be claimed", mapped to the
# uniform 410 on POST (mirror of `accounts.transports.http._RACE_LOST_SQLSTATES`):
#   40001 serialization_failure — loser of a true concurrent claim under
#         REPEATABLE READ (raised as `DBAPIError`, not `IntegrityError`).
#   23505 unique_violation — the invitee's email is already a user
#         (`uq_users_email_lower`); "already a member" ⇒ "link no longer
#         valid" is semantically a 410, and collapsing it here (rather than
#         a distinct 409) removes an account-enumeration oracle on an
#         anonymous, un-rate-limited route (D11).
# Anything else under `DBAPIError` is an application bug → re-raise → 500.
_ACCEPT_RACE_LOST_SQLSTATES = frozenset({"40001", "23505"})


@accept_invite_router.get("", response_model=AcceptInvitePreviewResponse)
async def preview_invitation(
    response: Response,
    session: SessionDep,
    token: Annotated[str, Query(min_length=1, max_length=128)],
) -> AcceptInvitePreviewResponse:
    """Pre-check an invitation token; 200 + {email, expires_at}, else 410.

    Anonymous, read-only — does not consume the token. Every invalid case
    (unknown/expired/accepted/revoked) collapses to one uniform 410 so the
    response can never be used to enumerate which tokens exist (ADR 0010).
    """
    response.headers.update(_NO_STORE_HEADERS)
    inv = await invitation_service.resolve_pending(session, token)
    if inv is None:
        raise HTTPException(status.HTTP_410_GONE, detail=_GONE_DETAIL)
    return AcceptInvitePreviewResponse(email=inv.email, expires_at=inv.expires_at)


@accept_invite_router.post("", response_model=TokenPair, status_code=status.HTTP_200_OK)
async def accept_invitation(
    body: AcceptInviteRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenPair:
    """Accept an invitation: create the `member` invitee, auto-login a `TokenPair`.

    Anonymous. One transaction (D2): atomically claim the invitation →
    create the `member` user → audit `invite_accepted` (actor-less) → mint
    tokens. An invalid token (unknown/expired/accepted/revoked) ⇒ uniform
    410. A lost race (40001) or an email already enrolled (23505) ⇒ the
    **same** 410 via the `DBAPIError` backstop (mirror of `/setup`) — no
    third status code, no oracle (D5/D11). `get_db` rolls back the whole
    transaction on any exception (so a partial `accepted_at` is undone and
    the invitation reverts to pending). A body carrying `role`/`email` is
    ignored (anti-poisoning): the role is ALWAYS `member`, the email is
    ALWAYS the invitation's, and the `id` is generated server-side.
    """
    response.headers.update(_NO_STORE_HEADERS)  # ASVS V8.3.4 — tokens

    try:
        inv = await invitation_service.accept(session, body.token)
        if inv is None:
            raise HTTPException(status.HTTP_410_GONE, detail=_GONE_DETAIL)
        user = await create_user(
            session,
            email=inv.email,  # never from the body (anti-poisoning)
            password=body.password.get_secret_value(),
            display_name=body.display_name,
            role=UserRole.MEMBER,  # hardcoded — NEVER admin, never from the body
        )
        await log_admin_action(
            session,
            action=AdminAction.INVITE_ACCEPTED,
            by=None,  # self-service: no admin actor (D1)
            target=user.id,
            # No `email` here: it is redundant with the `target_email` column
            # that `log_admin_action(target=user.id)` already snapshots, and
            # storing it twice in an append-only trail would survive the
            # `ON DELETE SET NULL` erasure of `target_email` (PII minimisation).
            metadata={"invitation_id": str(inv.id)},
        )
    except DBAPIError as exc:
        # Race backstop (D5/D11), mirror of `/setup`: 40001 (loser of a true
        # claim race) or 23505 (`uq_users_email_lower`, email already
        # enrolled) ⇒ uniform 410. Any other SQLSTATE is an app bug →
        # re-raise (500). `get_db` rolls back → `accepted_at` undone.
        sqlstate = getattr(exc.orig, "sqlstate", None)
        client_ip = client_ip_for(request, settings)
        if sqlstate not in _ACCEPT_RACE_LOST_SQLSTATES:
            logger.error(
                "accept_invite_unexpected_integrity",
                extra={"sqlstate": sqlstate, "client_ip": client_ip},
            )
            raise
        logger.warning(
            "accept_invite_race_lost",
            extra={"sqlstate": sqlstate, "client_ip": client_ip},
        )
        raise HTTPException(status.HTTP_410_GONE, detail=_GONE_DETAIL) from exc

    device_label = sanitize_device_label(request.headers.get("user-agent"))
    access_token = issue_access_token(user.id, settings=settings)
    refresh_token = await issue_refresh(
        session, user.id, settings=settings, device_label=device_label
    )
    return TokenPair(access_token=access_token, refresh_token=refresh_token)
