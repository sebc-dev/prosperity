"""Boot the REAL PowerSync Service against the sync rules (S13.7, P13.7.4).

This is the declarative anti-typo filet the plan calls for: PyYAML only proves the
manifest is well-formed YAML, but the sync rules are compiled by PowerSync's own
SQL engine — a bad column reference, a parameter a data query fails to cover, or a
table missing an `id` only surfaces there. So we boot the pinned
`journeyapps/powersync-service` image against a freshly migrated + published
Postgres, mounting the REAL `powersync/` config, seed a `personal_share_request`
debt, and assert:

- the service reaches `/probes/readiness` (replication caught up to a consistent
  checkpoint — which it CANNOT do if the snapshot of any published table fails),
- the replication engine started and `debts` replicated with NO Postgres error
  (PSYNC_S1120 / "permission denied" — the exact failure a column-level GRANT on
  `debts` would cause; here the table-level grant + column-list publication let
  the `SELECT *` snapshot run while keeping materialization_trace out of the
  stream),
- NO fatal sync-rule compilation error (bad parameter coverage / missing id /
  unknown column).

Heavy (boots two containers + a service) and Docker-gated, like the publication
test. The container plumbing is factored into `_powersync_service.py` so S13.8 /
E14 (client auth, upload handler) can reuse the same stack.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest

from tests.integration.sync._powersync_service import PowerSyncStack, docker_available

# Fatal sync-rule compiler messages (PowerSync refuses to deploy the rules). If
# any appears, the YAML is broken in a way PyYAML cannot see.
_FATAL_RULE_MARKERS = (
    "Fatal replication error",
    "must cover all bucket parameters",
    'must return an "id" column',
    "must return an id column",
)


@pytest.fixture(scope="module")
def booted_stack() -> Iterator[PowerSyncStack]:
    if not docker_available():
        pytest.skip("Docker unavailable — integration tier requires a Docker daemon")
    with PowerSyncStack() as stack:
        # A personal_share_request debt: debtor B owes creditor A, source account
        # owned by A. Gives `debts` + `share_requests` rows for the replicator to
        # snapshot (so a debts snapshot failure would surface here).
        stack.seed_personal_share_request_debt()
        stack.start_service()
        # Readiness = replication reached a consistent checkpoint over EVERY
        # published table. It cannot turn 200 if the debts snapshot errors.
        assert stack.wait_until_ready(timeout=180), (
            "PowerSync service never became ready — replication likely failed:\n"
            + stack.service_logs()[-4000:]
        )
        # Let a couple more replication ticks land in the logs.
        time.sleep(3)
        yield stack


def test_replication_engine_started_and_rules_compiled(booted_stack: PowerSyncStack) -> None:
    logs = booted_stack.service_logs()
    assert "Successfully started Replication Engine" in logs, (
        f"replication engine did not start:\n{logs[-4000:]}"
    )
    fatal = [m for m in _FATAL_RULE_MARKERS if m in logs]
    assert not fatal, f"sync rules failed to compile in the real engine ({fatal}):\n{logs[-4000:]}"


def test_debts_snapshot_has_no_postgres_permission_error(booted_stack: PowerSyncStack) -> None:
    # The regression this story is most exposed to at the replication layer: a
    # grant/publication combo that the snapshot `SELECT * FROM debts` cannot run.
    logs = booted_stack.service_logs()
    assert "PSYNC_S1120" not in logs, f"replication error while snapshotting:\n{logs[-4000:]}"
    assert "permission denied for table debts" not in logs, (
        f"powersync role cannot SELECT debts (grant/publication mismatch):\n{logs[-4000:]}"
    )


def test_no_server_only_table_replicated(booted_stack: PowerSyncStack) -> None:
    # The replicator only ever names PUBLISHED tables. A server-only table being
    # snapshotted ("Replicating ... admin_audit_logs") would mean the publication
    # boundary was breached. Cheap log-level cross-check of the SQL boundary.
    logs = booted_stack.service_logs()
    # The replicator logs `Replicating "public"."<table>"` for each published
    # table (quotes JSON-escaped as \"). A server-only table here = boundary breach.
    for forbidden in ("admin_audit_logs", "refresh_tokens", "sync_request_log", "settlements"):
        marker = f'Replicating \\"public\\".\\"{forbidden}\\"'
        assert marker not in logs, (
            f"server-only table {forbidden} is being replicated:\n{logs[-2000:]}"
        )
