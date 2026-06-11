#!/usr/bin/env bash
# smoke_powersync.sh — verify the dev PowerSync stack is actually wired up.
#
# Asserts the three runtime acceptance criteria of S13.1 (the riskiest part of
# E13): Postgres runs with wal_level=logical, an active replication slot exists
# for PowerSync, and the PowerSync Service reports ready ("connected").
#
# Assumes `compose.dev.yml` is already up AND the documented setup sequence has
# run (alembic upgrade head + 10_powersync_publication.sql); see
# runbooks/powersync_setup.md. Runs locally (Podman) and in nightly CI (Docker).
#
# Usage:
#   bash scripts/smoke_powersync.sh
# Env overrides:
#   COMPOSE      compose command (default: auto-detect podman/docker)
#   COMPOSE_FILE compose file     (default: compose.dev.yml)
#   PS_PORT      PowerSync port    (default: from .env or 8080)

set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-compose.dev.yml}"

# Pick a compose engine: explicit override > podman > docker.
if [[ -n "${COMPOSE:-}" ]]; then
  read -r -a COMPOSE_CMD <<<"${COMPOSE}"
elif command -v podman >/dev/null 2>&1; then
  COMPOSE_CMD=(podman compose)
elif command -v docker >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
else
  echo "FAIL: neither podman nor docker found" >&2
  exit 1
fi

# Load .env so PS_PORT / PG creds are available to this script (compose loads it
# on its own).
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
PS_PORT="${PS_PORT:-8080}"

compose() { "${COMPOSE_CMD[@]}" -f "${COMPOSE_FILE}" "$@"; }

psql_source() {
  # Run psql inside the postgres container against the source DB.
  compose exec -T postgres psql -tA -U prosperity -d prosperity -c "$1"
}

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

poll_probe() {
  # Poll an HTTP probe for up to ~60s — both liveness and readiness can lag a
  # cold boot, so neither is a one-shot.
  local path="$1"
  for _ in $(seq 1 30); do
    if curl -fsS "http://localhost:${PS_PORT}${path}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

echo "==> 1/4 wal_level is logical"
wal_level="$(psql_source 'SHOW wal_level;' | tr -d '[:space:]')"
[[ "${wal_level}" == "logical" ]] || fail "wal_level=${wal_level} (expected logical)"
echo "    ok: wal_level=logical"

echo "==> 2/4 active replication slot for PowerSync"
# PowerSync creates a pgoutput logical slot once it connects. Poll briefly: the
# replication worker may still be connecting right after boot.
slot_ok=""
for _ in $(seq 1 30); do
  slots="$(psql_source "SELECT slot_name, plugin, active FROM pg_replication_slots WHERE plugin='pgoutput' AND active;")"
  if [[ -n "${slots}" ]]; then
    slot_ok="yes"
    echo "    ok: ${slots}"
    break
  fi
  sleep 2
done
[[ -n "${slot_ok}" ]] || fail "no active pgoutput replication slot (PowerSync not replicating)"

echo "==> 3/4 PowerSync liveness probe"
poll_probe /probes/liveness || fail "liveness probe not 2xx on :${PS_PORT}"
echo "    ok: /probes/liveness"

echo "==> 4/4 PowerSync readiness probe (connected to source + storage)"
poll_probe /probes/readiness || fail "readiness probe not 2xx on :${PS_PORT} (not connected)"
echo "    ok: /probes/readiness"

echo "PASS: PowerSync connected to Postgres, replication slot active, state published."
