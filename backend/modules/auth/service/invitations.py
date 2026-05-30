"""Invitation lifecycle helpers (story S04.3, phase P04.3.3).

`create` / `regenerate` / `revoke` are the write paths over the
server-only `invitations` table (ADR 0010). The raw token is a 256-bit
URL-safe random string returned **once** on creation / regeneration; only
its sha256 hex digest is persisted, so a DB read alone can never resurrect
the link. The lookup/consumption path (`/accept-invite`) lands in S04.5
and will reuse `hash_invitation_token` from this same module.

Internal to the auth module — cross-module callers must go through
`backend.modules.auth.public`.

Transaction contract (D6) — these helpers `flush()` but never `commit()`:
the caller (the admin route in S04.4) owns the transaction boundary, so
the mutation and its audit row commit together. There is **no audit and
no authorization check here** (D6/D7): unlike `promote_to_admin` — which
writes a non-forgeable audit row and therefore must guard the actor
itself — an invitation write touches no audit table in S04.3. The route
S04.4 MUST carry `require_admin` and emit `log_admin_action(INVITE_*)` in
the same transaction, before commit. The FK `invited_by → users.id` is
the only integrity backstop here: an unknown `by_admin_id` surfaces as an
`IntegrityError` at flush.

Concurrency (D8/D9) — the conditional `UPDATE … RETURNING` of
`regenerate` / `revoke` is single-statement atomic, and `create`'s
uniqueness is the partial index (`uq_invitations_pending_email`). Unlike
`refresh_tokens.rotate` and `promote_to_admin`, these helpers deliberately
do **not** catch the `SerializationFailure` (SQLSTATE 40001) that a *true*
concurrent contention on the same row raises under REPEATABLE READ. The
omission is intentional, not an oversight:

  - Invitation mutations are rare, manual admin actions on a single id;
    genuine same-row contention is not a real-world workload (contrast
    refresh-token rotation, which fires on every client refresh).
  - There is **no security tombstone** that must survive a caller-side
    rollback (the reason `rotate` commits-inside-service), so a 500 on the
    losing transaction is acceptable signal — exactly the contract
    documented in `backend.shared.db.build_engine` ("callers that don't
    handle 40001 will see it bubble up to a 500 — deliberate signal").
  - Replicating `promote_to_admin`'s pattern would be *wrong* for
    `regenerate`: a concurrent regenerate leaves the row **pending**, so
    re-resolving the loser via `_raise_for_non_pending` would raise a
    misleading `InvitationNotPendingError` for a row that is still pending.
    Correct recovery would need retry logic disproportionate to the risk.

The exact-double-`create` race is still covered: the partial unique index
is the hard backstop (the loser takes an `IntegrityError`), pinned by
`test_invitations_constraint` and the service-level race test.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.models import Invitation

# ADR 0010 / glossary: an invitation is valid for 7 days. Exposed at module
# scope (acceptance criterion) so the route and tests share one source.
INVITATION_TTL = timedelta(days=7)

# 32 bytes = 256 bits → 43 url-safe chars. Same entropy as refresh tokens;
# wide enough that the UNIQUE(token_hash) index is belt-and-braces.
_TOKEN_ENTROPY_BYTES = 32


class InvitationError(Exception):
    """Base class for invitation-write failures.

    A bare `Exception` subclass (cf. D7 of #74): the auth module does not
    derive domain errors from `ValueError` / `LookupError`, so a caller can
    `except InvitationError` without swallowing unrelated stdlib exceptions.
    """


class InvitationNotFoundError(InvitationError):
    """The target `invitation_id` does not resolve to an `invitations` row."""


class DuplicatePendingInvitationError(InvitationError):
    """A pending invitation already exists for this email (D9 pre-check)."""


class InvitationNotPendingError(InvitationError):
    """The target invitation is terminal (accepted, or revoked) — not pending.

    Raised by `regenerate` / `revoke` when the conditional UPDATE matched no
    row because the invitation is no longer pending. `revoke` on an
    already-revoked row is the one exception: it is idempotent (a silent
    no-op), since re-revoking expresses the same intent.
    """


def hash_invitation_token(raw_token: str) -> str:
    """Return the sha256 hex digest (64 chars) of `raw_token`.

    sha256, not the HMAC `refresh_tokens.hash_refresh_token` uses: with 256
    bits of entropy an offline pre-image is infeasible and the keyed pepper
    buys little, while the glossary (CONTEXT.md) and the S04.3 acceptance
    criteria pin sha256. The raw token is never persisted; this digest is.
    Reused by `/accept-invite` (S04.5) to resolve a row by token.
    """
    return sha256(raw_token.encode("utf-8")).hexdigest()


async def create(session: AsyncSession, *, email: str, by_admin_id: UUID) -> str:
    """Create a pending invitation for `email` and return the raw token once.

    Does **not** commit (D6); authorization and the `INVITE_SENT` audit row
    are the route's responsibility (S04.4), in the same transaction.
    `by_admin_id` is validated only by the FK `invited_by` (an unknown id
    raises `IntegrityError` at flush — D7).

    Raises `DuplicatePendingInvitationError` when a pending invitation
    already exists for the (normalised) email. This pre-check gives a clean
    domain error on the common path; the partial unique index remains the
    hard backstop for a true concurrent double-create (the loser takes an
    `IntegrityError`).
    """
    normalized = email.strip().lower()
    existing = (
        await session.execute(
            select(Invitation.id).where(
                func.lower(Invitation.email) == normalized,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
            )
        )
    ).first()
    if existing is not None:
        raise DuplicatePendingInvitationError(
            f"a pending invitation already exists for {normalized}"
        )

    raw = secrets.token_urlsafe(_TOKEN_ENTROPY_BYTES)
    now = datetime.now(tz=UTC)
    session.add(
        Invitation(
            email=normalized,
            invited_by=by_admin_id,
            invited_at=now,
            expires_at=now + INVITATION_TTL,
            token_hash=hash_invitation_token(raw),
        )
    )
    await session.flush()
    return raw


async def regenerate(session: AsyncSession, invitation_id: UUID) -> str:
    """Rotate a pending invitation's token and return the new raw token once.

    Replaces `token_hash` and resets `expires_at = now + TTL` (a fresh
    7-day window for "the admin lost the link"); `invited_at` is immutable
    so the original-invite timestamp survives. The old link becomes
    unusable the moment this commits. Atomic conditional UPDATE (gabarit
    `promote_to_admin`); does not commit (D6).

    Raises `InvitationNotFoundError` (unknown id) or
    `InvitationNotPendingError` (accepted / revoked). See the module
    docstring for why a 40001 contention is left to bubble as a 500.
    """
    raw = secrets.token_urlsafe(_TOKEN_ENTROPY_BYTES)
    now = datetime.now(tz=UTC)
    row = (
        await session.execute(
            update(Invitation)
            .where(
                Invitation.id == invitation_id,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
            )
            .values(token_hash=hash_invitation_token(raw), expires_at=now + INVITATION_TTL)
            .returning(Invitation.id)
        )
    ).one_or_none()
    if row is None:
        await _raise_for_non_pending(session, invitation_id)
    await session.flush()
    return raw


async def revoke(session: AsyncSession, invitation_id: UUID) -> None:
    """Mark a pending invitation revoked (`revoked_at = now`).

    Atomic conditional UPDATE; does not commit (D6). Idempotent on the
    terminal `revoked` state — a no-op, no error, since re-revoking
    expresses the same intent (admin ergonomics). Raises
    `InvitationNotFoundError` (unknown id) or `InvitationNotPendingError`
    (already accepted).
    """
    now = datetime.now(tz=UTC)
    row = (
        await session.execute(
            update(Invitation)
            .where(
                Invitation.id == invitation_id,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
            )
            .values(revoked_at=now)
            .returning(Invitation.id)
        )
    ).one_or_none()
    if row is None:
        await _raise_for_non_pending(session, invitation_id, revoke_idempotent=True)
        return
    await session.flush()


async def _raise_for_non_pending(
    session: AsyncSession, invitation_id: UUID, *, revoke_idempotent: bool = False
) -> None:
    """Re-resolve a row the conditional UPDATE did not match, and raise.

    Called when `UPDATE … WHERE <pending>` matched no row. A secondary read
    distinguishes the outcomes:

      - no row → `InvitationNotFoundError`
      - revoked + `revoke_idempotent` → return (silent no-op for `revoke`)
      - otherwise (accepted, or revoked under `regenerate`) →
        `InvitationNotPendingError`
    """
    result = (
        await session.execute(
            select(Invitation.accepted_at, Invitation.revoked_at).where(
                Invitation.id == invitation_id
            )
        )
    ).one_or_none()
    if result is None:
        raise InvitationNotFoundError(f"invitation {invitation_id} does not exist")
    _accepted_at, revoked_at = result
    if revoked_at is not None and revoke_idempotent:
        return
    raise InvitationNotPendingError(f"invitation {invitation_id} is not pending")
