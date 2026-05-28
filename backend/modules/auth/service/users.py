"""User-creation and existence helpers (S03.2 + S03.3 boot hook).

`create_user` hashes the password via `pwdlib` and INSERTs the row,
**without** committing — composable inside a larger transaction. The
`/setup` flow needs to atomically create the admin + initialise the
household in one shot (see `accounts.service.setup`). UNIQUE-on-email
enforcement is delegated to the `uq_users_email_lower` functional
index — duplicate-creation attempts surface as
`sqlalchemy.exc.IntegrityError` from the `session.flush()` below.

`create_user_with_hash` is the S03.3 variant: it takes a pre-computed
Argon2id hash and stores it **as-is** without re-hashing. The
`INITIAL_ADMIN_PASSWORD_HASH` env var holds a hash generated offline
via `scripts/hash_password.py` so the plaintext never reaches the
process environment; passing it through `password_hasher().hash()`
would silently double-hash and make `/auth/login` impossible to use.
Two explicit functions (vs. a `password XOR hash` polymorphic
signature) keep the call site unambiguous and dodge a runtime branch
on `password is None`.

`any_user_exists` is a cheap EXISTS check used by `/setup` to gate the
route open/closed; equivalent SQL: `SELECT EXISTS(SELECT 1 FROM users)`.
S03.3 reuses it from a boot hook to decide whether to seed the admin
from `INITIAL_ADMIN_*` env vars.

Internal to the auth module — cross-module callers must import via
`backend.modules.auth.public`.
"""

from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.auth.models import User, UserRole
from backend.modules.auth.service._password import password_hasher


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: str,
    role: UserRole,
) -> User:
    """Persist a `User` with an Argon2id-hashed password.

    Does **not** commit. The caller (route via `get_db`, or boot hook)
    commits its own transaction. `session.flush()` is called here so any
    UNIQUE / NOT NULL violation surfaces as `IntegrityError` at this call
    site rather than at the outer commit — keeping error attribution
    legible.
    """
    user = User(
        # `_normalize_email` validator on `User` lowercases + strips so the
        # functional index `uq_users_email_lower` can never disagree.
        email=email,
        password_hash=password_hasher().hash(password),
        display_name=display_name,
        role=role,
    )
    session.add(user)
    await session.flush()
    return user


async def create_user_with_hash(
    session: AsyncSession,
    *,
    email: str,
    password_hash: str,
    display_name: str,
    role: UserRole,
) -> User:
    """Persist a `User` with a pre-computed Argon2id hash, stored AS-IS.

    Used by the S03.3 startup hook to materialise an admin from
    `INITIAL_ADMIN_PASSWORD_HASH`. The hash is inserted unchanged so
    `pwdlib.verify(plaintext, password_hash)` at the next `/auth/login`
    matches the plaintext the operator hashed offline via
    `scripts/hash_password.py`.

    The orchestrator probes the hash format with
    `password_hasher().verify("x", hash)` before calling this helper, so
    `UnknownHashError` cannot reach the DB. We don't re-probe here:
    `create_user_with_hash` is intentionally a thin wrapper that trusts
    its caller, mirroring `create_user` which trusts the route to
    validate the plaintext.

    Does **not** commit. The caller (boot orchestrator) owns the
    transaction. `session.flush()` surfaces UNIQUE / NOT NULL violations
    here so error attribution stays local to this function rather than
    deferring to the outer commit.
    """
    user = User(
        # `_normalize_email` validator on `User` lowercases + strips so the
        # functional index `uq_users_email_lower` can never disagree.
        email=email,
        password_hash=password_hash,
        display_name=display_name,
        role=role,
    )
    session.add(user)
    await session.flush()
    return user


async def any_user_exists(session: AsyncSession) -> bool:
    """True iff at least one row exists in the `users` table."""
    result = await session.execute(select(exists().select_from(User)))
    return bool(result.scalar())
