"""`sync_request_log` is SERVER-ONLY — never in the PowerSync publication (S13.2).

The idempotence journal carries cross-user request ids and must NEVER reach the
sync download channel (ADR 0003 — the publication is the sync security boundary).
This is a regression LOCK on the single-source allowlist
(`tests/_powersync_tables.py`): the table must be absent both from the Python
constant `PUBLISHED_TABLES` AND from the SQL `ARRAY[...]` block that the
publication declares. Runtime proof that the replication slot never carries it is
deferred to S13.7 (live PowerSync); this pins the declaration that gates it.
"""

from __future__ import annotations

from tests._powersync_tables import PUBLISHED_TABLES, publication_allowlist_from_sql

_TABLE = "sync_request_log"


def test_sync_request_log_absent_from_python_allowlist() -> None:
    assert _TABLE not in PUBLISHED_TABLES


def test_sync_request_log_absent_from_sql_publication() -> None:
    assert _TABLE not in publication_allowlist_from_sql()
