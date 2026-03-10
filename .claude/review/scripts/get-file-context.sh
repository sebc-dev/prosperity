#!/usr/bin/env bash
set -euo pipefail

# Usage: get-file-context.sh <session> <path>
# Stdout: JSON compact of a single file's context (observations, note, counts, comments)

session="${1:?Usage: get-file-context.sh <session> <path>}"
filepath="${2:?Missing path}"

if [[ ! -f "$session" ]]; then
  echo "Error: session file not found: $session" >&2
  exit 1
fi

jq --arg p "$filepath" '
  .user_comments as $comments |
  (.files[] | select(.path == $p)) // null |
  if . == null then
    error("File not found in session: \($p)")
  else
    {
      path: .path,
      category: .category,
      green: .green,
      yellow: .yellow,
      red: .red,
      blocking: (.blocking // 0),
      note: (.note // ""),
      observations: (.observations // []),
      comments: [$comments[] | select(.file == $p) | .comment]
    }
  end
' "$session"
