"""Level 1 schema check for Alembic migrations.

Applies `alembic upgrade head` against the session-scoped testcontainers
Postgres, diffs the runtime schema against the versioned snapshot in
`tests/snapshots/`, then validates that `alembic downgrade base` is also
clean. Cf. docs/Stratégie de tests §4.6.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect
from testcontainers.postgres import PostgresContainer

from alembic import command

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "schema_baseline.txt"


def _alembic_config(async_dsn: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", async_dsn)
    return cfg


def _schema_snapshot(sync_dsn: str) -> str:
    engine = create_engine(sync_dsn)
    try:
        insp = inspect(engine)
        lines: list[str] = []
        for table in sorted(insp.get_table_names()):
            cols = ", ".join(col["name"] for col in insp.get_columns(table))
            lines.append(f"{table}: {cols}")
        return "\n".join(lines)
    finally:
        engine.dispose()


def test_baseline_migration_round_trip(postgres_container: PostgresContainer) -> None:
    async_dsn = postgres_container.get_connection_url()
    # Reflection runs synchronously via psycopg2-binary (declared as dev dep).
    sync_dsn = async_dsn.replace("postgresql+asyncpg://", "postgresql+psycopg2://")

    cfg = _alembic_config(async_dsn)

    command.upgrade(cfg, "head")
    assert _schema_snapshot(sync_dsn) == SNAPSHOT_PATH.read_text().strip()

    command.downgrade(cfg, "base")
