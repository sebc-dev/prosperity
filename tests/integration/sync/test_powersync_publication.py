"""The real PowerSync publication security boundary (S13.1, ADR 0003).

Applies the dev initdb SQL (`00_powersync_roles.sql` + `10_powersync_publication.sql`)
to a fresh PG17 testcontainer *after* `alembic upgrade head`, then queries the
live `pg_publication_tables` / role catalogs. Going through real Postgres (rather
than parsing the SQL text) is deliberate: a regex over the SQL would be fooled by
the `--` comments that name the excluded server-only tables, and would silently
let `materialization_trace` through. Here drift is a loud, exact-match failure.

The publication SQL is table-existence-guarded, so it relies on migrations having
created the tables first — this fixture reproduces the documented dev sequence
(compose up → alembic upgrade head → apply publication).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import docker
import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from testcontainers.postgres import PostgresContainer

from alembic import command
from tests._powersync_tables import (
    DEBTS_SERVER_ONLY_COLUMN,
    PUBLISHED_TABLES,
    debts_published_columns,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
INITDB = REPO_ROOT / "compose" / "initdb"

# Driver-safe initdb scripts applied here (00 roles, 10 publication). 05
# (CREATE DATABASE via \gexec) is psql-only and irrelevant to publication checks.
INITDB_FILES = ("00_powersync_roles.sql", "10_powersync_publication.sql")


def _docker_available() -> bool:
    try:
        docker.from_env().ping()
    except Exception:
        return False
    return True


def _alembic_config(async_dsn: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", async_dsn)
    return cfg


def _apply_initdb(engine: Engine) -> None:
    """Apply the driver-safe initdb scripts via a raw psycopg2 cursor.

    NO params: the SQL contains `%I` (server-side format()) which psycopg2 would
    otherwise mistake for a client-side parameter placeholder. Safe to call more
    than once — the scripts are idempotent (see test_initdb_scripts_are_idempotent).
    """
    raw = engine.raw_connection()
    try:
        cursor = raw.cursor()
        for name in INITDB_FILES:
            cursor.execute((INITDB / name).read_text())
        raw.commit()
    finally:
        raw.close()


def _published_tables(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT tablename FROM pg_publication_tables "
                "WHERE pubname = 'powersync' AND schemaname = 'public'"
            )
        )
        return {r[0] for r in rows}


@pytest.fixture(scope="module")
def published_engine() -> Iterator[Engine]:
    """A PG17 container with migrations applied + the publication SQL run.

    Dedicated container (not the shared `postgres_container`) so the publication
    and replication roles never leak into sibling tests.
    """
    if not _docker_available():
        pytest.skip("Docker unavailable — integration tier requires a Docker daemon")

    with PostgresContainer("postgres:17-alpine", driver="asyncpg") as container:
        async_dsn = container.get_connection_url()
        sync_dsn = async_dsn.replace("postgresql+asyncpg://", "postgresql+psycopg2://")

        # 1. Create the app schema (the publication SQL is table-existence-guarded).
        command.upgrade(_alembic_config(async_dsn), "head")

        # 2. Apply the driver-safe initdb scripts (00 roles, 10 publication).
        engine = create_engine(sync_dsn)
        _apply_initdb(engine)

        try:
            yield engine
        finally:
            engine.dispose()


def test_publication_matches_client_allowlist(published_engine: Engine) -> None:
    published = _published_tables(published_engine)
    # Exact match (allowlist): too many = leak, too few = broken sync.
    assert published == set(PUBLISHED_TABLES), (
        f"publication drift — unexpected: {published - PUBLISHED_TABLES}, "
        f"missing: {PUBLISHED_TABLES - published}"
    )


def test_initdb_scripts_are_idempotent(published_engine: Engine) -> None:
    # The scripts claim idempotence + non-destructiveness, and the real dev/prod
    # flow re-runs 10 after migrations (runbook + nightly smoke). Re-apply 00+10
    # twice more (3 applications total) and assert no error and an unchanged
    # publication — locks in the invariant the runbook relies on.
    _apply_initdb(published_engine)
    _apply_initdb(published_engine)
    assert _published_tables(published_engine) == set(PUBLISHED_TABLES)


def test_replication_role_has_least_privilege(published_engine: Engine) -> None:
    with published_engine.connect() as conn:
        role = conn.execute(
            text("SELECT rolreplication, rolsuper FROM pg_roles WHERE rolname = 'powersync'")
        ).one()
        assert role.rolreplication is True, "powersync role must have REPLICATION"
        assert role.rolsuper is False, "powersync role must NOT be superuser"

        granted = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT table_name FROM information_schema.role_table_grants "
                    "WHERE grantee = 'powersync' AND privilege_type = 'SELECT' "
                    "AND table_schema = 'public'"
                )
            )
        }
    # Every published table (including `debts`) has a table-level SELECT and
    # nothing broader is granted. `debts` needs TABLE-level SELECT — not a
    # column-level grant — because PowerSync's initial snapshot runs
    # `SELECT * FROM debts`, which a column-level grant would deny (verified
    # against the live PowerSync Service: a column grant breaks replication with
    # "permission denied for table debts"). materialization_trace is kept out of
    # what clients receive by the PUBLICATION column-list (asserted below) plus
    # the explicit-column sync rules — not by the grant.
    assert granted == set(PUBLISHED_TABLES), (
        f"SELECT grant drift — unexpected: {granted - PUBLISHED_TABLES}, "
        f"missing: {PUBLISHED_TABLES - granted}"
    )


def test_debts_published_with_column_list_excluding_materialization_trace(
    published_engine: Engine,
) -> None:
    # D-MAT — the heart of the column-list publication: `materialization_trace`
    # (server-only) must NEVER be in the published columns of `debts`, and every
    # column that SHOULD be published must be present (a future `debts` column
    # silently dropped from the list would break the owner's sync).
    with published_engine.connect() as conn:
        published_cols = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT a.attname "
                    "FROM pg_publication_tables pt "
                    "JOIN pg_class c ON c.relname = pt.tablename "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = pt.schemaname "
                    "JOIN pg_attribute a ON a.attrelid = c.oid "
                    "  AND a.attname = ANY(pt.attnames) "
                    "WHERE pt.pubname = 'powersync' "
                    "  AND pt.schemaname = 'public' AND pt.tablename = 'debts'"
                )
            )
        }
    assert DEBTS_SERVER_ONLY_COLUMN not in published_cols, (
        f"server-only column {DEBTS_SERVER_ONLY_COLUMN!r} leaked into the debts publication"
    )
    expected = debts_published_columns()
    assert published_cols == set(expected), (
        f"debts column-list drift — unexpected: {published_cols - expected}, "
        f"missing: {expected - published_cols}"
    )


def test_settlements_table_is_not_published(published_engine: Engine) -> None:
    # D-SET fail-closed: `settlements` (free-text PII note) must stay REST-only.
    # `settlement_lines` IS published; this guards the deliberate asymmetry.
    published = _published_tables(published_engine)
    assert "settlements" not in published, "settlements must stay unpublished (D-SET)"
    assert "settlement_lines" in published, "settlement_lines must be published"
