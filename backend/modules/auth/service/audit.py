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


class UnknownAuditUserError(Exception):
    """`by` (or a non-null `target`) does not resolve to a `users` row.

    Raised by `log_admin_action` *before* the flush so a privileged action
    can never be recorded against an unresolved identity. The FK would also
    reject the row, but only at flush time, as an opaque `IntegrityError`,
    and — for `by` — only because the snapshot columns would already be
    blank: a defence-in-depth check above the FK keeps a half-anonymous
    audit row from ever being built.
    """


class ForbiddenAuditMetadataError(Exception):
    """`metadata` carries a key whose name signals a secret/credential.

    The audit trail must never store passwords/hashes, invitation or
    refresh/JWT tokens, or TOTP/recovery secrets (see `log_admin_action`).
    This is enforced at the single write path rather than left to caller
    discipline — a guard-rail, not a guarantee (it matches by key name, so
    it stops accidental leakage, not a caller who mislabels the key).
    """


# Case-insensitive substring blacklist for `metadata` keys. Substrings (not
# exact names) so `password_hash`, `totp_secret`, `refresh_token`,
# `invitation_token`, `recovery_code`... are all caught.
_FORBIDDEN_METADATA_KEY_SUBSTRINGS = (
    "password",
    "passwd",
    "secret",
    "token",
    "hash",
    "otp",  # also covers `totp`
    "recovery",
    "jwt",
    "bearer",
    "credential",
)


def _reject_secret_metadata_keys(metadata: dict[str, Any] | None) -> None:
    """Raise `ForbiddenAuditMetadataError` if any key looks like a secret.

    Walks nested dicts and lists so a secret buried in
    `{"ctx": {"refresh_token": ...}}` is caught too.
    """
    if metadata is None:
        return
    stack: list[Any] = [metadata]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                # `str(...)` guards against non-string keys (JSONB requires
                # string keys, but a caller dict may not) — a clear rejection
                # beats an opaque AttributeError on `.lower()`.
                lowered = str(key).lower()
                if any(needle in lowered for needle in _FORBIDDEN_METADATA_KEY_SUBSTRINGS):
                    raise ForbiddenAuditMetadataError(
                        f"metadata key {key!r} looks like a secret and must not be "
                        "stored in the audit trail"
                    )
                stack.append(value)
        elif isinstance(current, list):
            stack.extend(current)


async def log_admin_action(
    session: AsyncSession,
    *,
    action: AdminAction,
    by: uuid.UUID,
    target: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> AdminAuditLog:
    """Append one `AdminAuditLog` row and return it (with its `id`).

    Does **not** commit. `session.flush()` is called so the generated
    `id` is available on return; the caller owns the transaction so the
    admin action and its audit row commit together. The FKs on `by` and
    `target` remain as a final backstop, but an unresolved identity is
    already rejected before the flush (see below), so it never surfaces
    here as an opaque `IntegrityError`.

    `action` is coerced through `AdminAction(action)` so a string outside
    the catalogue is rejected at runtime (the type hint alone is not
    enforced) — keeping the `text` column and the Python enum in lockstep.

    Non-repudiation is captured *here*, not by the caller: the helper
    reads the actor (and target, if any) and snapshots an immutable copy
    of their identity (`actor_email`, `actor_label`, `target_email`) into
    the row. Because `ON DELETE SET NULL` later nulls the FKs when an
    account is deleted, this snapshot is the only thing that keeps the
    trail meaningful — so it must not depend on each caller remembering to
    pass it (see `AdminAuditLog` docstring). An unresolved `by` (or a
    non-null `target` that resolves to nothing) raises
    `UnknownAuditUserError` *before* the flush, so a log can never be born
    against an unknown identity (defence in depth above the FK).

    **Never log secrets in `metadata`.** The column is free-form JSONB by
    design, but callers MUST NOT store passwords or hashes, invitation
    tokens, TOTP/recovery secrets, or JWT/refresh tokens. Prefer
    identifiers (`invitation_id`, `target_user_id`) over sensitive values.
    This is critical for `TWOFA_RESET_VIA_DB` (ADR 0013). A key-name
    blacklist rejects the obvious offenders with `ForbiddenAuditMetadataError`,
    but it is a guard-rail, not a substitute for caller discipline.
    """
    # Coerce first: an out-of-catalogue string is a caller bug, reject it
    # before touching the DB. `metadata` is screened next so a secret never
    # reaches the row even in memory.
    action = AdminAction(action)
    _reject_secret_metadata_keys(metadata)

    actor = await session.get(User, by)
    if actor is None:
        raise UnknownAuditUserError(f"audit actor {by} does not exist")
    target_user = await session.get(User, target) if target is not None else None
    if target is not None and target_user is None:
        raise UnknownAuditUserError(f"audit target {target} does not exist")

    record = AdminAuditLog(
        action=action,
        actor_user_id=by,
        actor_email=actor.email,
        # `UserRole` is a `StrEnum`, so it formats to its bare value
        # ("admin"/"member") here whether the attribute holds the enum
        # member or the equivalent raw string the ORM has not yet coerced.
        actor_label=f"{actor.email} ({actor.role})",
        target_user_id=target,
        target_email=target_user.email if target_user is not None else None,
        event_metadata=metadata,
    )
    session.add(record)
    await session.flush()
    return record
