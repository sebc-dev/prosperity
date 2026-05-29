"""Round-trip persistence test for `UserRole` (S04.1, P04.1.1).

P04.1.1 moves `UserRole` out of `models.py` into `domain.py`. The
SQLAlchemy column mapping — `Enum(UserRole, name="user_role",
values_callable=_user_role_values)` — stays in `models.py`. This test
pins that the move is transparent end-to-end: a `User` persisted with
`UserRole.MEMBER` reads back as `UserRole.MEMBER` from an **independent**
session, and the raw value stored in Postgres is the lowercased
`"member"` (not the member name `"MEMBER"`) — i.e. `values_callable`
still drives the mapping after the relocation.

Uses the committed fixtures (real cross-session visibility) so the
read-back genuinely crosses a transaction boundary rather than reading
the writer's identity-mapped object.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.modules.auth.domain import UserRole
from backend.modules.auth.models import User

pytestmark = [pytest.mark.usefixtures("_clean_committed_db")]


async def test_userrole_round_trips_through_pg_enum(
    committed_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with committed_sessionmaker() as session:
        user = User(
            email="enum-roundtrip@example.com",
            password_hash="x" * 60,
            display_name="Enum Roundtrip",
            role=UserRole.MEMBER,
        )
        session.add(user)
        await session.flush()
        user_id = user.id
        await session.commit()

    # Independent session: the ORM re-hydrates `role` from the column,
    # exercising the value -> enum mapping rather than returning the
    # cached instance from the writer's identity map.
    async with committed_sessionmaker() as session:
        reloaded = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
        assert reloaded.role is UserRole.MEMBER

        # The raw stored value is the lowercased ENUM label, proving
        # `values_callable` survived the move to `domain.py`.
        raw = (
            await session.execute(
                text("SELECT role::text FROM users WHERE id = :id"),
                {"id": user_id},
            )
        ).scalar_one()
        assert raw == "member"
