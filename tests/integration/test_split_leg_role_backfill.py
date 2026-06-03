"""Back-fill check for migration `0013_split_leg_role` (S08.5.1, ADR 0017).

The level-1 snapshot test pins the *resulting* schema; this pins the
*data migration* the snapshot cannot see: rows existing BEFORE `0013` must
receive a deterministic `leg_role` derived from `category_id`
(`NULL ⇒ 'funding'`, else `'classification'` — the canonical form B).

Pattern (gabarit `test_migrations_schema`): drive Alembic against the
session-scoped testcontainers Postgres, seed the minimal FK chain at `0012`
via Core `text()` INSERTs (splits inserted WITHOUT `leg_role`, which does not
exist yet at that revision), `upgrade` to `0013`, then assert. The container
is left at `base` for sibling tests.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, text
from testcontainers.postgres import PostgresContainer

from alembic import command

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_SINGLETON = "00000000-0000-0000-0000-000000000001"


def _alembic_config(async_dsn: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", async_dsn)
    return cfg


def _seed_at_0012(sync_dsn: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Seed the minimal FK chain + two splits at revision 0012.

    Returns `(funding_split_id, classification_split_id)` — the first has
    `category_id IS NULL`, the second a real category. `leg_role` is omitted
    on purpose: the column does not exist until `0013`.
    """
    user_id = uuid.uuid4()
    account_id = uuid.uuid4()
    category_id = uuid.uuid4()
    tx_id = uuid.uuid4()
    funding_split_id = uuid.uuid4()
    classification_split_id = uuid.uuid4()

    engine = create_engine(sync_dsn)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO household (id, name, base_currency) "
                    "VALUES (:id, 'Foyer', 'EUR')"
                ),
                {"id": _SINGLETON},
            )
            conn.execute(
                text(
                    "INSERT INTO users (id, email, display_name, password_hash, role) "
                    "VALUES (:id, 'seed@example.com', 'Seed', 'x', 'member')"
                ),
                {"id": user_id},
            )
            conn.execute(
                text(
                    "INSERT INTO accounts (id, household_id, name, type, currency) "
                    "VALUES (:id, :hh, 'Courant', 'courant', 'EUR')"
                ),
                {"id": account_id, "hh": _SINGLETON},
            )
            conn.execute(
                text("INSERT INTO categories (id, name) VALUES (:id, 'Courses')"),
                {"id": category_id},
            )
            conn.execute(
                text(
                    "INSERT INTO transactions "
                    "(id, account_id, date, state, created_by, tags, debt_generation_override) "
                    "VALUES (:id, :acc, '2026-01-01', 'draft', :user, '{}', 'default')"
                ),
                {"id": tx_id, "acc": account_id, "user": user_id},
            )
            conn.execute(
                text(
                    "INSERT INTO splits (id, transaction_id, account_id, amount_cents, currency) "
                    "VALUES (:id, :tx, :acc, -1000, 'EUR')"
                ),
                {"id": funding_split_id, "tx": tx_id, "acc": account_id},
            )
            conn.execute(
                text(
                    "INSERT INTO splits "
                    "(id, transaction_id, account_id, category_id, amount_cents, currency) "
                    "VALUES (:id, :tx, :acc, :cat, 1000, 'EUR')"
                ),
                {
                    "id": classification_split_id,
                    "tx": tx_id,
                    "acc": account_id,
                    "cat": category_id,
                },
            )
    finally:
        engine.dispose()
    return funding_split_id, classification_split_id


def _leg_role(sync_dsn: str, split_id: uuid.UUID) -> str | None:
    engine = create_engine(sync_dsn)
    try:
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT leg_role FROM splits WHERE id = :id"), {"id": split_id}
            ).scalar_one()
    finally:
        engine.dispose()


def test_backfill_derives_leg_role_from_category(
    postgres_container: PostgresContainer,
) -> None:
    async_dsn = postgres_container.get_connection_url()
    sync_dsn = async_dsn.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    cfg = _alembic_config(async_dsn)

    try:
        command.upgrade(cfg, "0012")
        funding_id, classification_id = _seed_at_0012(sync_dsn)

        command.upgrade(cfg, "0013")

        # Deterministic back-fill: category_id IS NULL ⇒ 'funding', else
        # 'classification' (canonical form B).
        assert _leg_role(sync_dsn, funding_id) == "funding"
        assert _leg_role(sync_dsn, classification_id) == "classification"
    finally:
        # Leave the session-scoped container clean for sibling tests.
        command.downgrade(cfg, "base")


def test_downgrade_drops_leg_role_column(postgres_container: PostgresContainer) -> None:
    async_dsn = postgres_container.get_connection_url()
    sync_dsn = async_dsn.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    cfg = _alembic_config(async_dsn)

    try:
        command.upgrade(cfg, "0013")
        command.downgrade(cfg, "0012")

        # The column AND its CHECK are gone after downgrade (clean rollback).
        engine = create_engine(sync_dsn)
        try:
            with engine.connect() as conn:
                cols = (
                    conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = 'splits'"
                        )
                    )
                    .scalars()
                    .all()
                )
                checks = (
                    conn.execute(
                        text(
                            "SELECT conname FROM pg_constraint "
                            "WHERE conname = 'ck_splits_leg_role'"
                        )
                    )
                    .scalars()
                    .all()
                )
        finally:
            engine.dispose()
        assert "leg_role" not in cols
        assert checks == []
    finally:
        command.downgrade(cfg, "base")
