#!/usr/bin/env bash
set -euo pipefail

# Usage: add-comment.sh <session> "<file_path>" "<comment>"
# Appends a comment to user_comments
# Stdout: comment count after addition

session="${1:?Usage: add-comment.sh <session> \"<file_path>\" \"<comment>\"}"
file_path="${2:?Missing file_path}"
comment="${3:?Missing comment}"

if [[ ! -f "$session" ]]; then
  echo "Error: session file not found: $session" >&2
  exit 1
fi

tmp="${session}.tmp"
jq --arg f "$file_path" --arg c "$comment" '
  .user_comments += [{"file": $f, "comment": $c}] |
  (.user_comments | length)
' "$session" > "$tmp"

# Extract count before overwriting
count=$(cat "$tmp")

# Write full updated session
jq --arg f "$file_path" --arg c "$comment" '
  .user_comments += [{"file": $f, "comment": $c}]
' "$session" > "$tmp" && mv "$tmp" "$session"

echo "$count"
