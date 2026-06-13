#!/usr/bin/env bash
# Tests unitaires de decide.sh (S18.1) : couvre les branches force-full + fail-safe + préséance
# + valeurs par défaut, en secondes, en local ET dans le job ci-selftest — donc AVANT merge.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
fail=0
tmp=""
trap 'rm -f "$tmp"' EXIT # cleanup même en cas d'interruption

# run EVENT F_BACKEND F_FRONTEND F_CI F_UNKNOWN → "<backend> <frontend>"
# Asserte AUSSI le contrat exit-code : un decide.sh qui sort ≠0 fait échouer le test.
run() {
  tmp="$(mktemp)"
  local rc=0
  EVENT="$1" F_BACKEND="$2" F_FRONTEND="$3" F_CI="$4" F_UNKNOWN="$5" \
    GITHUB_OUTPUT="$tmp" bash "$here/decide.sh" || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "FAIL run($*) : decide.sh a terminé en erreur (exit $rc)" >&2
    fail=1
    echo "ERR ERR" # force l'échec de l'assertion appelante
    rm -f "$tmp"
    return
  fi
  # awk (pas grep) → pas d'échec sous set -e si une ligne manque (le diagnostic vient de l'assert).
  printf '%s %s' \
    "$(awk -F= '/^backend=/{print $2}' "$tmp")" \
    "$(awk -F= '/^frontend=/{print $2}' "$tmp")"
  rm -f "$tmp"
}

chk() { # nom attendu obtenu
  if [ "$2" = "$3" ]; then
    echo "ok   $1"
  else
    echo "FAIL $1 : attendu [$2], obtenu [$3]"
    fail=1
  fi
}

# --- Force-full ---
chk "push main → full"            "true true"   "$(run push false false false false)"
chk "dispatch → full"             "true true"   "$(run workflow_dispatch false false false false)"
chk "ci change → full"            "true true"   "$(run pull_request false false true false)"
# --- Fail-safe (unknown) ---
chk "fail-safe unknown seul"      "true false"  "$(run pull_request false false false true)"
chk "mixte client + unknown"      "true true"   "$(run pull_request false true false true)"
# --- Skip / classés simples ---
chk "docs-only → skip tout"       "false false" "$(run pull_request false false false false)"
chk "backend-only"                "true false"  "$(run pull_request true false false false)"
chk "client-only"                 "false true"  "$(run pull_request false true false false)"
# --- Préséance de la cascade (elif) ---
chk "ci prime sur unknown"        "true true"   "$(run pull_request false false true true)"
chk "backend + unknown (fail-safe redondant)" "true false" "$(run pull_request true false false true)"
# --- Valeurs par défaut / entrée inconnue (sûreté : ne pas skipper) ---
chk "event inconnu → full"        "true true"   "$(run autre_event false false false false)"
chk "PR sans filtres (F vides) → skip" "false false" "$(run pull_request '' '' '' '')"

exit "$fail"
