"""Single source of truth for the PowerSync publication allowlist (ADR 0003).

The set of tables published to the sync download channel — the sync security
boundary. Both the unit manifest test and the testcontainers integration test
import `PUBLISHED_TABLES` from here, and a unit test asserts that
`compose/initdb/10_powersync_publication.sql` declares exactly this set
(`publication_allowlist_from_sql`) — so the allowlist lives in ONE place and any
drift between the SQL and the Python constant fails loudly.

S13.7 added the debt-projection tables: `debts` (with a column-list excluding the
server-only `materialization_trace`, D-MAT), `share_requests`, `settlement_lines`
(full-column), and `users_public` (the non-PII identity projection).
`settlements` stays UNPUBLISHED (fail-closed, D-SET — free-text PII note +
inexpressible per-participant routing).

Underscore prefix → pytest does not collect this as a test module.
"""

from __future__ import annotations

import re
from pathlib import Path

# Side-effect import registers `debts` on `Base.metadata` (needed by
# debts_published_columns). Same set as alembic/env.py.
import backend.modules.debts.models  # noqa: F401  # pyright: ignore[reportUnusedImport]
from backend.shared.models import Base

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLICATION_SQL = REPO_ROOT / "compose" / "initdb" / "10_powersync_publication.sql"

# Tables published to the sync download channel (ADR 0003). `debts` is published
# with a COLUMN-LIST (see DEBTS_PUBLISHED_COLUMNS) excluding materialization_trace.
# Deliberately ABSENT: `settlements` (fail-closed, D-SET) and every server-only /
# PII table (users/refresh_tokens/invitations/admin_audit_logs/sync_request_log/
# banking staging).
PUBLISHED_TABLES = frozenset(
    {
        "accounts",
        "account_members",
        "transactions",
        "splits",
        "categories",
        "budgets",
        "budget_contributors",
        # S13.7 debt-projection + identity tables.
        "debts",
        "share_requests",
        "settlement_lines",
        "users_public",
    }
)

# The one column of `debts` that must NEVER be replicated (server-only forensic
# marker — ADR 0003 / CONTEXT.md). Excluded at the publication column-list level
# (D-MAT), so it can never reach a client even through a `SELECT *` sync rule.
DEBTS_SERVER_ONLY_COLUMN = "materialization_trace"


def debts_published_columns() -> frozenset[str]:
    """Columns of `debts` that SHOULD be published = all columns minus the
    server-only `materialization_trace`.

    Derived from the live ORM metadata so a FUTURE column added to `debts` is
    expected to be published by default — if it is sensitive and someone forgets
    to exclude it, the integration test (which compares this against the live
    publication catalog) goes red, and if it is benign the column-list must be
    updated to carry it. Either way drift is loud.
    """
    columns = {c.name for c in Base.metadata.tables["debts"].columns}
    return frozenset(columns - {DEBTS_SERVER_ONLY_COLUMN})


def publication_allowlist_from_sql() -> frozenset[str]:
    """Parse the publication SQL and return every table it publishes.

    Two sources, unioned: the `allow text[] := ARRAY[...]` block (full-column
    tables) AND the dedicated `ALTER PUBLICATION powersync ADD TABLE debts (...)`
    column-list block (S13.7). Lets a test assert the SQL declares exactly
    `PUBLISHED_TABLES`, keeping the SQL and the Python constant from silently
    drifting. Strips `--` line comments first so a table name that only appears
    in a comment never counts.
    """
    code = "\n".join(line.split("--", 1)[0] for line in PUBLICATION_SQL.read_text().splitlines())
    match = re.search(r"allow\s+text\[\]\s*:=\s*ARRAY\s*\[(.*?)\]", code, re.DOTALL)
    if match is None:
        raise AssertionError("could not locate the `allow text[] := ARRAY[...]` block")
    tables = set(re.findall(r"'([a-z_][a-z0-9_]*)'", match.group(1)))
    # Pick up tables published via an explicit `ADD TABLE <name> (...)` column-list
    # (debts) — these are NOT in the `allow` array.
    tables |= set(
        re.findall(
            r"ALTER\s+PUBLICATION\s+powersync\s+ADD\s+TABLE\s+([a-z_][a-z0-9_]*)\s*\(",
            code,
            re.IGNORECASE,
        )
    )
    return frozenset(tables)
