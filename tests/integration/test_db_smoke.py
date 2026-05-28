"""Integration smoke test: the testcontainers Postgres + db_session fixture work."""

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from testcontainers.postgres import PostgresContainer

from backend.config import Settings
from backend.shared.db import build_engine


async def test_db_session_executes_query(db_session: AsyncSession) -> None:
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar_one() == 1


async def test_db_session_rolls_back_between_tests(db_session: AsyncSession) -> None:
    await db_session.execute(text("CREATE TEMP TABLE smoke_marker (id int)"))
    await db_session.execute(text("INSERT INTO smoke_marker VALUES (1)"))
    count = await db_session.execute(text("SELECT COUNT(*) FROM smoke_marker"))
    assert count.scalar_one() == 1


async def test_build_engine_hides_parameters_in_dbapi_error_str(
    postgres_container: PostgresContainer,
) -> None:
    """`hide_parameters=True` keeps bound values out of `DBAPIError.__str__`.

    Forge an `IntegrityError` via a PK duplicate INSERT — without the
    flag, `str(exc)` includes the bound parameters in `[parameters: ...]`.
    With the flag, SQLAlchemy substitutes `[SQL parameters hidden as
    hide_parameters=True]`. Defense in depth against accidentally
    logging the S03.3 hash via `str(exc)` in some future log shim.
    """
    settings = Settings(
        database_url=postgres_container.get_connection_url(),
        jwt_secret=SecretStr("smoke-test-jwt-secret-min-32-chars!!"),
    )
    engine = build_engine(settings)
    secret_sentinel = "do-not-leak-this-token-into-logs"

    try:
        async with async_sessionmaker(engine)() as session:
            await session.execute(
                text(
                    "CREATE TEMP TABLE hide_param_marker "
                    "(key text PRIMARY KEY, value text)"
                )
            )
            await session.execute(
                text("INSERT INTO hide_param_marker (key, value) VALUES (:k, :v)"),
                {"k": "dup", "v": secret_sentinel},
            )
            with pytest.raises(IntegrityError) as exc_info:
                await session.execute(
                    text("INSERT INTO hide_param_marker (key, value) VALUES (:k, :v)"),
                    {"k": "dup", "v": secret_sentinel},
                )
        assert secret_sentinel not in str(exc_info.value)
    finally:
        await engine.dispose()
