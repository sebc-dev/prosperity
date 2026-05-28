"""Bootstrap-init service for the `/setup` flow + env-var seed (S03.2/S03.3).

Encapsulates the single-transaction "create first admin + init
household" sequence so the HTTP transport and the boot-startup hook
can share it. Two write paths, one shared core:

* `initialize_bootstrap(session, *, password, ...)` — plaintext path
  used by `POST /setup`. Delegates Argon2id hashing to
  `auth.public.create_user` (intra-auth) so this service never touches
  the password hasher.
* `_bootstrap_from_hash(session, *, password_hash, ...)` — hash-as-is
  path used by the S03.3 startup hook. Stores `password_hash`
  byte-for-byte so the operator's offline-hashed plaintext matches at
  `/auth/login`.
* `_insert_household_and_register_invalidation` — shared core that
  inserts the `Household` row, flushes (so PK / CHECK violations
  surface here for legible error attribution), and registers a
  `after_commit` listener that invalidates `_household_cache` **only
  if** the surrounding transaction commits. Rollback never fires the
  listener, so a race-lost setup never poisons the cache.

`is_setup_open(session)` answers "can /setup still write?". Returns
False as soon as the singleton row exists, regardless of
`initialized_at` — distinct from `get_household()` semantics by
design. See its docstring.

`bootstrap_initial_admin_from_env(sessionmaker, settings)` is the
FastAPI-lifespan orchestrator (S03.3). Never raises on infra/DB
failures — the app must boot even if bootstrap fails so the operator
can always `/setup` manually. Programming errors (TypeError,
AttributeError, …) intentionally propagate so a bug surfaces loudly.

Internal to the accounts module — cross-module callers go through
`backend.modules.accounts.public`.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from sqlalchemy import event
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.config import Settings
from backend.modules.accounts.models import HOUSEHOLD_SINGLETON_UUID, Household
from backend.modules.accounts.service.household import invalidate_household_cache
from backend.modules.auth.public import (
    UserRole,
    any_user_exists,
    create_user,
    create_user_with_hash,
)

logger = logging.getLogger(__name__)

# Same race-lost classification as `accounts.transports.http`
# (`_RACE_LOST_SQLSTATES`). Reproduced here rather than imported to
# keep the transport layer importable independently — the orchestrator
# runs from the lifespan, before any route is wired.
#
# 23505 unique_violation: PK on `household.id` AND UNIQUE on
# `lower(email)`. 23514 check_violation: defensive coverage of
# `ck_household_singleton`. 40001 serialization_failure: a true
# concurrent flush under REPEATABLE READ can abort the loser before
# UNIQUE fires; same race-lost semantics. Also covers a `40001` raised
# by `is_setup_open`'s SELECT when another worker has just committed.
_RACE_LOST_SQLSTATES = frozenset({"23505", "23514", "40001"})

# Postgres `connection_exception` family — transient network /
# liveness errors that warrant a retry. We deliberately exclude
# 40001 (handled above as race-lost) and 25*** (in_failed_sql_transaction)
# which would point at a bug.
_TRANSIENT_SQLSTATE_PREFIXES = ("08",)

# Tunable retry policy. Cumulative wall-clock on persistent failure:
# 0.5 + 1.0 + 2.0 = 3.5s before giving up. Tested via a monkeypatched
# `asyncio.sleep` no-op so the test suite stays fast.
_TRANSIENT_RETRIES = 3
_TRANSIENT_BACKOFF_S: tuple[float, ...] = (0.5, 1.0, 2.0)


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


async def _insert_household_and_register_invalidation(
    session: AsyncSession,
    *,
    household_name: str,
) -> None:
    """Insert the household singleton + register cache invalidation.

    Shared by `initialize_bootstrap` (plaintext path) and
    `_bootstrap_from_hash` (env-var path). Both callers chain a user
    INSERT afterwards on the same session; flushing here surfaces PK /
    CHECK violations at the household step rather than mixing them
    with email-UNIQUE errors at user-INSERT time.

    The `after_commit` listener uses `once=True` so a session reused
    across requests cannot accidentally invalidate twice. On rollback
    (race-lost branch in the route, or any exception in the boot
    hook), the listener never fires — the cache stays intact.
    """
    household = Household(
        name=household_name,
        base_currency="EUR",
        initialized_at=datetime.now(tz=UTC),
    )
    session.add(household)
    # Surface PK / CHECK violations here so error attribution stays
    # local to the household step (the outer commit would otherwise be
    # the only place the IntegrityError could rise from).
    await session.flush()

    # `after_commit` fires on `session.sync_session` once the outer
    # transaction commits. We register on the sync_session because
    # SQLAlchemy's async event facade re-routes to the underlying sync
    # session for txn-level events.
    @event.listens_for(session.sync_session, "after_commit", once=True)
    def _invalidate_on_commit(_sync_session: object) -> None:  # pyright: ignore[reportUnusedFunction]
        invalidate_household_cache()


async def initialize_bootstrap(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: str,
    household_name: str,
) -> UUID:
    """Create the first admin + initialise the household, atomically.

    Plaintext-password entrypoint used by `POST /setup` (S03.2).
    Delegates hashing to `auth.public.create_user` so this module
    never imports the underscore-private `_password` factory.

    Pre-condition: the caller has just verified `is_setup_open()`.
    This service does **not** re-check — it goes straight to the
    writes and counts on the DB constraints (PK on `household`,
    UNIQUE on `lower(email)`) to reject the concurrent-loser case via
    `IntegrityError`. The HTTP route then maps it to 404.

    Returns the newly-created admin's `id` (UUID) rather than the
    full ORM `User`. The caller only needs the id (route uses it for
    `issue_*_token`; boot hook uses it for logging). Keeping `User`
    out of the return type lets `auth.public.__all__` stay minimal.

    Does not commit. The route's `get_db` dependency commits at the
    end of the request (ADR 0015).
    """
    await _insert_household_and_register_invalidation(
        session, household_name=household_name
    )
    admin = await create_user(
        session,
        email=email,
        password=password,
        display_name=display_name,
        role=UserRole.ADMIN,
    )
    return admin.id


async def _bootstrap_from_hash(
    session: AsyncSession,
    *,
    email: str,
    password_hash: str,
    display_name: str,
    household_name: str,
) -> UUID:
    """Hash-as-is bootstrap used by the S03.3 startup hook.

    Stores `password_hash` byte-for-byte so `pwdlib.verify(plaintext,
    stored)` at the next `/auth/login` matches the plaintext the
    operator hashed offline via `scripts/hash_password.py`. Hashing the
    hash a second time would silently break login.

    Same pre-conditions and DB-constraint contract as
    `initialize_bootstrap`. Does not commit — the orchestrator owns
    the transaction and commits explicitly after a successful flush.
    """
    await _insert_household_and_register_invalidation(
        session, household_name=household_name
    )
    admin = await create_user_with_hash(
        session,
        email=email,
        password_hash=password_hash,
        display_name=display_name,
        role=UserRole.ADMIN,
    )
    return admin.id


def _is_hash_recognisable(password_hash: str) -> bool:
    """Probe whether `pwdlib` can identify the hash format.

    Calls `PasswordHash.recommended().verify("x", hash)` — `pwdlib`
    raises `UnknownHashError` if it cannot identify the hash (bad
    prefix, truncated to nothing, plaintext typed into the env var by
    mistake) and otherwise returns `False` because `"x"` does not
    match. A `False` return is the **happy** outcome of this probe:
    the hash parsed, so the operator's actual plaintext has a chance
    of verifying at `/auth/login`.

    Constructs a fresh `PasswordHash` rather than reaching into
    `auth.service._password.password_hasher` because the latter is
    underscore-private intra-auth and the public surface (`auth.public`)
    deliberately doesn't expose it. A one-shot construction at boot
    costs ~100ms; not worth a public-surface entry.

    The orchestrator skips bootstrap on probe failure rather than
    proceeding optimistically: the catastrophic alternative is the row
    landing in `users.password_hash`, `/auth/login` raising
    `UnknownHashError` (not caught by the login route), the response
    becoming a 500 (oracle vs 401), AND the deployment being permanently
    locked because `/setup` is now 404 — remediation = manual
    `DELETE FROM users`.
    """
    try:
        PasswordHash.recommended().verify("x", password_hash)
    except UnknownHashError:
        return False
    return True


async def bootstrap_initial_admin_from_env(  # noqa: PLR0911 — each branch is a documented skip-or-fail path; collapsing them would obscure the runbook table.
    sessionmaker: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    """Auto-create the first admin from `INITIAL_ADMIN_*` if applicable.

    Called from the FastAPI lifespan after the engine is up but before
    the app accepts traffic. No-op in any of these cases:

    * Neither env var set → normal mode, silent.
    * Only one of the two set → warning `initial_admin_partial_config`,
      skip. (A typo in an env-file must not block startup.)
    * Hash format unrecognisable to `pwdlib` → error
      `initial_admin_hash_invalid`, skip. (Defends against a plaintext
      typed into `INITIAL_ADMIN_PASSWORD_HASH` by mistake.)
    * DB already initialised → info `initial_admin_skipped`, skip.
    * Race lost against another worker (SQLSTATE 23505/23514/40001) →
      info `initial_admin_race_lost`, skip.
    * Transient DB error (SQLSTATE 08***) → up to 3 retries with
      exponential backoff; persistent failure logs `error
      initial_admin_db_error_persistent` and lets startup continue.

    Never raises on infra/DB failures: the app must boot even when
    bootstrap fails so the operator can always `/setup` manually.
    Programming errors (TypeError, AttributeError, …) intentionally
    propagate so a bug surfaces loudly at startup rather than hiding
    in a silent skip.
    """
    email = settings.initial_admin_email
    hash_secret = settings.initial_admin_password_hash

    # Normal mode: no env vars set, silent skip. The vast majority of
    # deployments take this path — we don't want a log line every boot.
    if email is None and hash_secret is None:
        return

    # XOR config: a single value almost certainly means an env-file
    # typo. Warn loudly + skip rather than half-creating an admin or
    # crashing the boot.
    if email is None or hash_secret is None:
        logger.warning(
            "initial_admin_partial_config",
            extra={
                "has_email": email is not None,
                "has_hash": hash_secret is not None,
            },
        )
        return

    password_hash = hash_secret.get_secret_value()

    # Canonical probe via `pwdlib.verify` rather than a `startswith`
    # check: `pwdlib` is the source of truth for what counts as a
    # valid hash and what `/auth/login` will accept. A `startswith`
    # would let a plaintext "argon2id-wantabe" through; the canonical
    # probe rejects everything `pwdlib.verify` would later reject.
    if not _is_hash_recognisable(password_hash):
        logger.error("initial_admin_hash_invalid")
        return

    for attempt in range(_TRANSIENT_RETRIES):
        try:
            async with sessionmaker() as session:
                # Re-check open-ness on every retry: another worker may
                # have committed between our previous attempt and this
                # one. Cheap (two SELECTs against an empty/near-empty
                # users + household).
                if not await is_setup_open(session):
                    logger.info(
                        "initial_admin_skipped",
                        extra={"reason": "already_initialized"},
                    )
                    return
                admin_id = await _bootstrap_from_hash(
                    session,
                    email=email,
                    password_hash=password_hash,
                    display_name=settings.initial_admin_display_name,
                    household_name=settings.initial_household_name,
                )
                await session.commit()
                logger.info(
                    "initial_admin_created",
                    extra={"user_id": str(admin_id)},
                )
                return

        except DBAPIError as exc:
            sqlstate = getattr(exc.orig, "sqlstate", None) or ""
            # Race lost: another worker beat us to it. No retry — the
            # next pass through the loop would observe `is_setup_open
            # == False` and skip anyway.
            if sqlstate in _RACE_LOST_SQLSTATES:
                logger.info(
                    "initial_admin_race_lost",
                    extra={"sqlstate": sqlstate, "attempt": attempt},
                )
                return
            # Transient connection error: retry with backoff. The last
            # attempt falls through to the persistent-error branch so
            # the loop terminates instead of sleeping pointlessly.
            if (
                sqlstate.startswith(_TRANSIENT_SQLSTATE_PREFIXES)
                and attempt < _TRANSIENT_RETRIES - 1
            ):
                logger.warning(
                    "initial_admin_db_error_retry",
                    extra={
                        "attempt": attempt,
                        "sqlstate": sqlstate,
                        "error_type": type(exc).__name__,
                    },
                )
                # `asyncio.sleep` is non-blocking inside the lifespan
                # (no clients are waiting on the loop yet). Tests
                # monkeypatch this attribute to a no-op via
                # `backend.modules.accounts.service.setup.asyncio.sleep`.
                await asyncio.sleep(_TRANSIENT_BACKOFF_S[attempt])
                continue
            # Persistent failure or unknown SQLSTATE: log at ERROR
            # (not WARNING) so log aggregators alert. Startup
            # continues — the operator can still `/setup` manually
            # once the DB is healthy.
            logger.error(
                "initial_admin_db_error_persistent",
                extra={
                    "attempt": attempt,
                    "sqlstate": sqlstate,
                    "error_type": type(exc).__name__,
                },
            )
            return
