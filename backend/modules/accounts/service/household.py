"""Household singleton accessor + process-local cache.

`get_household()` returns the singleton if `/setup` (S03.2) has marked
it `initialized_at`. Until then it raises `HouseholdNotInitializedError`,
which the caller (route or RBAC middleware) translates to a
domain-appropriate error response.

Cache lifecycle
---------------
The household row is set once (at `/setup`) and read on every
authenticated request. We cache the detached ORM object in a module-level
variable: the first successful read populates the cache, subsequent
reads short-circuit the DB hit.

* `session.expunge(h)` detaches the loaded object from the session so
  the cached reference survives the originating session being closed
  (commit/rollback). The model has no relationships, so attribute
  access on the detached object never triggers lazy-loading.
* Concurrent cache-miss reads from independent async tasks may both
  hit the DB and overwrite each other; this is safe because both
  writes store the same value (idempotent — only one row can ever
  satisfy the singleton CHECK).
* `invalidate_household_cache()` is intra-module only (S03.2 calls it
  after the `/setup` transaction commits; tests call it via an
  autouse fixture to keep per-test isolation).

Post-commit contract (S03.2 callers)
------------------------------------
`get_household()` MUST NOT be called inside an uncommitted transaction
that just wrote `initialized_at`. The cache stores the in-memory state
seen by `session.get` (which consults the identity map first), so a
read followed by a rollback would seed every subsequent worker with a
phantom singleton the DB never persisted. The `/setup` flow must commit
first, then warm the cache — and on any error path that rolls back the
write, callers must call `invalidate_household_cache()`.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.accounts.models import HOUSEHOLD_SINGLETON_UUID, Household


class HouseholdNotInitializedError(Exception):
    """Raised by `get_household()` when `/setup` has not completed."""


_household_cache: Household | None = None


async def get_household(session: AsyncSession) -> Household:
    """Return the singleton household, or raise if `/setup` hasn't run.

    `session.get` consults the identity map first (so a freshly-INSERTed
    row in the same transaction — the S03.2 case — resolves without a
    second SELECT), then falls back to a primary-key fetch.

    Caller contract: only invoke after the writer transaction has
    committed. Calling on an uncommitted session poisons the cache
    with a value the DB may never persist (see module docstring).
    """
    global _household_cache  # noqa: PLW0603  process-local singleton cache
    if _household_cache is not None:
        return _household_cache
    household = await session.get(Household, HOUSEHOLD_SINGLETON_UUID)
    if household is None or household.initialized_at is None:
        raise HouseholdNotInitializedError("Household singleton not initialised; run /setup first.")
    session.expunge(household)
    _household_cache = household
    return _household_cache


def invalidate_household_cache() -> None:
    """Clear the process-local cache. Intra-module only (S03.2, tests)."""
    global _household_cache  # noqa: PLW0603  process-local singleton cache
    _household_cache = None
