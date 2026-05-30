"""Role-transition helpers (story S04.1, phase P04.1.3).

`promote_to_admin` is the single write path that lifts a `member` to
`admin` and records the privileged action in the same transaction via
`log_admin_action` (S04.2). It mirrors `refresh_tokens.rotate()`: a
conditional `UPDATE … RETURNING` is the atomicity primitive, and a
`SerializationFailure` (SQLSTATE 40001) under REPEATABLE READ is the
concurrent-loser signal.

Internal to the auth module — cross-module callers must import via
`backend.modules.auth.public`.

Transport contract (the future admin route, E04): `promote_to_admin`
**does not commit** (D8) — the promotion and its audit row share one
transaction whose commit the caller owns. The route MUST
`session.commit()` immediately after a successful call, with no
intervening logic that could raise: if anything between this service and
the commit throws, `get_db`'s exception handler rolls the transaction
back and *neither* the promotion *nor* its audit row persist. That
all-or-nothing behaviour is intentional, but it means the commit must
follow the call directly.
"""

from __future__ import annotations

from typing import NoReturn, cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.engine.cursor import CursorResult
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.domain import AdminAction, UserRole
from backend.modules.auth.models import User
from backend.modules.auth.service.audit import log_admin_action


class RoleError(Exception):
    """Base class for role-transition failures.

    Deliberately a bare `Exception` subclass — the auth module does not
    inherit from `ValueError` / `LookupError` for domain errors (cf. D7
    of #74), so a caller can `except RoleError` without also swallowing
    unrelated stdlib exceptions.
    """


class UserNotFoundError(RoleError):
    """The target `user_id` does not resolve to a `users` row."""


class AlreadyAdminError(RoleError):
    """The target user already holds the `admin` role — nothing to do.

    Also the result of an admin promoting themselves
    (`by_admin_id == user_id`): the actor guard passes (they are an active
    admin), the conditional `UPDATE … WHERE role='member'` matches no row,
    and the re-resolution lands here. No audit row is written.
    """


class NotAuthorizedError(RoleError):
    """`by_admin_id` is not an active admin, so it may not promote anyone.

    Raised *before* any mutation or audit write so a non-admin (or an
    unknown / disabled actor) can never forge an audit row — the audit
    trail is non-forgeable by construction, not by the caller's diligence.
    """


async def promote_to_admin(
    session: AsyncSession,
    *,
    user_id: UUID,
    by_admin_id: UUID,
) -> User:
    """Transition `user_id` from `member` to `admin` and audit it atomically.

    Returns the promoted `User` (with `role == ADMIN`). The promotion and
    its `user_promoted` audit row are written in the **same** transaction;
    this helper does **not** commit (D8) — see the module docstring for
    the transport's commit responsibility.

    Raises:
        NotAuthorizedError: `by_admin_id` is unknown, not an `admin`, or
            disabled (`disabled_at` set). Checked first, before any
            mutation or audit write, so a non-admin cannot forge a log.
        UserNotFoundError: `user_id` resolves to no `users` row.
        AlreadyAdminError: `user_id` is already an `admin` (including the
            self-promotion case `by_admin_id == user_id`).

    Concurrency: the conditional `UPDATE … RETURNING` is single-statement
    atomic under REPEATABLE READ (cf. `backend.shared.db`). Two concurrent
    promotions of the same member converge to exactly one success and one
    `AlreadyAdminError` — exactly one audit row — via two paths:
      - Sequential (loser's snapshot already sees `role='admin'`): the
        UPDATE matches zero rows and re-resolution raises `AlreadyAdminError`.
      - True race (both UPDATEs in flight): Postgres aborts the loser with
        `SerializationFailure` (SQLSTATE 40001) once the winner commits.
        Caught here, the aborted transaction is rolled back and the target
        is re-resolved against a fresh snapshot.

    Note: after the 40001 rollback the session's transaction is cleared —
    this function only re-resolves (a read) and raises afterwards, never
    writes, so it is safe; a future edit must not add a write past that
    rollback without opening a new transaction.

    A disabled target (`disabled_at` set) is **not** rejected here: the
    conditional UPDATE filters on `role='member'` only. Promotion concerns
    the role; whether a disabled account should be actionable is the
    route's policy, not this primitive's.
    """
    # 1 — Actor guard (D11). Load the actor and require an *active admin*.
    # `log_admin_action` only checks that `by` exists, not its role/state,
    # so this guard is what keeps the audit trail non-forgeable. It runs
    # before any mutation or audit write.
    # NOTE: if `User` gains further liveness fields (e.g. `locked_until`,
    # `suspended_at`), extend this guard so a frozen admin cannot promote.
    actor = await session.get(User, by_admin_id)
    if actor is None or actor.role != UserRole.ADMIN or actor.disabled_at is not None:
        raise NotAuthorizedError(f"actor {by_admin_id} is not an active admin")

    # 2 — Conditional atomic UPDATE (D12), modelled on `refresh_tokens.rotate()`.
    # `WHERE role='member'` means a matched row was provably a member, so
    # `old_role='member'` is exact without a separate read (D13).
    try:
        update_result = cast(
            "CursorResult[tuple[UUID]]",
            await session.execute(
                update(User)
                .where(User.id == user_id, User.role == UserRole.MEMBER)
                .values(role=UserRole.ADMIN)
                .returning(User.id)
            ),
        )
        row = update_result.one_or_none()
    except DBAPIError as exc:
        # SQLSTATE 40001 = serialization_failure: we lost a true concurrent
        # promotion. Postgres aborted this transaction — clear it and
        # re-resolve against a fresh snapshot (the winner has committed
        # `role='admin'`). Any other DBAPIError is a real fault: re-raise.
        if getattr(exc.orig, "sqlstate", None) != "40001":
            raise
        await session.rollback()
        await _raise_for_unpromotable(session, user_id)

    if row is None:
        # The conditional UPDATE matched nothing: the target is either
        # unknown or already an admin. No row was mutated and no audit row
        # is written in either case.
        await _raise_for_unpromotable(session, user_id)

    # 3 — Audit in the same transaction (D7). `target=user_id`,
    # `by=by_admin_id`; the helper snapshots the actor/target identity. No
    # secret keys in `metadata` (S04.2 blacklist).
    await log_admin_action(
        session,
        action=AdminAction.USER_PROMOTED,
        by=by_admin_id,
        target=user_id,
        metadata={"old_role": UserRole.MEMBER.value, "new_role": UserRole.ADMIN.value},
    )

    # 4 — Return the promoted user (D8: no commit). `session.get` may hit a
    # stale identity-map snapshot if the caller pre-loaded this row in the
    # same session (the Core UPDATE bypasses the ORM): `refresh` reloads it
    # so `role == ADMIN` reflects the in-transaction UPDATE, not the prior
    # member snapshot.
    promoted = await session.get(User, user_id)
    if promoted is None:
        # The UPDATE matched this id moments ago in the same transaction;
        # a vanished row is a broken invariant, not a domain outcome. Not
        # an `assert` — `python -O` would strip it from a security path.
        raise RuntimeError(f"invariant violated: user {user_id} vanished after a matched UPDATE")
    await session.refresh(promoted)
    return promoted


async def _raise_for_unpromotable(session: AsyncSession, user_id: UUID) -> NoReturn:
    """Re-resolve a target the conditional UPDATE did not promote, and raise.

    Called when the `UPDATE … WHERE role='member'` matched no row (either
    the sequential `rowcount=0` path or the post-40001-rollback path). A
    secondary read distinguishes the two domain outcomes:

      - no row → `UserNotFoundError`
      - row present → it must hold `role='admin'` (the only other role a
        non-matching row can have) → `AlreadyAdminError`
    """
    current_role = (
        await session.execute(select(User.role).where(User.id == user_id))
    ).scalar_one_or_none()
    if current_role is None:
        raise UserNotFoundError(f"user {user_id} does not exist")
    raise AlreadyAdminError(f"user {user_id} is already an admin")
