#!/usr/bin/env bash
set -euo pipefail

# Usage: session-summary.sh <session>
# Generates markdown summary table, lists comments, marks session completed
# Stdout: markdown table ready to display

session="${1:?Usage: session-summary.sh <session>}"

if [[ ! -f "$session" ]]; then
  echo "Error: session file not found: $session" >&2
  exit 1
fi

# Generate the summary output
jq -r --arg g "🟢" --arg y "🟡" --arg r "🔴" '
  .branch as $branch |
  .summary as $s |

  "Recapitulatif de la review — \($branch)\n",
  "| # | Fichier | Categorie | \($g) | \($y) | \($r) | B |",
  "|---|---------|-----------|-----|-----|-----|---|",
  (.files[] |
    "| \(.index) | \(.path) | \(.category) | \(.green) | \(.yellow) | \(.red) | \(.blocking // 0) |"
  ),
  "|   | **TOTAL** |           | **\($s.green)** | **\($s.yellow)** | **\($s.red)** | **\($s.blocking // 0)** |",
  "",
  if (.user_comments | length) > 0 then
    "### Commentaires\n",
    (.user_comments[] | "- **\(.file)** : \(.comment)")
  else
    empty
  end
' "$session"

# Mark session as completed with head_at_completion (atomic write)
tmp="${session}.tmp"
head_sha=$(git rev-parse HEAD)
jq --arg h "$head_sha" '.status = "completed" | .head_at_completion = $h' "$session" > "$tmp" && mv "$tmp" "$session"
