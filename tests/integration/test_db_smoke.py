"""Integration smoke test: the testcontainers Postgres + db_session fixture work."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_db_session_executes_query(db_session: AsyncSession) -> None:
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar_one() == 1


async def test_db_session_rolls_back_between_tests(db_session: AsyncSession) -> None:
    await db_session.execute(text("CREATE TEMP TABLE smoke_marker (id int)"))
    await db_session.execute(text("INSERT INTO smoke_marker VALUES (1)"))
    count = await db_session.execute(text("SELECT COUNT(*) FROM smoke_marker"))
    assert count.scalar_one() == 1
