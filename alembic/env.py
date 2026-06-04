"""Alembic migration environment — async SQLAlchemy 2.

DSN flows from `backend.config.get_settings()` (which reads `DATABASE_URL`
via pydantic-settings) unless an explicit `sqlalchemy.url` is already set
on the `Config` object — tests inject the testcontainers DSN that way.

`target_metadata` is the single `Base.metadata` shared by every persisted
module (cf. `backend/shared/models.py`). Each module's models file is
imported here purely for its side-effect of registering its tables on
that shared metadata — without these imports Alembic's autogenerate
would see an empty schema and emit spurious drops. env.py is outside the
`backend` import-linter root so the cross-module imports are not policed.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Side-effect imports below register each module's tables on `Base.metadata`
# (cf. module docstring); the bare module imports look unused to flake8/F401.
import backend.modules.accounts.models  # noqa: F401  # pyright: ignore[reportUnusedImport]
import backend.modules.auth.models  # noqa: F401  # pyright: ignore[reportUnusedImport]
import backend.modules.budget.models  # noqa: F401  # pyright: ignore[reportUnusedImport]
import backend.modules.debts.models  # noqa: F401  # pyright: ignore[reportUnusedImport]
import backend.modules.transactions.models  # noqa: F401  # pyright: ignore[reportUnusedImport]
from alembic import context
from backend.config import get_settings
from backend.shared.models import Base

config = context.config

if config.config_file_name is not None:
    # `disable_existing_loggers=False` so loading the Alembic logging
    # config does not silence the backend loggers (e.g. structured
    # warnings on refresh-token replay) created before this call —
    # otherwise running migrations from within the app process leaves
    # the app log-deaf.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
