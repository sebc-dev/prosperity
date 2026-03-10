#!/usr/bin/env bash
set -euo pipefail

# Usage: apply-summary.sh <session>
# Generates markdown recap table, marks session completed + completed_at
# Stdout: markdown table ready to display

session="${1:?Usage: apply-summary.sh <session>}"

if [[ ! -f "$session" ]]; then
  echo "Error: session file not found: $session" >&2
  exit 1
fi

jq -r '
  .summary as $s |

  "Recapitulatif apply\n",
  "| # | Fichier | Obs | Appliquees | Sautees | Rejetees |",
  "|---|---------|-----|------------|---------|----------|",
  (.files[] |
    (.observations | length) as $total |
    ([.observations[] | select(.apply_status == "applied")] | length) as $app |
    ([.observations[] | select(.apply_status == "skipped" or .apply_status == "skipped_ambiguous")] | length) as $skip |
    ([.observations[] | select(.apply_status == "dismissed")] | length) as $dis |
    "| \(.index) | \(.path) | \($total) | \($app) | \($skip) | \($dis) |"
  ),
  "|   | **TOTAL** | **\($s.total_observations)** | **\($s.applied)** | **\($s.skipped)** | **\($s.dismissed)** |",
  "",

  # List skipped observations
  if ([.files[].observations[] | select(.apply_status == "skipped" or .apply_status == "skipped_ambiguous")] | length) > 0 then
    "### Observations sautees\n",
    ([.files[] |
      .path as $p |
      .observations[] | select(.apply_status == "skipped" or .apply_status == "skipped_ambiguous") |
      "- `\($p)` — \(.level) **\(.criterion)** : \(.text)"
    ] | .[]),
    ""
  else
    empty
  end,

  # List dismissed observations
  if ([.files[].observations[] | select(.apply_status == "dismissed")] | length) > 0 then
    "### Observations rejetees (faux positifs)\n",
    ([.files[] |
      .path as $p |
      .observations[] | select(.apply_status == "dismissed") |
      "- `\($p)` — \(.level) **\(.criterion)** : \(.text)"
    ] | .[]),
    ""
  else
    empty
  end,

  "---",
  "\($s.applied) corrections appliquees, \($s.skipped) sautees, \($s.dismissed) rejetees sur \($s.total_observations) observations.",
  "",
  if ($s.skipped + $s.dismissed) > 0 then
    "Lancez `/scd-review:review-followup` pour verifier les corrections appliquees."
  else
    "Toutes les observations ont ete traitees. Lancez `/scd-review:review-followup` pour valider."
  end
' "$session"

# Mark session as completed
tmp="${session}.tmp"
jq '.status = "completed" | .completed_at = (now | strftime("%Y-%m-%dT%H:%M:%SZ"))' "$session" > "$tmp" && mv "$tmp" "$session"
