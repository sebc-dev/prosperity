"""Level 1 schema check for Alembic migrations.

Applies `alembic upgrade head` against the session-scoped testcontainers
Postgres, diffs the runtime schema against the versioned snapshot in
`tests/snapshots/`, then validates that `alembic downgrade base` is also
clean (no `users` table, no `user_role` ENUM left behind).

The snapshot captures:
- Postgres ENUM types and their labels (catches an `upgrade()` that
  forgets `create_type=False` or a `downgrade()` that forgets to drop
  the type).
- Per-table column name, dialect-compiled type, and nullability (catches
  a column dropped, renamed, retyped, or with flipped NULL/NOT NULL).
- Per-table primary key (name + columns).
- Per-table non-PK indexes including functional ones, with their full
  expression (catches a missing `lower(email)` index or any UNIQUE
  index dropped).

Cf. docs/Stratégie de tests §4.6 — the format goes beyond the bare
"niveau 1 minimal" because the gap matters: a missing ENUM drop or a
flipped nullability bit would corrupt prod silently.
"""

from __future__ import annotations

import re
from pathlib import Path

from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, text
from testcontainers.postgres import PostgresContainer

from alembic import command

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SNAPSHOT_PATH = REPO_ROOT / "tests" / "snapshots" / "schema_baseline.txt"


def _alembic_config(async_dsn: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", async_dsn)
    return cfg


def _index_expression(indexdef: str) -> str:
    """Extract the trailing `(...)` body of a `CREATE INDEX ...` statement.

    Greedy match handles nested parens in functional indexes such as
    `(lower((email)::text))`.
    """
    match = re.search(r"\((.+)\)\s*$", indexdef.strip())
    return match.group(1) if match else indexdef


def _format_schema(engine: Engine) -> str:
    with engine.connect() as conn:
        enums = list(
            conn.execute(
                text(
                    "SELECT t.typname, "
                    "string_agg(e.enumlabel, ', ' ORDER BY e.enumsortorder) "
                    "FROM pg_type t "
                    "JOIN pg_enum e ON e.enumtypid = t.oid "
                    "JOIN pg_namespace n ON n.oid = t.typnamespace "
                    "WHERE n.nspname = 'public' "
                    "GROUP BY t.typname ORDER BY t.typname"
                )
            )
        )
        indexes_raw = list(
            conn.execute(
                text(
                    "SELECT tablename, indexname, indexdef FROM pg_indexes "
                    "WHERE schemaname = 'public' ORDER BY tablename, indexname"
                )
            )
        )

    indexes_by_table: dict[str, list[tuple[str, str]]] = {}
    for tablename, indexname, indexdef in indexes_raw:
        indexes_by_table.setdefault(tablename, []).append((indexname, indexdef))

    insp = inspect(engine)
    dialect = engine.dialect

    lines: list[str] = []
    for name, labels in enums:
        lines.append(f"enum {name}: {labels}")
    if enums:
        lines.append("")

    for table in sorted(insp.get_table_names()):
        lines.append(f"table {table}")
        for col in sorted(insp.get_columns(table), key=lambda c: c["name"]):
            col_type = col["type"].compile(dialect=dialect)
            nullable = "NULL" if col["nullable"] else "NOT NULL"
            lines.append(f"  col {col['name']}: {col_type} {nullable}")
        pk = insp.get_pk_constraint(table)
        pk_name = pk.get("name") or ""
        if pk["constrained_columns"]:
            pk_cols = ", ".join(pk["constrained_columns"])
            lines.append(f"  pk {pk_name}({pk_cols})")
        # pg_indexes also lists the PK-backing index under the same name;
        # skip it to avoid duplicating the constraint above.
        for indexname, indexdef in indexes_by_table.get(table, []):
            if indexname == pk_name:
                continue
            unique = "UNIQUE" if "CREATE UNIQUE INDEX" in indexdef else "INDEX"
            lines.append(f"  idx {indexname} {unique}: {_index_expression(indexdef)}")
        lines.append("")

    return "\n".join(lines).strip()


def _schema_snapshot(sync_dsn: str) -> str:
    engine = create_engine(sync_dsn)
    try:
        return _format_schema(engine)
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
    post = _schema_snapshot(sync_dsn)
    # The most likely regressions on a migration rewrite are an orphaned
    # `user_role` ENUM or a leftover `users` / `refresh_tokens` table —
    # all silently invisible in column-name-only snapshots, so assert
    # each one explicitly.
    assert "enum " not in post, f"ENUM type leaked after downgrade:\n{post}"
    assert "table users" not in post, f"users table leaked after downgrade:\n{post}"
    assert "table refresh_tokens" not in post, (
        f"refresh_tokens table leaked after downgrade:\n{post}"
    )
