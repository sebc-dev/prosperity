#!/usr/bin/env bash
set -euo pipefail

# Usage: update-followup-file.sh <session> <index> <green> <yellow> <red> "<note>" "<resolution>"
# resolution: resolved | partially_resolved | unresolved | null (for new files)
# Marks a file as completed and recalculates followup summary
# Stdout: updated summary JSON

session="${1:?Usage: update-followup-file.sh <session> <index> <green> <yellow> <red> \"<note>\" \"<resolution>\"}"
index="${2:?Missing index}"
green="${3:?Missing green count}"
yellow="${4:?Missing yellow count}"
red="${5:?Missing red count}"
note="${6:?Missing note}"
resolution="${7:?Missing resolution}"

if [[ ! -f "$session" ]]; then
  echo "Error: session file not found: $session" >&2
  exit 1
fi

# Handle "null" string as actual null
if [[ "$resolution" == "null" ]]; then
  res_arg="null"
else
  res_arg="\"$resolution\""
fi

tmp="${session}.tmp"
jq --argjson idx "$index" \
   --argjson g "$green" \
   --argjson y "$yellow" \
   --argjson r "$red" \
   --arg note "$note" \
   --argjson res "$res_arg" '
  (.files[] | select(.index == $idx)) |= (
    .status = "completed" |
    .green = $g |
    .yellow = $y |
    .red = $r |
    .note = $note |
    .resolution = $res
  ) |
  .summary.completed = ([.files[] | select(.status == "completed")] | length) |
  .summary.resolved = ([.files[] | select(.resolution == "resolved" or .resolution == "auto_resolved_deleted")] | length) |
  .summary.partially_resolved = ([.files[] | select(.resolution == "partially_resolved")] | length) |
  .summary.unresolved = ([.files[] | select(.resolution == "unresolved")] | length) |
  .summary.new_green = ([.files[] | select(.review_type == "new") | .green] | add // 0) |
  .summary.new_yellow = ([.files[] | select(.review_type == "new") | .yellow] | add // 0) |
  .summary.new_red = ([.files[] | select(.review_type == "new") | .red] | add // 0)
' "$session" > "$tmp" && mv "$tmp" "$session"

jq '.summary' "$session"
