"""Cheap (no-Docker) guards over the PowerSync dev manifest (S13.1).

These assert the *shape* of the static config — compose, .env.example,
config.yaml, sync_rules.yaml, and the publication SQL. The real security
boundary (the exact set of published tables) is enforced against a live
Postgres in tests/integration/sync/test_powersync_publication.py; the
constant below is the single source of truth both tiers reference.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

# Side-effect imports register each module's tables on `Base.metadata` (same set
# as alembic/env.py) — REQUIRED for test_published_tables_exist_in_metadata,
# which is otherwise asserting against an empty MetaData.
import backend.modules.accounts.models  # noqa: F401  # pyright: ignore[reportUnusedImport]
import backend.modules.auth.models  # noqa: F401  # pyright: ignore[reportUnusedImport]
import backend.modules.budget.models  # noqa: F401  # pyright: ignore[reportUnusedImport]
import backend.modules.debts.models  # noqa: F401  # pyright: ignore[reportUnusedImport]
import backend.modules.transactions.models  # noqa: F401  # pyright: ignore[reportUnusedImport]
from backend.shared.models import Base
from tests.unit import _yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "compose.dev.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
CONFIG_YAML = REPO_ROOT / "powersync" / "config.yaml"
SYNC_RULES = REPO_ROOT / "powersync" / "sync_rules.yaml"
PUBLICATION_SQL = REPO_ROOT / "compose" / "initdb" / "10_powersync_publication.sql"
README = REPO_ROOT / "README.md"

# Client-sync tables published in S13.1 (ADR 0003 — no sensitive columns).
# The integration test asserts the publication SQL produces EXACTLY this set;
# keep the two in sync.
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


def _parse_dotenv(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def test_compose_dev_yaml_parses() -> None:
    data = yaml.safe_load(COMPOSE.read_text())
    assert set(data["services"]) >= {"postgres", "powersync"}


def test_postgres_enables_logical_replication() -> None:
    data = yaml.safe_load(COMPOSE.read_text())
    command = data["services"]["postgres"]["command"]
    assert "wal_level=logical" in command

    def _value(setting: str) -> int:
        for item in command:
            if isinstance(item, str) and item.startswith(f"{setting}="):
                return int(item.split("=", 1)[1])
        raise AssertionError(f"{setting} not set in postgres command")

    assert _value("max_wal_senders") >= 10
    assert _value("max_replication_slots") >= 10


def test_powersync_image_is_pinned() -> None:
    data = yaml.safe_load(COMPOSE.read_text())
    image = data["services"]["powersync"]["image"]
    assert image.startswith("journeyapps/powersync-service:")
    assert ":latest" not in image
    # The pinned tag flows from .env.example — it must be present and not `latest`.
    env = _parse_dotenv(ENV_EXAMPLE.read_text())
    tag = env.get("PS_IMAGE_TAG", "")
    assert tag and tag != "latest"


def test_readme_documents_download_vs_upload() -> None:
    text = README.read_text().lower()
    assert "download" in text
    assert "upload" in text
    assert "/sync/upload" in text


def test_publication_forbids_for_all_tables() -> None:
    # `FOR ALL TABLES` would replicate PII / server-only data through the sync
    # channel (ADR 0003). The publication must be table-explicit. Strip `--`
    # line comments first — the SQL deliberately *names* the forbidden form in
    # a comment, and a naive substring check would false-positive on it (the
    # exact fragility flagged in the plan review).
    lines = [line.split("--", 1)[0] for line in PUBLICATION_SQL.read_text().splitlines()]
    sql = "\n".join(lines).upper()
    assert "FOR ALL TABLES" not in sql


def test_config_yaml_parses_and_env_refs_are_declared() -> None:
    data = _yaml.load(CONFIG_YAML.read_text())
    assert "connections" in data["replication"]
    assert data["storage"]["type"] == "postgresql"
    assert "port" in data
    assert data["sync_config"]["path"]
    assert "prosperity-api" in data["client_auth"]["audience"]

    # Every `!env PS_*` reference must resolve to a declared dev var (catches a
    # `!env PS_TYPO` that would otherwise only fail at container boot).
    declared = set(_parse_dotenv(ENV_EXAMPLE.read_text()))
    referenced = _yaml.env_refs(data)
    assert referenced, "config.yaml should reference env vars via !env"
    assert referenced <= declared, f"undeclared !env refs: {referenced - declared}"


def test_sync_rules_yaml_parses() -> None:
    data = _yaml.load(SYNC_RULES.read_text())
    assert data["bucket_definitions"]


def test_sync_rules_reference_only_published_tables() -> None:
    data = _yaml.load(SYNC_RULES.read_text())
    referenced: set[str] = set()
    for bucket in data["bucket_definitions"].values():
        for query in bucket.get("data", []):
            referenced |= set(re.findall(r"\bFROM\s+([a-z_][a-z0-9_]*)", query, re.IGNORECASE))
    assert referenced, "placeholder sync rules should select from at least one table"
    unpublished = referenced - PUBLISHED_TABLES
    assert not unpublished, f"unpublished tables in sync rules: {unpublished}"


def test_published_tables_exist_in_metadata() -> None:
    """Every published table is a real table in the ORM metadata (anti-typo).

    `Base.metadata` is EMPTY until the model modules are imported for their side
    effect (cf. alembic/env.py) — this module does those imports at the top, then
    `users` is a sentinel proving the registration happened. Keeps the
    publication honest as the schema evolves: rename a table in a migration and
    this goes red.
    """
    tables = set(Base.metadata.tables)
    assert "users" in tables, "model side-effect imports did not register tables"
    missing = PUBLISHED_TABLES - tables
    assert not missing, f"published tables missing from schema: {missing}"
