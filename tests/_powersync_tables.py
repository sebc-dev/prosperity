"""Single source of truth for the S13.1 PowerSync publication allowlist.

The set of tables published to the sync download channel (ADR 0003 — client-sync
tables without sensitive columns). Both the unit manifest test and the
testcontainers integration test import `PUBLISHED_TABLES` from here, and a unit
test asserts that `compose/initdb/10_powersync_publication.sql` declares exactly
this set (`publication_allowlist_from_sql`) — so the allowlist lives in ONE place
and any drift between the SQL and the Python constant fails loudly.

Underscore prefix → pytest does not collect this as a test module.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLICATION_SQL = REPO_ROOT / "compose" / "initdb" / "10_powersync_publication.sql"

# Client-sync tables published in S13.1 (ADR 0003 — no sensitive columns).
# Deliberately ABSENT: debt-projection tables (debts/share_requests/settlements/
# settlement_lines, deferred to S13.7) and server-only tables (users/
# refresh_tokens/invitations/admin_audit_logs/banking staging).
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


def publication_allowlist_from_sql() -> frozenset[str]:
    """Parse the `allow text[] := ARRAY[...]` block of the publication SQL.

    Lets a test assert the SQL declares exactly `PUBLISHED_TABLES`, keeping the
    SQL and the Python constant from silently drifting (e.g. when S13.7 adds the
    debt-projection tables). Strips `--` line comments first so a table name that
    only appears in a comment never counts.
    """
    code = "\n".join(line.split("--", 1)[0] for line in PUBLICATION_SQL.read_text().splitlines())
    match = re.search(r"allow\s+text\[\]\s*:=\s*ARRAY\s*\[(.*?)\]", code, re.DOTALL)
    if match is None:
        raise AssertionError("could not locate the `allow text[] := ARRAY[...]` block")
    return frozenset(re.findall(r"'([a-z_][a-z0-9_]*)'", match.group(1)))
