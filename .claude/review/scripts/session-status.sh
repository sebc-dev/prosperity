#!/usr/bin/env bash
set -euo pipefail

# Usage: session-status.sh <session>
# Read-only status output for display
# Stdout: plain text status report

session="${1:?Usage: session-status.sh <session>}"

if [[ ! -f "$session" ]]; then
  echo "Error: session file not found: $session" >&2
  exit 1
fi

jq -r '
  .summary.total_files as $total |
  "branch: \(.branch)",
  "base: \(.base)",
  "status: \(.status)",
  "completed: \(.summary.completed)/\($total)",
  "green: \(.summary.green) yellow: \(.summary.yellow) red: \(.summary.red)",
  (
    [.files[] | select(.status == "completed")] |
    if length > 0 then
      "files_done:",
      (.[] | "  \(.index)/\($total) \(.path) [\(.category)] — \(.note)")
    else
      "files_done: (none)"
    end
  ),
  (
    [.files[] | select(.status == "pending")] |
    if length > 0 then
      "next: \(.[0].index)/\($total) \(.[0].path) [\(.[0].category)]"
    else
      "next: (all files completed)"
    end
  )
' "$session"
