"""Bootstrap-init service for the `/setup` flow (S03.2).

Encapsulates the single-transaction "create first admin + init
household" sequence so the HTTP transport is a thin shell. Will also
be called from the S03.3 boot-startup hook that materialises
`INITIAL_ADMIN_*` env vars before `/setup` becomes publicly reachable.

Two helpers:

* `is_setup_open(session)` answers "can `/setup` still write?". It
  returns `False` as soon as the singleton row exists, regardless of
  `initialized_at` — distinct from `get_household()` semantics by
  design. See docstring for the rationale.
* `initialize_bootstrap(session, ...)` performs the two writes (INSERT
  `household` + INSERT `users`) and registers a SQLAlchemy
  `after_commit` listener that invalidates the process-local
  `_household_cache` *only if* the surrounding transaction commits.
  On rollback (IntegrityError → 404 in the route) the listener never
  fires, so the cache is never poisoned by a failed setup.

Internal to the accounts module — cross-module callers must go through
`backend.modules.accounts.public`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.models import HOUSEHOLD_SINGLETON_UUID, Household
from backend.modules.accounts.service.household import invalidate_household_cache
from backend.modules.auth.public import UserRole, any_user_exists, create_user


async def is_setup_open(session: AsyncSession) -> bool:
    """True iff a fresh `/setup` is still allowed.

    Called by transport (`GET /setup`, `POST /setup` precheck) and by
    the S03.3 boot hook. `initialize_bootstrap` does **not** call this
    — it trusts its caller and relies on the DB constraints (PK on
    `household`, UNIQUE on `lower(email)`) to backstop a stale
    precheck under concurrency.

    Returns False as soon as the singleton row exists, regardless of
    `initialized_at`. The "row exists but uninitialised" state cannot
    be reached in production: migration 0004 doesn't pre-INSERT the
    row, and `/setup` is mono-transactional (partial writes never
    commit). The only path to that state is out-of-band SQL by a
    sysop — explicitly unsupported; recovery is `DELETE FROM
    household`.

    This is intentionally not the same question `get_household` asks:

    * `get_household()` — "is the household usable for reads" → raises
      on `initialized_at IS NULL`.
    * `is_setup_open()` — "is /setup still allowed to write" → False
      as soon as the row exists.
    """
    if await any_user_exists(session):
        return False
    existing = await session.get(Household, HOUSEHOLD_SINGLETON_UUID)
    return existing is None


async def initialize_bootstrap(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: str,
    household_name: str,
) -> UUID:
    """Create the first admin + initialise the household, atomically.

    Pre-condition: the caller has just verified `is_setup_open()`.
    This service does **not** re-check — it goes straight to the
    writes and counts on the DB constraints (PK on `household`,
    UNIQUE on `lower(email)`) to reject the concurrent-loser case
    via `IntegrityError`. The HTTP route then maps it to 404.

    Returns the newly-created admin's `id` (UUID) rather than the
    full ORM `User`. The caller only needs the id (route uses it for
    `issue_*_token`; boot hook uses it for logging). Keeping `User`
    out of the return type lets `auth.public.__all__` stay minimal.

    Registers a SQLAlchemy `after_commit` listener that invalidates
    the process-local `_household_cache` **only if** the surrounding
    transaction commits successfully. `once=True` so a session reused
    across requests cannot accidentally invalidate twice. On
    rollback (IntegrityError → 404 in the route) the listener never
    fires, so the cache is never poisoned by a failed setup.

    Does not commit. The route's `get_db` dependency commits at the
    end of the request (ADR 0015). The boot hook (S03.3) commits
    inside its own context manager.
    """
    household = Household(
        name=household_name,
        base_currency="EUR",
        initialized_at=datetime.now(tz=UTC),
    )
    session.add(household)
    # Surface PK / CHECK violations here so error attribution stays
    # local to this function (the outer commit would otherwise be the
    # only place the IntegrityError could rise from).
    await session.flush()

    admin = await create_user(
        session,
        email=email,
        password=password,
        display_name=display_name,
        role=UserRole.ADMIN,
    )

    # `after_commit` fires on `session.sync_session` once the outer
    # transaction commits. We register on the sync_session because
    # SQLAlchemy's async event facade re-routes to the underlying
    # sync session for txn-level events. `once=True` removes the
    # listener after firing so any session-reuse pathway cannot
    # double-invalidate. A rollback never triggers `after_commit`,
    # so the cache stays intact on the 404 race-lost branch.
    @event.listens_for(session.sync_session, "after_commit", once=True)
    def _invalidate_on_commit(_sync_session: object) -> None:  # pyright: ignore[reportUnusedFunction]
        invalidate_household_cache()

    return admin.id
