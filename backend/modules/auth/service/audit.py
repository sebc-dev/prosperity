"""Admin audit logging helper (S04.2, P04.2.2).

`log_admin_action` is the single write path into the append-only,
server-only `admin_audit_logs` table. It is the socle for every
privileged action across E04 (invitations, promotions) and beyond
(E05+: user disable, TOTP reset via DB) — the callers themselves land
in #79 and S04.3/4/5; this story ships only the primitive.

Like `create_user`, it **does not commit** — it `flush()`es to surface
the `id` and any FK/NOT-NULL violation at the call site, and leaves the
commit to the caller so the admin action and its audit row stay atomic
in one transaction.

Internal to the auth module — cross-module callers must import via
`backend.modules.auth.public`.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.domain import AdminAction
from backend.modules.auth.models import AdminAuditLog, User


async def log_admin_action(
    session: AsyncSession,
    *,
    action: AdminAction,
    by: uuid.UUID,
    target: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> AdminAuditLog:
    """Append one `AdminAuditLog` row and return it (with its `id`).

    Does **not** commit. `session.flush()` is called so the FK on `by`
    (and any NOT NULL violation) surfaces as `IntegrityError` here rather
    than at the outer commit, and so the generated `id` is available on
    return. The caller owns the transaction: the admin action and its
    audit row must commit together.

    `action` is coerced through `AdminAction(action)` so a string outside
    the catalogue is rejected at runtime (the type hint alone is not
    enforced) — keeping the `text` column and the Python enum in lockstep.

    Non-repudiation is captured *here*, not by the caller: the helper
    reads the actor (and target, if any) and snapshots an immutable copy
    of their identity (`actor_email`, `actor_label`, `target_email`) into
    the row. Because `ON DELETE SET NULL` later nulls the FKs when an
    account is deleted, this snapshot is the only thing that keeps the
    trail meaningful — so it must not depend on each caller remembering to
    pass it (see `AdminAuditLog` docstring). An unknown `by` finds no
    actor and the FK then raises `IntegrityError` at the flush below.

    **Never log secrets in `metadata`.** The column is free-form JSONB by
    design, but callers MUST NOT store passwords or hashes, invitation
    tokens, TOTP/recovery secrets, or JWT/refresh tokens. Prefer
    identifiers (`invitation_id`, `target_user_id`) over sensitive values.
    This is critical for `TWOFA_RESET_VIA_DB` (ADR 0013).
    """
    actor = await session.get(User, by)
    target_user = await session.get(User, target) if target is not None else None
    record = AdminAuditLog(
        action=AdminAction(action),
        actor_user_id=by,
        actor_email=actor.email if actor is not None else None,
        # `UserRole` is a `StrEnum`, so it formats to its bare value
        # ("admin"/"member") here whether the attribute holds the enum
        # member or the equivalent raw string the ORM has not yet coerced.
        actor_label=f"{actor.email} ({actor.role})" if actor is not None else None,
        target_user_id=target,
        target_email=target_user.email if target_user is not None else None,
        event_metadata=metadata,
    )
    session.add(record)
    await session.flush()
    return record
