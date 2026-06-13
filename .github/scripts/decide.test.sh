#!/usr/bin/env bash
# Tests unitaires de decide.sh (S18.1) : couvre les branches force-full + fail-safe, en
# secondes, en local ET dans le job ci-selftest — donc AVANT merge (pas seulement en prod CI).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
fail=0

# run EVENT F_BACKEND F_FRONTEND F_CI F_UNKNOWN → "<backend> <frontend>"
run() {
  local out
  out="$(mktemp)"
  EVENT="$1" F_BACKEND="$2" F_FRONTEND="$3" F_CI="$4" F_UNKNOWN="$5" \
    GITHUB_OUTPUT="$out" bash "$here/decide.sh"
  echo "$(grep '^backend=' "$out" | cut -d= -f2) $(grep '^frontend=' "$out" | cut -d= -f2)"
  rm -f "$out"
}

chk() { # nom attendu obtenu
  if [ "$2" = "$3" ]; then
    echo "ok   $1"
  else
    echo "FAIL $1 : attendu [$2], obtenu [$3]"
    fail=1
  fi
}

chk "push main → full"           "true true"   "$(run push false false false false)"
chk "dispatch → full"            "true true"   "$(run workflow_dispatch false false false false)"
chk "ci change → full"           "true true"   "$(run pull_request false false true false)"
chk "fail-safe unknown seul"     "true false"  "$(run pull_request false false false true)"
chk "mixte client + unknown"     "true true"   "$(run pull_request false true false true)"
chk "docs-only → skip tout"      "false false" "$(run pull_request false false false false)"
chk "backend-only"               "true false"  "$(run pull_request true false false false)"
chk "client-only"                "false true"  "$(run pull_request false true false false)"

exit "$fail"
