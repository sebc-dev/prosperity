"""Cheap (no-Docker) guards over the PowerSync dev manifest (S13.1).

These assert the *shape* of the static config — compose, .env.example,
config.yaml, sync_rules.yaml, and the publication SQL. The real security
boundary (the exact set of published tables, verified against a live Postgres)
lives in tests/integration/sync/test_powersync_publication.py; the allowlist
itself is defined once in tests/_powersync_tables.py and both tiers import it.
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
from tests._powersync_tables import (
    PUBLICATION_SQL,
    PUBLISHED_TABLES,
    publication_allowlist_from_sql,
)
from tests.unit import _yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "compose.dev.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
CONFIG_YAML = REPO_ROOT / "powersync" / "config.yaml"
SYNC_RULES = REPO_ROOT / "powersync" / "sync_rules.yaml"
README = REPO_ROOT / "README.md"


def _bucket_queries(bucket: dict[str, object]) -> list[str]:
    """Every SQL string a bucket runs — its `parameters` query (a scalar) PLUS
    each of its `data` queries. The server-only guard MUST see both: a leak can
    come from a parameter query referencing a forbidden table just as much as a
    data query."""
    queries: list[str] = []
    params = bucket.get("parameters")
    if isinstance(params, str):
        queries.append(params)
    data = bucket.get("data")
    if isinstance(data, list):
        queries.extend(q for q in data if isinstance(q, str))  # pyright: ignore[reportUnknownVariableType]
    return queries


def _referenced_tables() -> set[str]:
    """All tables referenced by any FROM/JOIN across every bucket's
    `parameters` ∪ `data` queries."""
    data = _yaml.load(SYNC_RULES.read_text())
    referenced: set[str] = set()
    for bucket in data["bucket_definitions"].values():
        for query in _bucket_queries(bucket):
            # Match both FROM and JOIN so the guard covers multi-table buckets,
            # not just single-table ones.
            referenced |= set(
                re.findall(r"\b(?:FROM|JOIN)\s+([a-z_][a-z0-9_]*)", query, re.IGNORECASE)
            )
    return referenced


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


def test_publication_sql_declares_exactly_the_allowlist() -> None:
    # Single-source guard: the `allow text[]` array in the publication SQL must
    # equal PUBLISHED_TABLES, so the SQL and the Python constant cannot drift
    # (e.g. when S13.7 adds the debt-projection tables, both move together or the
    # build goes red here).
    assert publication_allowlist_from_sql() == PUBLISHED_TABLES


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
    referenced = _referenced_tables()
    assert referenced, "sync rules should select from at least one table"
    unpublished = referenced - PUBLISHED_TABLES
    assert not unpublished, f"unpublished tables in sync rules: {unpublished}"


def test_sync_rules_declare_the_four_bucket_families() -> None:
    # AC: the four ADR 0003 families are present (plus the D-BUD / D-SET
    # derivations that split out of them). Naming is part of the glossary
    # contract — a typo'd bucket name silently drops a whole partition.
    data = _yaml.load(SYNC_RULES.read_text())
    buckets = set(data["bucket_definitions"])
    assert buckets == {
        "user_personal",
        "account_shared",
        "user_budget",
        "user_debt",
        "user_settlement",
        "household",
    }, f"unexpected bucket set: {buckets}"
    # The S13.1 placeholder must be gone.
    assert "_connectivity_check" not in buckets


def test_no_server_only_table_in_manifest() -> None:
    # The PRIMARY, self-maintaining server-only guard: every ORM table that is
    # NOT in the publication allowlist must be ABSENT from the sync rules
    # (parameters ∪ data). This updates itself as the schema grows — a future
    # server-only table (pending_actions, PATs, device_tokens) is caught the day
    # it lands, without anyone enumerating it here.
    referenced = _referenced_tables()
    server_only = set(Base.metadata.tables) - PUBLISHED_TABLES
    leaked = referenced & server_only
    assert not leaked, f"server-only tables referenced by sync rules: {leaked}"


def test_manifest_targets_admin_audit_logs_physical_name() -> None:
    # Secondary, human-readable guard naming the most dangerous tables outright —
    # including the PHYSICAL audit name `admin_audit_logs` (NOT the generic
    # `audit_logs` alias of ADR 0003) and the freshly-added `sync_request_log` /
    # `settlements` (fail-closed). Redundant with the derived guard above on
    # purpose: this one reads as documentation and fails with an obvious message.
    referenced = _referenced_tables()
    forbidden = {
        "admin_audit_logs",
        "sync_request_log",
        "settlements",
        "users",
        "refresh_tokens",
        "invitations",
        "bank_account_external_refs",
        "imported_transactions",
        "budget_threshold_alerts",
    }
    leaked = referenced & forbidden
    assert not leaked, f"forbidden tables referenced by sync rules: {leaked}"


def test_sync_rules_mask_debtor_columns_on_debts() -> None:
    # CORE security assertion at the cheap tier (D-MASK). In the `user_debt`
    # bucket the DEBTOR query (WHERE from_user_id = ...) must project BOTH
    # account_id AND source_transaction_id as NULL — unconditionally (no CASE,
    # so it can never fail-open) — while the CREDITOR query (WHERE to_user_id)
    # must project the REAL columns. A regression here is exactly the leak this
    # story exists to close, so we pin the structure, not just the runtime stream.
    data = _yaml.load(SYNC_RULES.read_text())
    debt_queries = data["bucket_definitions"]["user_debt"]["data"]
    debtor = next(q for q in debt_queries if "from_user_id = bucket.user_id" in q)
    creditor = next(q for q in debt_queries if "to_user_id = bucket.user_id" in q)

    # Debtor: both columns masked to NULL, and NOT via a CASE (unconditional).
    assert re.search(r"NULL\s+AS\s+account_id", debtor, re.IGNORECASE), debtor
    assert re.search(r"NULL\s+AS\s+source_transaction_id", debtor, re.IGNORECASE), debtor
    assert "case" not in debtor.lower(), "debtor mask must be unconditional (no CASE)"

    # Creditor: real columns, no NULL masking of the two sensitive columns.
    assert not re.search(r"NULL\s+AS\s+account_id", creditor, re.IGNORECASE), creditor
    assert not re.search(r"NULL\s+AS\s+source_transaction_id", creditor, re.IGNORECASE), creditor
    assert re.search(r"\baccount_id\b", creditor), creditor
    assert re.search(r"\bsource_transaction_id\b", creditor), creditor


def test_sync_rules_creditor_view_is_unconditional_for_all_origins() -> None:
    # Guards the DELIBERATE sync ⇄ REST divergence on overflow debts (ADR 0003
    # consequences). The creditor query reveals the real columns for EVERY debt
    # regardless of `origin` (no CASE, no `origin` predicate) -- including
    # `shared_account_overflow`, which REST still masks in V1. Safe because the
    # overflow creditor already receives the shared account + its source tx via
    # `account_shared`. This is also what keeps D-MASK CASE-free on both sides.
    # If a future change reintroduces an origin-conditioned creditor view, this
    # goes red so the divergence is re-decided on purpose, not by accident.
    data = _yaml.load(SYNC_RULES.read_text())
    debt_queries = data["bucket_definitions"]["user_debt"]["data"]
    creditor = next(q for q in debt_queries if "to_user_id = bucket.user_id" in q)
    assert "case" not in creditor.lower(), "creditor view must stay unconditional (no CASE)"
    assert "origin =" not in creditor.lower(), (
        "creditor view must not filter on origin (overflow is revealed by design)"
    )


def test_sync_rules_mask_share_request_source_tx_for_debtor() -> None:
    # D-SR: the share_requests query addressed to the DEBTOR (requested_from)
    # masks source_transaction_id; the OWNER query (requested_by) keeps it.
    data = _yaml.load(SYNC_RULES.read_text())
    sr_queries = [
        q for q in data["bucket_definitions"]["user_debt"]["data"] if "share_requests" in q
    ]
    debtor = next(q for q in sr_queries if "requested_from = bucket.user_id" in q)
    owner = next(q for q in sr_queries if "requested_by = bucket.user_id" in q)
    assert re.search(r"NULL\s+AS\s+source_transaction_id", debtor, re.IGNORECASE), debtor
    assert not re.search(r"NULL\s+AS\s+source_transaction_id", owner, re.IGNORECASE), owner


def test_users_public_model_columns_are_exactly_the_non_pii_projection() -> None:
    # S-m2: the projection is deliberately tiny. If a future migration adds a PII
    # column to `users_public` (email, a hash, anything), this goes red BEFORE it
    # can be synced household-wide. Pinned at the metadata level (no Docker).
    columns = {c.name for c in Base.metadata.tables["users_public"].columns}
    assert columns == {"user_id", "display_name", "role"}, (
        f"users_public must stay {{user_id, display_name, role}}; got {columns}"
    )


def test_users_public_query_carries_no_pii() -> None:
    # AC: users_public is synced WITHOUT PII. The household bucket query must
    # select only {user_id, display_name, role} and never email / password_hash.
    data = _yaml.load(SYNC_RULES.read_text())
    household = data["bucket_definitions"]["household"]["data"]
    query = next(q for q in household if "users_public" in q)
    lowered = query.lower()
    assert "email" not in lowered, query
    assert "password" not in lowered, query
    for col in ("user_id", "display_name", "role"):
        assert col in query, f"{col} missing from users_public sync query"


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
