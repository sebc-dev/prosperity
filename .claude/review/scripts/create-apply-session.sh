#!/usr/bin/env bash
set -euo pipefail

# Usage: create-apply-session.sh <source_session>
# source_session: completed review or followup session JSON
# Filters files with red/yellow observations, orders blocking-first,
# adds obs_index + apply_status per observation
# Stdout: JSON for the apply session (caller writes with Write)

source_session="${1:?Usage: create-apply-session.sh <source_session>}"

if [[ ! -f "$source_session" ]]; then
  echo "Error: source session not found: $source_session" >&2
  exit 1
fi

jq --arg src "$source_session" '
  # Extract files that have red or yellow observations
  [.files[] | select(
    (.observations // []) | any(.level == "red" or .level == "yellow")
  )] |

  # Sort: files with red (blocking) observations first, then by index
  sort_by(
    if ([.observations[] | select(.level == "red")] | length) > 0
    then 0
    else 1
    end,
    .index
  ) |

  # Build the apply session files array
  to_entries | map(
    .key as $file_idx |
    .value | {
      index: ($file_idx + 1),
      path: .path,
      category: .category,
      status: "pending",
      observations: (
        [.observations[] | select(.level == "red" or .level == "yellow")] |
        to_entries | map(
          .key as $obs_idx |
          .value + {
            obs_index: ($obs_idx + 1),
            apply_status: "pending",
            change_summary: null
          }
        )
      )
    }
  ) |

  # Count totals
  . as $files |
  [$files[].observations[]] as $all_obs |

  {
    type: "apply",
    source_session: $src,
    status: "in_progress",
    created_at: (now | strftime("%Y-%m-%dT%H:%M:%SZ")),
    summary: {
      total_observations: ($all_obs | length),
      applied: 0,
      skipped: 0,
      dismissed: 0,
      pending: ($all_obs | length)
    },
    files: $files
  }
' "$source_session"
