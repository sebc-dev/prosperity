#!/usr/bin/env bash
set -euo pipefail

# Usage: echo '<observations_json_array>' | add-observations.sh <session> <index>
# Stdin: JSON array of observations [{"criterion":"...","severity":"...","level":"...","text":"..."}]
# Writes observations into the file at the given index
# Stdout: number of observations added

session="${1:?Usage: echo '<json>' | add-observations.sh <session> <index>}"
index="${2:?Missing index}"

if [[ ! -f "$session" ]]; then
  echo "Error: session file not found: $session" >&2
  exit 1
fi

# Read observations from stdin
obs=$(cat)

if [[ -z "$obs" ]] || ! echo "$obs" | jq empty 2>/dev/null; then
  echo "Error: invalid JSON on stdin" >&2
  exit 1
fi

tmp="${session}.tmp"
jq --argjson idx "$index" --argjson obs "$obs" '
  (.files[] | select(.index == $idx)).observations = $obs
' "$session" > "$tmp" && mv "$tmp" "$session"

echo "$obs" | jq 'length'
