#!/usr/bin/env bash
set -euo pipefail

# Usage: update-apply-observation.sh <session> <file_index> <obs_index> "<status>" ["<change_summary>"]
# status: applied | skipped | dismissed | skipped_ambiguous
# Updates one observation, marks file completed if all obs treated, recalculates summary
# Stdout: updated summary JSON

session="${1:?Usage: update-apply-observation.sh <session> <file_index> <obs_index> \"<status>\" [\"<change_summary>\"]}"
file_index="${2:?Missing file_index}"
obs_index="${3:?Missing obs_index}"
status="${4:?Missing status}"
change_summary="${5:-}"

if [[ ! -f "$session" ]]; then
  echo "Error: session file not found: $session" >&2
  exit 1
fi

tmp="${session}.tmp"
jq --argjson fidx "$file_index" \
   --argjson oidx "$obs_index" \
   --arg st "$status" \
   --arg cs "$change_summary" '

  # Update the specific observation
  (.files[] | select(.index == $fidx)).observations |=
    map(if .obs_index == $oidx then
      .apply_status = $st |
      .change_summary = (if $cs == "" then null else $cs end)
    else . end) |

  # Mark file completed if all observations are treated
  (.files[] | select(.index == $fidx)) |=
    if ([.observations[] | select(.apply_status == "pending")] | length) == 0
    then .status = "completed"
    else .
    end |

  # Recalculate summary from all observations
  [.files[].observations[]] as $all |
  .summary.applied = ([$all[] | select(.apply_status == "applied")] | length) |
  .summary.skipped = ([$all[] | select(.apply_status == "skipped" or .apply_status == "skipped_ambiguous")] | length) |
  .summary.dismissed = ([$all[] | select(.apply_status == "dismissed")] | length) |
  .summary.pending = ([$all[] | select(.apply_status == "pending")] | length)

' "$session" > "$tmp" && mv "$tmp" "$session"

jq '.summary' "$session"
