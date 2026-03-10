#!/usr/bin/env bash
set -euo pipefail

# Usage: post-inline-comments.sh <session> <config> [filter]
# Posts observations as inline PR/MR comments (1 per observation)
# Complements post-review-comments.sh (summary comment) — does not replace it
# Filters: blocking (default), all, red, yellow
# GitHub: 1 batch review with all comments via /reviews
# GitLab: 1 discussion per observation via /discussions
# Stdout: POSTED/SKIP/WARN message
# Exit 0 always (never blocks the review)

session="${1:?Usage: post-inline-comments.sh <session> <config> [filter]}"
config="${2:?Usage: post-inline-comments.sh <session> <config> [filter]}"
filter="${3:-blocking}"

case "$filter" in
  blocking|all|red|yellow) ;;
  *) echo "WARN: unknown filter '$filter' (valid: blocking, all, red, yellow)"; exit 0 ;;
esac

if [[ ! -f "$session" ]]; then echo "WARN: session not found: $session"; exit 0; fi
if [[ ! -f "$config" ]]; then echo "WARN: config not found: $config"; exit 0; fi

# Platform config
platform_type=$(jq -r '.platform.type // empty' "$config" 2>/dev/null || true)
if [[ -z "$platform_type" || "$platform_type" == "null" ]]; then
  echo "SKIP: platform not configured"; exit 0
fi

if [[ "$platform_type" == "github" ]]; then
  command -v gh &>/dev/null || { echo "WARN: gh CLI not found. Install: https://cli.github.com"; exit 0; }
elif [[ "$platform_type" == "gitlab" ]]; then
  command -v glab &>/dev/null || { echo "WARN: glab CLI not found. Install: https://gitlab.com/gitlab-org/cli"; exit 0; }
else
  echo "WARN: unknown platform: $platform_type"; exit 0
fi

# Branch + PR/MR detection
branch=$(git branch --show-current 2>/dev/null || true)
[[ -z "$branch" ]] && { echo "SKIP: not on a branch (detached HEAD?)"; exit 0; }

pr_number=""
if [[ "$platform_type" == "github" ]]; then
  pr_number=$(gh pr list --head "$branch" --json number --jq '.[0].number' 2>/dev/null || true)
elif [[ "$platform_type" == "gitlab" ]]; then
  pr_number=$(glab mr list --source-branch "$branch" -o json 2>/dev/null | jq -r '.[0].iid // empty' 2>/dev/null || true)
fi
[[ -z "$pr_number" ]] && { echo "SKIP: no open PR/MR for branch $branch"; exit 0; }

lang=$(jq -r '.options.language // "fr"' "$config" 2>/dev/null || echo "fr")
ai_fix_prompt=$(jq -r '.platform.inline_comments.ai_fix_prompt // false' "$config" 2>/dev/null || echo "false")

# ---------------------------------------------------------------------------
# Extract filtered observations with resolved line numbers
# Line resolution priority:
#   1. location field with :NN (structured field from code-reviewer/test-reviewer)
#   2. diff_position.new_line  (future enrichment)
#   3. :NN pattern in text/detail (e.g. "UserService.java:92")
#   4. :NN-MM range — takes start line (e.g. ":38-61" → 38)
#   5. "line NN" / "ligne NN" in text/detail
#   6. fallback: 1 (known limitation — see ARCHITECTURE.md)
# ---------------------------------------------------------------------------
observations=$(jq --arg filter "$filter" '
  [.files[] | .path as $path | .observations[] |
    # Apply severity filter
    if $filter == "blocking" then select(.severity == "bloquant")
    elif $filter == "red" then select(.level == "red")
    elif $filter == "yellow" then select(.level == "yellow")
    else . end |

    # Resolve line number (best effort)
    ((.text // "") + " " + (.detail // "")) as $content |
    (
      if (.location // null) and ((.location | tostring) | test(":[0-9]+")) then
        {n: ((.location | tostring) | capture(":(?<n>[0-9]+)") | .n | tonumber), resolved: true}
      elif .diff_position.new_line then
        {n: .diff_position.new_line, resolved: true}
      elif ($content | test(":[0-9]+")) then
        {n: ($content | capture(":(?<n>[0-9]+)") | .n | tonumber), resolved: true}
      elif ($content | test("(?:line|ligne)\\s+[0-9]+"; "i")) then
        {n: ($content | capture("(?:line|ligne)\\s+(?<n>[0-9]+)"; "i") | .n | tonumber), resolved: true}
      else
        {n: 1, resolved: false}
      end
    ) as $ln |

    {
      path: $path,
      line: $ln.n,
      line_resolved: $ln.resolved,
      level: .level,
      criterion: .criterion,
      severity: .severity,
      text: .text,
      detail: (.detail // ""),
      suggestion: (.suggestion // null),
      fix_prompt: (.fix_prompt // null)
    }
  ]
' "$session")

obs_count=$(echo "$observations" | jq 'length')
if [[ "$obs_count" -eq 0 ]]; then
  echo "SKIP: no observations match filter '$filter'"
  exit 0
fi

resolved_count=$(echo "$observations" | jq '[.[] | select(.line_resolved)] | length')
fallback_count=$((obs_count - resolved_count))
echo "INFO: $obs_count observation(s) — $resolved_count with precise line, $fallback_count fallback to line 1"

# ---------------------------------------------------------------------------
# Comment body builder (shared jq fragment)
# Format: emoji [TAG] — title \n detail \n > suggestion
# ---------------------------------------------------------------------------
body_jq='
  (if .level == "red" then "🔴"
   elif .level == "yellow" then "🟡"
   else "🟢" end) as $emoji |
  (if .severity == "bloquant" then
     (if $lang == "en" then " [BLOCKING]" else " [BLOQUANT]" end)
   else "" end) as $tag |
  (if .suggestion then
     (if $lang == "en" then "\n\n> 💡 **Suggestion**: " else "\n\n> 💡 **Suggestion** : " end) + .suggestion
   else "" end) as $sug |
  (if ($ai_fix == "true") and .fix_prompt then
     "\n\n<details>\n<summary>🤖 AI Fix</summary>\n\n```ai-fix\nfile: \(.fix_prompt.file)\nline: \(.fix_prompt.line)\naction: \(.fix_prompt.action)\ndescription: \(.fix_prompt.description)\n```\n\n</details>"
   else "" end) as $ai |
  "\($emoji) **\(.criterion)**\($tag) — \(.text)\n\n\(.detail)\($sug)\($ai)"
'

# ---------------------------------------------------------------------------
# GitHub — batch review with all inline comments
# Uses subject_type "file" when line not resolved (avoids 422 errors)
# Falls back to individual comments if batch fails
# ---------------------------------------------------------------------------
if [[ "$platform_type" == "github" ]]; then
  payload=$(echo "$observations" | jq --arg lang "$lang" --arg ai_fix "$ai_fix_prompt" '
    {
      event: "COMMENT",
      body: "",
      comments: [.[] |
        (if .level == "red" then "🔴"
         elif .level == "yellow" then "🟡"
         else "🟢" end) as $emoji |
        (if .severity == "bloquant" then
           (if $lang == "en" then " [BLOCKING]" else " [BLOQUANT]" end)
         else "" end) as $tag |
        (if .suggestion then
           (if $lang == "en" then "\n\n> 💡 **Suggestion**: " else "\n\n> 💡 **Suggestion** : " end) + .suggestion
         else "" end) as $sug |
        (if ($ai_fix == "true") and .fix_prompt then
           "\n\n<details>\n<summary>🤖 AI Fix</summary>\n\n```ai-fix\nfile: \(.fix_prompt.file)\nline: \(.fix_prompt.line)\naction: \(.fix_prompt.action)\ndescription: \(.fix_prompt.description)\n```\n\n</details>"
         else "" end) as $ai |
        {
          path: .path,
          body: "\($emoji) **\(.criterion)**\($tag) — \(.text)\n\n\(.detail)\($sug)\($ai)"
        } + (if .line_resolved then
          {line: .line, side: "RIGHT"}
        else
          {subject_type: "file"}
        end)
      ]
    }
  ')

  result=$(echo "$payload" | gh api "repos/{owner}/{repo}/pulls/$pr_number/reviews" \
    --method POST --input - 2>&1 || true)

  if echo "$result" | jq -e '.id' &>/dev/null 2>&1; then
    echo "POSTED: $obs_count inline comment(s) on PR #$pr_number"
  else
    # Batch failed — retry one by one, skip invalid lines
    posted=0
    failed=0
    while IFS= read -r comment_json; do
      single=$(jq -n --argjson c "$comment_json" '{event: "COMMENT", body: "", comments: [$c]}')
      if echo "$single" | gh api "repos/{owner}/{repo}/pulls/$pr_number/reviews" \
        --method POST --input - &>/dev/null 2>&1; then
        posted=$((posted + 1))
      else
        failed=$((failed + 1))
      fi
    done < <(echo "$payload" | jq -c '.comments[]')

    if [[ "$posted" -gt 0 ]]; then
      msg="POSTED: $posted/$obs_count inline comment(s) on PR #$pr_number"
      [[ "$failed" -gt 0 ]] && msg="$msg ($failed skipped — line not in diff?)"
      echo "$msg"
    else
      echo "WARN: failed to post inline comments on PR #$pr_number"
    fi
  fi

# ---------------------------------------------------------------------------
# GitLab — 1 discussion per observation via /discussions
# Uses diff_refs (base, start, head SHA) for positioned comments
# Falls back to non-positioned discussion if inline fails
# ---------------------------------------------------------------------------
elif [[ "$platform_type" == "gitlab" ]]; then
  # Resolve project path for API
  remote_url=$(git remote get-url origin 2>/dev/null || true)
  project_path=$(echo "$remote_url" | sed -E 's|^(https?://[^/]+/|git@[^:]+:)||; s|\.git$||')
  encoded_project=$(echo "$project_path" | sed 's|/|%2F|g')

  # Fetch diff_refs from MR
  mr_json=$(glab api "projects/$encoded_project/merge_requests/$pr_number" 2>/dev/null || true)
  base_sha=$(echo "$mr_json" | jq -r '.diff_refs.base_sha // empty' 2>/dev/null || true)
  start_sha=$(echo "$mr_json" | jq -r '.diff_refs.start_sha // empty' 2>/dev/null || true)
  head_sha=$(echo "$mr_json" | jq -r '.diff_refs.head_sha // empty' 2>/dev/null || true)

  if [[ -z "$base_sha" || -z "$head_sha" ]]; then
    echo "WARN: could not retrieve diff_refs for MR !$pr_number"
    exit 0
  fi
  [[ -z "$start_sha" ]] && start_sha="$base_sha"

  posted=0
  failed=0

  while IFS= read -r obs; do
    path=$(echo "$obs" | jq -r '.path')
    line=$(echo "$obs" | jq '.line')
    body=$(echo "$obs" | jq -r --arg lang "$lang" --arg ai_fix "$ai_fix_prompt" "
      $body_jq
    ")

    # Build positioned discussion payload
    discussion_payload=$(jq -n \
      --arg body "$body" \
      --arg base "$base_sha" \
      --arg start "$start_sha" \
      --arg head "$head_sha" \
      --arg new_path "$path" \
      --argjson new_line "$line" \
      '{
        body: $body,
        position: {
          base_sha: $base,
          start_sha: $start,
          head_sha: $head,
          position_type: "text",
          new_path: $new_path,
          new_line: $new_line
        }
      }')

    # Try inline first, fall back to non-positioned discussion
    if echo "$discussion_payload" | glab api "projects/$encoded_project/merge_requests/$pr_number/discussions" \
      --method POST --input - 2>/dev/null | jq -e '.id' &>/dev/null; then
      posted=$((posted + 1))
    else
      fallback=$(jq -n --arg body "$body" '{body: $body}')
      if echo "$fallback" | glab api "projects/$encoded_project/merge_requests/$pr_number/discussions" \
        --method POST --input - 2>/dev/null | jq -e '.id' &>/dev/null; then
        posted=$((posted + 1))
      else
        failed=$((failed + 1))
      fi
    fi
  done < <(echo "$observations" | jq -c '.[]')

  if [[ "$posted" -gt 0 ]]; then
    msg="POSTED: $posted inline discussion(s) on MR !$pr_number"
    [[ "$failed" -gt 0 ]] && msg="$msg ($failed failed)"
    echo "$msg"
  else
    echo "WARN: all $obs_count discussion(s) failed for MR !$pr_number"
  fi
fi

exit 0
