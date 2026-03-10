#!/usr/bin/env bash
set -euo pipefail

# Usage: update-file.sh <session> <index> <green> <yellow> <red> "<note>" [blocking]
# Marks a file as completed and recalculates summary by aggregation
# 7th arg (blocking) is optional, defaults to 0 for retrocompatibility
# Stdout: updated summary JSON

session="${1:?Usage: update-file.sh <session> <index> <green> <yellow> <red> \"<note>\" [blocking]}"
index="${2:?Missing index}"
green="${3:?Missing green count}"
yellow="${4:?Missing yellow count}"
red="${5:?Missing red count}"
note="${6:?Missing note}"
blocking="${7:-0}"

if [[ ! -f "$session" ]]; then
  echo "Error: session file not found: $session" >&2
  exit 1
fi

tmp="${session}.tmp"
jq --argjson idx "$index" \
   --argjson g "$green" \
   --argjson y "$yellow" \
   --argjson r "$red" \
   --argjson b "$blocking" \
   --arg note "$note" '
  (.files[] | select(.index == $idx)) |= (
    .status = "completed" |
    .green = $g |
    .yellow = $y |
    .red = $r |
    .blocking = $b |
    .note = $note
  ) |
  .summary.completed = ([.files[] | select(.status == "completed")] | length) |
  .summary.green = ([.files[].green] | add // 0) |
  .summary.yellow = ([.files[].yellow] | add // 0) |
  .summary.red = ([.files[].red] | add // 0) |
  .summary.blocking = ([.files[].blocking // 0] | add // 0)
' "$session" > "$tmp" && mv "$tmp" "$session"

# Output the updated summary
jq '.summary' "$session"
