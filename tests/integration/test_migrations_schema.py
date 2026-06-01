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
- Per-table foreign keys with their constrained/referred columns and
  `ON DELETE` action (catches a migration that flips RESTRICT↔CASCADE or
  drops an `ondelete` — invisible in a column/index-only diff, yet a
  silent data-integrity regression: decision F02 pins `owner_id` /
  `account_members.user_id` to RESTRICT and `account_members.account_id`
  to CASCADE).
- Per-table CHECK constraints with their normalised SQL body (catches
  a constraint silently dropped between revisions — e.g., the household
  singleton CHECK whose absence would let raw INSERTs spawn a second
  foyer; ADR 0010).
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

# Every persisted-module table is registered on `Base.metadata` via the
# integration `conftest.py` (it imports the models + the factories), so the
# `create_all` parity test below materialises the full schema.
from backend.shared.models import Base

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
        # FKs surface here (not via pg_indexes); the snapshot needs the
        # `ON DELETE` action because a column/index diff is blind to it —
        # a migration that drops `ondelete` or flips RESTRICT↔CASCADE
        # (decision F02) would otherwise pass unnoticed. SQLAlchemy omits
        # `NO ACTION` from `options`, so a bare FK renders without a suffix.
        for fk in sorted(insp.get_foreign_keys(table), key=lambda f: f.get("name") or ""):
            fk_name = fk.get("name") or ""
            fk_cols = ", ".join(fk["constrained_columns"])
            ref = fk["referred_table"]
            ref_cols = ", ".join(fk["referred_columns"])
            ondelete = (fk.get("options") or {}).get("ondelete")
            suffix = f" ON DELETE {ondelete}" if ondelete else ""
            lines.append(f"  fk {fk_name}: ({fk_cols}) -> {ref}({ref_cols}){suffix}")
        # CHECK constraints surface here (not via pg_indexes); the
        # snapshot needs them because a missing CHECK is invisible in a
        # column-name-only diff (e.g. dropping `ck_household_singleton`
        # would let raw SQL spawn a second foyer; ADR 0010).
        for ck in sorted(insp.get_check_constraints(table), key=lambda c: c["name"] or ""):
            ck_name = ck.get("name") or ""
            ck_sql = ck.get("sqltext") or ""
            lines.append(f"  ck {ck_name}: ({ck_sql})")
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


def _without_table(schema: str, table: str) -> str:
    """Drop the `table <name>` block from a formatted schema.

    `create_all` never stamps the `alembic_version` bookkeeping table, while
    `alembic upgrade head` does — strip it from both sides so the comparison
    stays schema-to-schema. Blocks are separated by a blank line (see
    `_format_schema`).
    """
    blocks = schema.split("\n\n")
    return "\n\n".join(b for b in blocks if not b.startswith(f"table {table}"))


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
    assert "table household" not in post, f"household table leaked after downgrade:\n{post}"
    assert "table admin_audit_logs" not in post, (
        f"admin_audit_logs table leaked after downgrade:\n{post}"
    )
    assert "table invitations" not in post, f"invitations table leaked after downgrade:\n{post}"
    assert "table accounts" not in post, f"accounts table leaked after downgrade:\n{post}"
    assert "table account_members" not in post, (
        f"account_members table leaked after downgrade:\n{post}"
    )
    assert "table categories" not in post, f"categories table leaked after downgrade:\n{post}"
    assert "table splits" not in post, f"splits table leaked after downgrade:\n{post}"
    assert "table transactions" not in post, f"transactions table leaked after downgrade:\n{post}"


def test_create_all_matches_alembic_head(postgres_container: PostgresContainer) -> None:
    """`Base.metadata.create_all` must produce byte-for-byte the same schema as
    `alembic upgrade head` — column types, PK, FKs + `ON DELETE`, indexes, and
    crucially the constraint/index *names* (the `NAMING_CONVENTION` parity).

    The integration tier runs on `create_all` (the `auth_schema` fixture)
    while prod runs the migrations. Their parity used to be only *implicit*
    (inferred from the CASCADE/RESTRICT behaviour tests plus a shared snapshot
    file). This pins it directly, so a divergence — e.g. a migration whose FK
    name no longer matches the model's `Index(...)` — fails loudly here.
    """
    async_dsn = postgres_container.get_connection_url()
    sync_dsn = async_dsn.replace("postgresql+asyncpg://", "postgresql+psycopg2://")

    engine = create_engine(sync_dsn)
    try:
        # Start clean (a prior test may have left model tables) and build the
        # schema purely from the ORM metadata.
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        create_all_schema = _format_schema(engine)
    finally:
        engine.dispose()

    expected = SNAPSHOT_PATH.read_text().strip()
    assert _without_table(create_all_schema, "alembic_version") == _without_table(
        expected, "alembic_version"
    )

    # Leave the session-scoped container clean for sibling tests.
    engine = create_engine(sync_dsn)
    try:
        Base.metadata.drop_all(engine)
    finally:
        engine.dispose()
