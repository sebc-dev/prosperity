#!/usr/bin/env bash
set -euo pipefail

# Usage: update-validation.sh <session-path> <file-path> <decisions-json>
# Enriches each observation of the given file with .validation = {decision, confidence, reason}
# decisions-json: JSON array of [{index, decision, confidence, reason}]
# Indexes are 0-based positions in the observations array of the file
# Stdout: updated summary.validation JSON

session="${1:?Usage: update-validation.sh <session-path> <file-path> <decisions-json>}"
file_path="${2:?Missing file-path}"
decisions="${3:?Missing decisions-json}"

if [[ ! -f "$session" ]]; then
  echo "Error: session file not found: $session" >&2
  exit 1
fi

tmp="${session}.tmp"
jq --arg file "$file_path" \
   --argjson decisions "$decisions" '

  # Apply validation to each observation in the matching file
  (.files[] | select(.path == $file)).observations |=
    [to_entries[] | .value as $obs | .key as $idx |
      ($decisions[] | select(.index == $idx)) as $dec |
      if $dec then
        $obs + {"validation": {"decision": $dec.decision, "confidence": $dec.confidence, "reason": $dec.reason}}
      else
        $obs
      end
    ] |

  # Aggregate validation summary across all files
  [.files[].observations[] | .validation? // empty] as $vals |
  .summary.validation = {
    "apply": ([$vals[] | select(.decision == "apply")] | length),
    "skip": ([$vals[] | select(.decision == "skip")] | length),
    "escalate": ([$vals[] | select(.decision == "escalate")] | length),
    "total": ($vals | length)
  }

' "$session" > "$tmp" && mv "$tmp" "$session"

jq '.summary.validation' "$session"
