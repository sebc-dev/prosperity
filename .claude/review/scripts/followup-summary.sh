#!/usr/bin/env bash
set -euo pipefail

# Usage: followup-summary.sh <session>
# Generates markdown followup summary table, marks session completed with head_at_completion
# Stdout: markdown table ready to display

session="${1:?Usage: followup-summary.sh <session>}"

if [[ ! -f "$session" ]]; then
  echo "Error: session file not found: $session" >&2
  exit 1
fi

jq -r --arg g "🟢" --arg y "🟡" --arg r "🔴" '
  .branch as $branch |
  .round as $round |
  .summary as $s |

  "Recapitulatif du followup (round \($round)) — \($branch)\n",

  # Corrections section
  ([.files[] | select(.review_type == "correction")] | length) as $corr_count |
  if $corr_count > 0 then
    "### Corrections (\($corr_count) fichiers)\n",
    "| # | Fichier | Resolution | \($g) | \($y) | \($r) | Note originale |",
    "|---|---------|------------|-----|-----|-----|----------------|",
    ([.files[] | select(.review_type == "correction")] | sort_by(.index)[] |
      "| \(.index) | \(.path) | \(.resolution // "pending") | \(.green) | \(.yellow) | \(.red) | \(.original_note) |"
    ),
    ""
  else
    empty
  end,

  # Unaddressed section
  ([.files[] | select(.review_type == "unaddressed")] | length) as $unadr_count |
  if $unadr_count > 0 then
    "### Non adresses (\($unadr_count) fichiers)\n",
    "| # | Fichier | Resolution | Note originale |",
    "|---|---------|------------|----------------|",
    ([.files[] | select(.review_type == "unaddressed")] | sort_by(.index)[] |
      "| \(.index) | \(.path) | \(.resolution // "pending") | \(.original_note) |"
    ),
    ""
  else
    empty
  end,

  # New files section
  ([.files[] | select(.review_type == "new")] | length) as $new_count |
  if $new_count > 0 then
    "### Nouveaux fichiers (\($new_count) fichiers)\n",
    "| # | Fichier | Categorie | \($g) | \($y) | \($r) |",
    "|---|---------|-----------|-----|-----|-----|",
    ([.files[] | select(.review_type == "new")] | sort_by(.index)[] |
      "| \(.index) | \(.path) | \(.category) | \(.green) | \(.yellow) | \(.red) |"
    ),
    ""
  else
    empty
  end,

  "---",
  "Resume: \($s.resolved // 0) resolus, \($s.partially_resolved // 0) partiellement resolus, \($s.unresolved // 0) non resolus"
' "$session"

# Mark session as completed with head_at_completion
tmp="${session}.tmp"
head_sha=$(git rev-parse HEAD)
jq --arg h "$head_sha" '.status = "completed" | .head_at_completion = $h' "$session" > "$tmp" && mv "$tmp" "$session"
