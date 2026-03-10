#!/usr/bin/env bash
set -euo pipefail

# Usage: auto-report.sh <session-slug> <sessions-dir>
# Consolidates review + validation + apply + followup sessions into a JSON + markdown report
# Reads: <slug>.json, <slug>-apply.json, <slug>-followup.json (all optional except review)
# Stdout: JSON report with embedded markdown

slug="${1:?Usage: auto-report.sh <session-slug> <sessions-dir>}"
sessions_dir="${2:?Missing sessions-dir}"

review_session="${sessions_dir}/${slug}.json"
apply_session="${sessions_dir}/${slug}-apply.json"
followup_session="${sessions_dir}/${slug}-followup.json"

if [[ ! -f "$review_session" ]]; then
  echo "Error: review session not found: $review_session" >&2
  exit 1
fi

has_apply="false"
has_followup="false"
[[ -f "$apply_session" ]] && has_apply="true"
[[ -f "$followup_session" ]] && has_followup="true"

# Build consolidated report using jq
# Careful: apply session uses .files[].observations[] with .apply_status (not .status)
jq -n \
  --slurpfile review "$review_session" \
  --argjson has_apply "$has_apply" \
  --argjson has_followup "$has_followup" \
  --arg apply_path "$apply_session" \
  --arg followup_path "$followup_session" \
  --arg slug "$slug" '

  $review[0] as $rev |

  # Review stats
  ($rev.summary) as $rev_summary |
  ($rev.files | length) as $total_files |
  [$rev.files[].observations[]] as $all_obs |
  ($all_obs | length) as $total_obs |
  ([$all_obs[] | select(.level == "red")] | length) as $blocking_obs |

  # Validation stats (from review session observations)
  ([$all_obs[] | select(.validation != null)] | length) as $validated_count |
  ([$all_obs[] | select(.validation.decision == "apply")] | length) as $val_apply |
  ([$all_obs[] | select(.validation.decision == "skip")] | length) as $val_skip |
  ([$all_obs[] | select(.validation.decision == "escalate")] | length) as $val_escalate |

  # Escalations detail
  [$rev.files[] | .path as $fp | .observations[] |
    select(.validation.decision == "escalate") |
    {file: $fp, criterion, level, text, reason: .validation.reason}
  ] as $escalations |

  # Apply stats (if exists) — uses .files[].observations[].apply_status
  (if $has_apply then
    (input | . as $app |
      {
        total: [$app.files[].observations[]] | length,
        applied: [[$app.files[].observations[]] | .[] | select(.apply_status == "applied")] | length,
        skipped: [[$app.files[].observations[]] | .[] | select(.apply_status == "skipped" or .apply_status == "skipped_ambiguous")] | length,
        dismissed: [[$app.files[].observations[]] | .[] | select(.apply_status == "dismissed")] | length,
        applied_files: [$app.files[] | select([.observations[] | select(.apply_status == "applied")] | length > 0) | .path]
      }
    )
  else
    {total: 0, applied: 0, skipped: 0, dismissed: 0, applied_files: []}
  end) as $apply_stats |

  # Followup stats (if exists)
  (if $has_followup then
    (input | . as $fu |
      {
        resolved: ($fu.summary.resolved // 0),
        partially: ($fu.summary.partially_resolved // 0),
        unresolved: ($fu.summary.unresolved // 0)
      }
    )
  else
    {resolved: 0, partially: 0, unresolved: 0}
  end) as $followup_stats |

  # Verdict
  (if ($val_escalate == 0) and ($apply_stats.skipped == 0 or $blocking_obs == 0) and
      ($followup_stats.unresolved == 0) and ($followup_stats.partially == 0)
   then "ready_to_merge"
   elif ($val_escalate > 0) or ($apply_stats.skipped > 0)
   then "attention_required"
   else "blocked"
   end) as $verdict |

  {
    slug: $slug,
    branch: $rev.branch,
    base: $rev.base,
    generated_at: (now | strftime("%Y-%m-%dT%H:%M:%SZ")),
    review: {
      total_files: $total_files,
      total_observations: $total_obs,
      blocking: $blocking_obs,
      green: $rev_summary.green,
      yellow: $rev_summary.yellow,
      red: $rev_summary.red
    },
    validation: {
      validated: $validated_count,
      apply: $val_apply,
      skip: $val_skip,
      escalate: $val_escalate,
      escalations: $escalations
    },
    apply: $apply_stats,
    followup: $followup_stats,
    verdict: $verdict
  }

' $(if [[ "$has_apply" == "true" ]]; then echo "$apply_session"; fi) \
  $(if [[ "$has_followup" == "true" ]]; then echo "$followup_session"; fi)
