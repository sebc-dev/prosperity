"""Unit tests for `promote_to_admin` failure branches that need no DB.

The integration suite (`tests/integration/test_roles.py`) covers the
real Postgres behaviour. This module corners the one defensive branch
that a DB-backed test cannot reach deterministically: a `DBAPIError`
whose SQLSTATE is **not** 40001 must propagate untouched (only the
serialization-failure of a concurrent promotion is recovered).
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError

from backend.modules.auth.models import User, UserRole
from backend.modules.auth.service.roles import promote_to_admin


class _Orig(Exception):
    """Stand-in for the DBAPI driver exception wrapped by `DBAPIError`."""

    sqlstate = "42P01"  # undefined_table — anything other than 40001


async def test_promote_propagates_non_serialization_dbapi_error() -> None:
    actor = User(
        email="admin@example.com",
        password_hash="x" * 60,
        display_name="Admin",
        role=UserRole.ADMIN,
    )

    session = AsyncMock()
    # Actor guard passes (active admin)...
    session.get = AsyncMock(return_value=actor)
    # ...then the conditional UPDATE raises a non-40001 DBAPIError, which the
    # 40001-only recovery path must re-raise rather than swallow.
    session.execute = AsyncMock(
        side_effect=DBAPIError("UPDATE users ...", {}, _Orig("boom"))
    )

    with pytest.raises(DBAPIError):
        await promote_to_admin(session, user_id=uuid4(), by_admin_id=actor.id)

    # The non-recoverable error short-circuited before any rollback attempt.
    session.rollback.assert_not_awaited()
