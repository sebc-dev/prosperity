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

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
INITDB = REPO_ROOT / "compose" / "initdb"

# Client-sync tables published in S13.1 (ADR 0003 — no sensitive columns).
# MUST stay in sync with PUBLISHED_TABLES in tests/unit/test_powersync_manifest.py.
# This tier is the source of truth: it asserts the SQL produces EXACTLY this set,
# so a server-only table added by mistake (or a debt-projection table advanced
# prematurely) turns the build red.
PUBLISHED_TABLES = frozenset(
    {
        "accounts",
        "account_members",
        "transactions",
        "splits",
        "categories",
        "budgets",
        "budget_contributors",
    }
)


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
        #    05 (CREATE DATABASE via \gexec) is psql-only and irrelevant here.
        #    Use a raw psycopg2 cursor with NO params: the SQL contains `%I`
        #    (server-side format()) which psycopg2 would otherwise mistake for a
        #    client-side parameter placeholder.
        engine = create_engine(sync_dsn)
        raw = engine.raw_connection()
        try:
            cursor = raw.cursor()
            for name in ("00_powersync_roles.sql", "10_powersync_publication.sql"):
                cursor.execute((INITDB / name).read_text())
            raw.commit()
        finally:
            raw.close()

        try:
            yield engine
        finally:
            engine.dispose()


def test_publication_matches_client_allowlist(published_engine: Engine) -> None:
    with published_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT tablename FROM pg_publication_tables "
                "WHERE pubname = 'powersync' AND schemaname = 'public'"
            )
        )
        published = {r[0] for r in rows}
    # Exact match (allowlist): too many = leak, too few = broken sync.
    assert published == set(PUBLISHED_TABLES), (
        f"publication drift — unexpected: {published - PUBLISHED_TABLES}, "
        f"missing: {PUBLISHED_TABLES - published}"
    )


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
    # SELECT is scoped to exactly the published tables — no broad GRANT.
    assert granted == set(PUBLISHED_TABLES), (
        f"SELECT grant drift — unexpected: {granted - PUBLISHED_TABLES}, "
        f"missing: {PUBLISHED_TABLES - granted}"
    )
