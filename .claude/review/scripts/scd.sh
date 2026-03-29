#!/usr/bin/env bash
set -euo pipefail

# scd.sh — scd-review unified dispatcher v2.0.0
# Usage: scd.sh <domain> <action> [args...]
#
# Domains:
#   session    status | update-file | add-observations | add-comment | add-agent-tasks | summary | pending-files
#   followup   classify | get-context | update-file | summary
#   post       inline-comments | orphan-summary
#   validation update | report
#   context    resolve | clear
#   agent      capture-output | validate-output
#   test       run-affected
#   init       detect-env
#   config     update-state | get | resolve-model

# ── Helpers ──────────────────────────────────────────────────────────────────

_check_session() {
  [[ -f "${1:?Missing session path}" ]] || { echo "Error: session file not found: $1" >&2; exit 1; }
}

_check_config() {
  [[ -f "${1:?Missing config path}" ]] || { echo "Error: config file not found: $1" >&2; exit 1; }
}

_atomic_jq() {
  # _atomic_jq <file> [jq-args...] '<filter>'
  local file="$1"; shift
  local tmp="${file}.tmp"
  jq "$@" "$file" > "$tmp" && mv "$tmp" "$file"
}

# ── Domain: session ───────────────────────────────────────────────────────────

cmd_session() {
  local action="${1:?Usage: scd.sh session <action> [args...]}"; shift
  case "$action" in
    status)           _session_status "$@" ;;
    update-file)      _session_update_file "$@" ;;
    add-observations) _session_add_observations "$@" ;;
    add-comment)      _session_add_comment "$@" ;;
    add-agent-tasks)  _session_add_agent_tasks "$@" ;;
    summary)          _session_summary "$@" ;;
    pending-files)    _session_pending_files "$@" ;;
    *) echo "Error: unknown session action: $action" >&2; exit 1 ;;
  esac
}

_session_status() {
  local session="${1:?Usage: scd.sh session status <session>}"
  _check_session "$session"
  jq -r '
    .summary.total_files as $total |
    "branch: \(.branch)",
    "base: \(.base_branch // .base)",
    "status: \(.status)",
    "completed: \(.summary.completed // 0)/\($total)",
    "green: \(.summary.green // 0) yellow: \(.summary.yellow // 0) red: \(.summary.red // 0)",
    (
      [.files[] | select(.status == "completed")] |
      if length > 0 then
        "files_done:",
        (.[] | "  \(.index)/\($total) \(.path) [\(.category)] — \(.note // "")")
      else "files_done: (none)" end
    ),
    (
      [.files[] | select(.status == "pending")] |
      if length > 0 then
        "next: \(.[0].index)/\($total) \(.[0].path) [\(.[0].category)]"
      else "next: (all files completed)" end
    )
  ' "$session"
}

_session_update_file() {
  # scd.sh session update-file <session> <index> <green> <yellow> <red> "<note>" [blocking] [risk_score]
  local session="${1:?}" index="${2:?}" green="${3:?}" yellow="${4:?}" red="${5:?}" note="${6:?}"
  local blocking="${7:-0}" risk_score="${8:-0}"
  _check_session "$session"
  _atomic_jq "$session" \
    --argjson idx "$index" --argjson g "$green" --argjson y "$yellow" --argjson r "$red" \
    --argjson b "$blocking" --argjson rs "$risk_score" --arg note "$note" '
    (.files[] | select(.index == $idx)) |= (
      .status = "completed" | .green = $g | .yellow = $y | .red = $r |
      .blocking = $b | .note = $note |
      if $rs > 0 then .risk_score = $rs else . end
    ) |
    .summary.completed = ([.files[] | select(.status == "completed")] | length) |
    .summary.green  = ([.files[].green]  | add // 0) |
    .summary.yellow = ([.files[].yellow] | add // 0) |
    .summary.red    = ([.files[].red]    | add // 0) |
    .summary.blocking = ([.files[].blocking // 0] | add // 0)
  '
  jq '.summary' "$session"
}

_session_add_observations() {
  # scd.sh session add-observations <session> <index>
  # stdin: JSON array of observations (v2: includes correction_prompt, line_start, line_end)
  local session="${1:?}" index="${2:?}"
  _check_session "$session"
  local obs
  obs=$(cat)
  [[ -z "$obs" ]] || echo "$obs" | jq empty 2>/dev/null || { echo "Error: invalid JSON on stdin" >&2; exit 1; }
  _atomic_jq "$session" --argjson idx "$index" --argjson obs "$obs" '
    (.files[] | select(.index == $idx)).observations = $obs
  '
  echo "$obs" | jq 'length'
}

_session_add_comment() {
  # scd.sh session add-comment <session> "<file_path>" "<comment>"
  local session="${1:?}" file_path="${2:?}" comment="${3:?}"
  _check_session "$session"
  _atomic_jq "$session" --arg f "$file_path" --arg c "$comment" '
    .user_comments += [{"file": $f, "comment": $c}]
  '
  jq '.user_comments | length' "$session"
}

_session_add_agent_tasks() {
  # scd.sh session add-agent-tasks <session> '<json_object>'
  local session="${1:?}" json_obj="${2:?}"
  _check_session "$session"
  _atomic_jq "$session" --argjson tasks "$json_obj" '
    .agent_tasks = ((.agent_tasks // {}) + $tasks)
  '
  echo "$json_obj" | jq 'length'
}

_session_summary() {
  # scd.sh session summary <session>
  local session="${1:?Usage: scd.sh session summary <session>}"
  _check_session "$session"
  jq -r --arg g "🟢" --arg y "🟡" --arg r "🔴" '
    .branch as $branch |
    .summary as $s |
    "Recapitulatif de la review — \($branch)\n",
    "| # | Fichier | Categorie | \($g) | \($y) | \($r) | B |",
    "|---|---------|-----------|-----|-----|-----|---|",
    (.files[] |
      "| \(.index) | \(.path) | \(.category) | \(.green // 0) | \(.yellow // 0) | \(.red // 0) | \(.blocking // 0) |"
    ),
    "|   | **TOTAL** |  | **\($s.green // 0)** | **\($s.yellow // 0)** | **\($s.red // 0)** | **\($s.blocking // 0)** |",
    "",
    if (.user_comments // [] | length) > 0 then
      "### Commentaires\n",
      (.user_comments[] | "- **\(.file)** : \(.comment)")
    else empty end
  ' "$session"
  local tmp="${session}.tmp"
  local head_sha
  head_sha=$(git rev-parse HEAD)
  jq --arg h "$head_sha" '.status = "completed" | .head_at_completion = $h' "$session" > "$tmp" && mv "$tmp" "$session"
}

_session_pending_files() {
  # scd.sh session pending-files <session> [--sort-by=risk]
  local session="${1:?}" sort_by="category"
  [[ "${2:-}" == "--sort-by=risk" ]] && sort_by="risk"
  _check_session "$session"
  if [[ "$sort_by" == "risk" ]]; then
    jq -c '[.files[] | select(.status == "pending")] | sort_by(-((.risk_score // 0) * 0.6 + (.index // 99) * -0.004))[] | {index, path, category, risk_score: (.risk_score // 0)}' "$session"
  else
    jq -c '[.files[] | select(.status == "pending")][] | {index, path, category}' "$session"
  fi
}

# ── Domain: followup ──────────────────────────────────────────────────────────

cmd_followup() {
  local action="${1:?Usage: scd.sh followup <action> [args...]}"; shift
  case "$action" in
    classify)    _followup_classify "$@" ;;
    get-context) _followup_get_context "$@" ;;
    update-file) _followup_update_file "$@" ;;
    summary)     _followup_summary "$@" ;;
    *) echo "Error: unknown followup action: $action" >&2; exit 1 ;;
  esac
}

_followup_classify() {
  # scd.sh followup classify <previous_session> <diff_output_file>
  local previous_session="${1:?}" diff_file="${2:?}"
  _check_session "$previous_session"
  [[ -f "$diff_file" ]] || { echo "Error: diff file not found: $diff_file" >&2; exit 1; }
  local diff_content
  diff_content=$(cat "$diff_file")
  jq --arg diff "$diff_content" '
    ($diff | split("\n") | map(select(length > 0)) | map(
      split("\t") |
      if .[0][0:1] == "R" then { old: .[1], new: .[2], status: "R" }
      elif .[0] == "D" then { old: .[1], new: null, status: "D" }
      else { old: null, new: (.[1] // empty), status: .[0] } end
    )) as $changes |
    ($changes | map(
      if .status == "R" then .new
      elif .status == "D" then .old
      else .new end
    ) | map(select(. != null))) as $modified_paths |
    ($changes | map(select(.status == "R")) |
      if length > 0 then map({(.old): .new}) | add else {} end
    ) as $rename_map |
    ($changes | map(select(.status == "D")) | map(.old)) as $deleted_paths |
    .user_comments as $comments |
    .files as $files |
    def comments_for($p): [$comments[] | select(.file == $p) | .comment];
    def format_file($rtype):
      .path as $fpath |
      {
        path: .path, category: .category, review_type: $rtype,
        original_note: (.note // ""),
        original_blocking: (.blocking // 0),
        original_green: (.green // 0),
        original_yellow: (.yellow // 0),
        original_red: (.red // 0),
        original_observations: (.observations // []),
        original_comments: comments_for($fpath)
      };
    [$files[] | select((.blocking // 0) > 0) |
      .path as $p |
      if ($modified_paths | index($p)) then format_file("correction")
      elif ($rename_map[$p]) then . as $f | .path = $rename_map[$p] | format_file("correction") + { original_path: $f.path }
      elif ($deleted_paths | index($p)) then format_file("correction") + { resolution: "auto_resolved_deleted" }
      else null end
    | select(. != null)] as $corrections |
    [$files[] | select((.blocking // 0) > 0) |
      .path as $p |
      if ($modified_paths | index($p) | not) and
         (($rename_map[$p] // null) == null) and
         ($deleted_paths | index($p) | not) then format_file("unaddressed")
      else null end
    | select(. != null)] as $unaddressed |
    ([$corrections[].path] + [$unaddressed[].path]) as $handled |
    [$modified_paths[] |
      . as $p |
      if ($handled | index($p) | not) and ($deleted_paths | index($p) | not) then
        ($files | map(select(.path == $p)) | .[0] // null) as $prev |
        if $prev then $prev | format_file("new")
        else { path: $p, category: "unknown", review_type: "new",
               original_note: "", original_blocking: 0, original_green: 0,
               original_yellow: 0, original_red: 0,
               original_observations: [], original_comments: [] } end
      else null end
    | select(. != null)] as $new |
    { corrections: $corrections, unaddressed: $unaddressed, new: $new,
      stats: { corrections: ($corrections | length), unaddressed: ($unaddressed | length), new: ($new | length) } }
  ' "$previous_session"
}

_followup_get_context() {
  # scd.sh followup get-context <session> <path>
  local session="${1:?}" filepath="${2:?}"
  _check_session "$session"
  jq --arg p "$filepath" '
    .user_comments as $comments |
    (.files[] | select(.path == $p)) // null |
    if . == null then error("File not found in session: \($p)")
    else {
      path: .path, category: .category,
      green: (.green // 0), yellow: (.yellow // 0), red: (.red // 0),
      blocking: (.blocking // 0), note: (.note // ""),
      observations: (.observations // []),
      comments: [$comments[] | select(.file == $p) | .comment]
    } end
  ' "$session"
}

_followup_update_file() {
  # scd.sh followup update-file <session> <index> <green> <yellow> <red> "<note>" "<resolution>"
  local session="${1:?}" index="${2:?}" green="${3:?}" yellow="${4:?}" red="${5:?}"
  local note="${6:?}" resolution="${7:?}"
  _check_session "$session"
  local res_arg="null"
  [[ "$resolution" != "null" ]] && res_arg="\"$resolution\""
  _atomic_jq "$session" \
    --argjson idx "$index" --argjson g "$green" --argjson y "$yellow" --argjson r "$red" \
    --arg note "$note" --argjson res "$res_arg" '
    (.files[] | select(.index == $idx)) |= (
      .status = "completed" | .green = $g | .yellow = $y | .red = $r |
      .note = $note | .resolution = $res
    ) |
    .summary.completed  = ([.files[] | select(.status == "completed")] | length) |
    .summary.resolved   = ([.files[] | select(.resolution == "resolved" or .resolution == "auto_resolved_deleted")] | length) |
    .summary.partially_resolved = ([.files[] | select(.resolution == "partially_resolved")] | length) |
    .summary.unresolved = ([.files[] | select(.resolution == "unresolved")] | length) |
    .summary.new_green  = ([.files[] | select(.review_type == "new") | .green] | add // 0) |
    .summary.new_yellow = ([.files[] | select(.review_type == "new") | .yellow] | add // 0) |
    .summary.new_red    = ([.files[] | select(.review_type == "new") | .red] | add // 0)
  '
  jq '.summary' "$session"
}

_followup_summary() {
  # scd.sh followup summary <session>
  local session="${1:?Usage: scd.sh followup summary <session>}"
  _check_session "$session"
  jq -r --arg g "🟢" --arg y "🟡" --arg r "🔴" '
    .branch as $branch | .round as $round | .summary as $s |
    "Recapitulatif du followup (round \($round)) — \($branch)\n",
    ([.files[] | select(.review_type == "correction")] | length) as $corr_count |
    if $corr_count > 0 then
      "### Corrections (\($corr_count) fichiers)\n",
      "| # | Fichier | Resolution | \($g) | \($y) | \($r) | Note originale |",
      "|---|---------|------------|-----|-----|-----|----------------|",
      ([.files[] | select(.review_type == "correction")] | sort_by(.index)[] |
        "| \(.index) | \(.path) | \(.resolution // "pending") | \(.green // 0) | \(.yellow // 0) | \(.red // 0) | \(.original_note) |"
      ), ""
    else empty end,
    ([.files[] | select(.review_type == "unaddressed")] | length) as $unadr_count |
    if $unadr_count > 0 then
      "### Non adresses (\($unadr_count) fichiers)\n",
      "| # | Fichier | Resolution | Note originale |",
      "|---|---------|------------|----------------|",
      ([.files[] | select(.review_type == "unaddressed")] | sort_by(.index)[] |
        "| \(.index) | \(.path) | \(.resolution // "pending") | \(.original_note) |"
      ), ""
    else empty end,
    ([.files[] | select(.review_type == "new")] | length) as $new_count |
    if $new_count > 0 then
      "### Nouveaux fichiers (\($new_count) fichiers)\n",
      "| # | Fichier | Categorie | \($g) | \($y) | \($r) |",
      "|---|---------|-----------|-----|-----|-----|",
      ([.files[] | select(.review_type == "new")] | sort_by(.index)[] |
        "| \(.index) | \(.path) | \(.category) | \(.green // 0) | \(.yellow // 0) | \(.red // 0) |"
      ), ""
    else empty end,
    "---",
    "Resume: \($s.resolved // 0) resolus, \($s.partially_resolved // 0) partiellement resolus, \($s.unresolved // 0) non resolus"
  ' "$session"
  local tmp="${session}.tmp"
  local head_sha
  head_sha=$(git rev-parse HEAD)
  jq --arg h "$head_sha" '.status = "completed" | .head_at_completion = $h' "$session" > "$tmp" && mv "$tmp" "$session"
}

# ── Domain: post ──────────────────────────────────────────────────────────────

cmd_post() {
  local action="${1:?Usage: scd.sh post <action> [args...]}"; shift
  case "$action" in
    inline-comments) _post_inline_comments "$@" ;;
    orphan-summary)  _post_orphan_summary "$@" ;;
    *) echo "Error: unknown post action: $action" >&2; exit 1 ;;
  esac
}

_post_resolve_pr() {
  # Sets pr_number and encoded_project (GitLab) based on platform_type and branch
  # Called by both _post_inline_comments and _post_orphan_summary
  local platform_type="$1" branch="$2"
  pr_number=""
  if [[ "$platform_type" == "github" ]]; then
    pr_number=$(gh pr list --head "$branch" --json number --jq '.[0].number' 2>/dev/null || true)
  elif [[ "$platform_type" == "gitlab" ]]; then
    pr_number=$(glab mr list --source-branch "$branch" -o json 2>/dev/null | jq -r '.[0].iid // empty' 2>/dev/null || true)
  fi
}

_post_build_inline_body() {
  # Build a v2 inline comment body from an observation JSON (stdin)
  local lang="$1" obs="$2"
  echo "$obs" | jq -r --arg lang "$lang" '
    (if .level == "red" then "🔴" elif .level == "yellow" then "🟡" else "🟢" end) as $emoji |
    (if .severity == "blocking" or .severity == "bloquant" then
       (if $lang == "en" then " [BLOCKING]" else " [BLOQUANT]" end)
     else "" end) as $tag |
    (if .suggestion then
       (if $lang == "en" then "\n\n**Suggestion:** " else "\n\n**Suggestion :** " end) + .suggestion
     else "" end) as $sug |

    # correction_prompt block (v2)
    (if .correction_prompt then
       "\n\n<details>\n<summary>💡 " +
       (if $lang == "en" then "Correction prompt" else "Prompt de correction" end) +
       "</summary>\n\n" + .correction_prompt + "\n\n</details>"
     else "" end) as $prompt_block |

    # Location line reference
    (if .line_start and .line_end and (.line_start != .line_end) then
       "`\(.path // "?"):\(.line_start)-\(.line_end)`"
     elif .line_start then
       "`\(.path // "?"):\(.line_start)`"
     elif .location then
       "`\(.location)`"
     else "" end) as $loc |

    "\($emoji) **\(.criterion)**\($tag) — \(.text)" +
    (if ($loc | length) > 0 then "\n\n\($loc) — " else "\n\n" end) +
    (.detail // "") + $sug + $prompt_block
  '
}

_post_inline_comments() {
  # scd.sh post inline-comments <session> <config> [filter]
  # v2: inline-only; orphans collected and returned on stdout for optional posting
  # filter: blocking (default) | all | red | yellow
  local session="${1:?Usage: scd.sh post inline-comments <session> <config> [filter]}"
  local config="${2:?}" filter="${3:-blocking}"
  _check_session "$session"
  _check_config "$config"

  case "$filter" in
    blocking|all|red|yellow) ;;
    *) echo "WARN: unknown filter '$filter' (valid: blocking, all, red, yellow)"; exit 0 ;;
  esac

  local platform_type
  platform_type=$(jq -r '.platform.type // empty' "$config" 2>/dev/null || true)
  [[ -z "$platform_type" || "$platform_type" == "null" ]] && { echo "SKIP: platform not configured"; exit 0; }

  if [[ "$platform_type" == "github" ]]; then
    command -v gh &>/dev/null || { echo "WARN: gh CLI not found"; exit 0; }
  elif [[ "$platform_type" == "gitlab" ]]; then
    command -v glab &>/dev/null || { echo "WARN: glab CLI not found"; exit 0; }
  else
    echo "WARN: unknown platform: $platform_type"; exit 0
  fi

  local branch
  branch=$(git branch --show-current 2>/dev/null || true)
  [[ -z "$branch" ]] && { echo "SKIP: not on a branch (detached HEAD?)"; exit 0; }

  local pr_number
  _post_resolve_pr "$platform_type" "$branch"
  [[ -z "$pr_number" ]] && { echo "SKIP: no open PR/MR for branch $branch"; exit 0; }

  local lang
  lang=$(jq -r '.options.language // "fr"' "$config" 2>/dev/null || echo "fr")

  # Extract filtered observations with resolved line numbers
  local observations
  observations=$(jq --arg filter "$filter" '
    [.files[] | .path as $path | (.observations // [])[] |
      if $filter == "blocking" then select(.severity == "blocking" or .severity == "bloquant")
      elif $filter == "red" then select(.level == "red")
      elif $filter == "yellow" then select(.level == "yellow")
      else . end |

      # Resolve line number: prefer line_start (v2), then location, then fallback
      (
        if .line_start then { n: .line_start, resolved: true }
        elif (.location // null) and ((.location | tostring) | test(":[0-9]+")) then
          { n: ((.location | tostring) | capture(":(?<n>[0-9]+)") | .n | tonumber), resolved: true }
        else { n: 1, resolved: false } end
      ) as $ln |

      . + { path: $path, resolved_line: $ln.n, line_resolved: $ln.resolved }
    ]
  ' "$session")

  local obs_count
  obs_count=$(echo "$observations" | jq 'length')
  [[ "$obs_count" -eq 0 ]] && { echo "SKIP: no observations match filter '$filter'"; exit 0; }

  echo "INFO: $obs_count observation(s) to post inline"

  local posted=0 orphan_json="[]"

  if [[ "$platform_type" == "github" ]]; then
    # Build batch review payload
    local payload
    payload=$(echo "$observations" | jq --arg lang "$lang" '
      {
        event: "COMMENT",
        body: "",
        comments: [.[] |
          (if .level == "red" then "🔴" elif .level == "yellow" then "🟡" else "🟢" end) as $emoji |
          (if .severity == "blocking" or .severity == "bloquant" then
             (if $lang == "en" then " [BLOCKING]" else " [BLOQUANT]" end)
           else "" end) as $tag |
          (if .suggestion then
             (if $lang == "en" then "\n\n**Suggestion:** " else "\n\n**Suggestion :** " end) + .suggestion
           else "" end) as $sug |
          (if .correction_prompt then
             "\n\n<details>\n<summary>💡 " +
             (if $lang == "en" then "Correction prompt" else "Prompt de correction" end) +
             "</summary>\n\n" + .correction_prompt + "\n\n</details>"
           else "" end) as $prompt_block |
          {
            path: .path,
            body: "\($emoji) **\(.criterion)**\($tag) — \(.text)\n\n\(.detail // "")\($sug)\($prompt_block)"
          } + (if .line_resolved then
            { line: .resolved_line, side: "RIGHT" }
          else
            { subject_type: "file" }
          end)
        ]
      }
    ')

    local result
    result=$(echo "$payload" | gh api "repos/{owner}/{repo}/pulls/$pr_number/reviews" \
      --method POST --input - 2>&1 || true)

    if echo "$result" | jq -e '.id' &>/dev/null 2>&1; then
      posted=$obs_count
      echo "POSTED: $posted inline comment(s) on PR #$pr_number"
    else
      # Retry one by one — collect orphans (failed due to line not in diff)
      orphan_obs="[]"
      while IFS= read -r comment_json; do
        local single
        single=$(jq -n --argjson c "$comment_json" '{event: "COMMENT", body: "", comments: [$c]}')
        if echo "$single" | gh api "repos/{owner}/{repo}/pulls/$pr_number/reviews" \
          --method POST --input - &>/dev/null 2>&1; then
          posted=$((posted + 1))
        else
          orphan_obs=$(echo "$orphan_obs" | jq --argjson c "$comment_json" '. + [$c]')
        fi
      done < <(echo "$payload" | jq -c '.comments[]')

      local failed=$(( obs_count - posted ))
      if [[ "$posted" -gt 0 ]]; then
        msg="POSTED: $posted/$obs_count inline comment(s) on PR #$pr_number"
        [[ "$failed" -gt 0 ]] && msg="$msg ($failed orphaned — will need orphan-summary)"
        echo "$msg"
      else
        echo "WARN: all $obs_count inline comment(s) failed for PR #$pr_number"
      fi

      # Write orphans to temp file for follow-up
      if [[ "$failed" -gt 0 ]]; then
        local orphan_file
        orphan_file="$(dirname "$session")/$(basename "$session" .json)-orphans.json"
        echo "$orphan_obs" > "$orphan_file"
        echo "ORPHANS: $failed observation(s) saved to $orphan_file"
      fi
    fi

  elif [[ "$platform_type" == "gitlab" ]]; then
    local remote_url project_path encoded_project
    remote_url=$(git remote get-url origin 2>/dev/null || true)
    project_path=$(echo "$remote_url" | sed -E 's|^(https?://[^/]+/|git@[^:]+:)||; s|\.git$||')
    encoded_project=$(echo "$project_path" | sed 's|/|%2F|g')

    local mr_json base_sha start_sha head_sha
    mr_json=$(glab api "projects/$encoded_project/merge_requests/$pr_number" 2>/dev/null || true)
    base_sha=$(echo "$mr_json" | jq -r '.diff_refs.base_sha // empty' 2>/dev/null || true)
    start_sha=$(echo "$mr_json" | jq -r '.diff_refs.start_sha // empty' 2>/dev/null || true)
    head_sha=$(echo "$mr_json" | jq -r '.diff_refs.head_sha // empty' 2>/dev/null || true)

    if [[ -z "$base_sha" || -z "$head_sha" ]]; then
      echo "WARN: could not retrieve diff_refs for MR !$pr_number"; exit 0
    fi
    [[ -z "$start_sha" ]] && start_sha="$base_sha"

    local orphan_obs="[]"
    while IFS= read -r obs; do
      local path line body
      path=$(echo "$obs" | jq -r '.path')
      line=$(echo "$obs" | jq '.resolved_line')
      body=$(_post_build_inline_body "$lang" "$obs")

      local discussion_payload
      discussion_payload=$(jq -n \
        --arg body "$body" --arg base "$base_sha" --arg start "$start_sha" \
        --arg head "$head_sha" --arg new_path "$path" --argjson new_line "$line" '
        {
          body: $body,
          position: {
            base_sha: $base, start_sha: $start, head_sha: $head,
            position_type: "text", new_path: $new_path, new_line: $new_line
          }
        }')

      if echo "$discussion_payload" | glab api "projects/$encoded_project/merge_requests/$pr_number/discussions" \
        --method POST --input - 2>/dev/null | jq -e '.id' &>/dev/null; then
        posted=$((posted + 1))
      else
        # Fallback: non-positioned discussion
        local fallback
        fallback=$(jq -n --arg body "$body" '{body: $body}')
        if echo "$fallback" | glab api "projects/$encoded_project/merge_requests/$pr_number/discussions" \
          --method POST --input - 2>/dev/null | jq -e '.id' &>/dev/null; then
          posted=$((posted + 1))
        else
          orphan_obs=$(echo "$orphan_obs" | jq --argjson o "$obs" '. + [$o]')
        fi
      fi
    done < <(echo "$observations" | jq -c '.[]')

    local failed=$(( obs_count - posted ))
    if [[ "$posted" -gt 0 ]]; then
      msg="POSTED: $posted inline discussion(s) on MR !$pr_number"
      [[ "$failed" -gt 0 ]] && msg="$msg ($failed orphaned)"
      echo "$msg"
    else
      echo "WARN: all $obs_count discussion(s) failed for MR !$pr_number"
    fi

    if [[ "$failed" -gt 0 ]]; then
      local orphan_file
      orphan_file="$(dirname "$session")/$(basename "$session" .json)-orphans.json"
      echo "$orphan_obs" > "$orphan_file"
      echo "ORPHANS: $failed observation(s) saved to $orphan_file"
    fi
  fi
}

_post_orphan_summary() {
  # scd.sh post orphan-summary <session> <config>
  # Posts accumulated orphan observations as a single general comment
  local session="${1:?}" config="${2:?}"
  _check_session "$session"
  _check_config "$config"

  local orphan_file
  orphan_file="$(dirname "$session")/$(basename "$session" .json)-orphans.json"
  [[ -f "$orphan_file" ]] || { echo "SKIP: no orphan file found"; exit 0; }

  local orphan_count
  orphan_count=$(jq 'length' "$orphan_file")
  [[ "$orphan_count" -eq 0 ]] && { echo "SKIP: no orphan observations"; exit 0; }

  local platform_type lang branch pr_number
  platform_type=$(jq -r '.platform.type // empty' "$config" 2>/dev/null || true)
  lang=$(jq -r '.options.language // "fr"' "$config" 2>/dev/null || echo "fr")
  branch=$(git branch --show-current 2>/dev/null || true)
  _post_resolve_pr "$platform_type" "$branch"
  [[ -z "$pr_number" ]] && { echo "SKIP: no open PR/MR for branch $branch"; exit 0; }

  local header
  if [[ "$lang" == "en" ]]; then
    header="⚠️ Observations hors diff ($orphan_count items) — these observations concern code not modified in this MR"
  else
    header="⚠️ Observations hors diff ($orphan_count items) — ces observations concernent du code non modifié dans cette MR"
  fi

  local body
  body=$(jq -r --arg header "$header" --arg lang "$lang" '
    $header + "\n\n" +
    (.[] |
      (if .level == "red" then "🔴" elif .level == "yellow" then "🟡" else "🟢" end) as $emoji |
      "- \($emoji) **\(.criterion)** `\(.path // "?")` — \(.text)"
    )
  ' "$orphan_file")

  if [[ "$platform_type" == "github" ]]; then
    gh pr comment "$pr_number" --body "$body" 2>/dev/null \
      && echo "POSTED: orphan summary ($orphan_count items) on PR #$pr_number" \
      || echo "WARN: failed to post orphan summary on PR #$pr_number"
  elif [[ "$platform_type" == "gitlab" ]]; then
    local remote_url project_path encoded_project
    remote_url=$(git remote get-url origin 2>/dev/null || true)
    project_path=$(echo "$remote_url" | sed -E 's|^(https?://[^/]+/|git@[^:]+:)||; s|\.git$||')
    encoded_project=$(echo "$project_path" | sed 's|/|%2F|g')
    jq -n --arg body "$body" '{body: $body}' | \
      glab api "projects/$encoded_project/merge_requests/$pr_number/notes" \
        --method POST --input - 2>/dev/null \
      && echo "POSTED: orphan summary ($orphan_count items) on MR !$pr_number" \
      || echo "WARN: failed to post orphan summary on MR !$pr_number"
  fi

  # Clean up orphan file after posting
  rm -f "$orphan_file"
}

# ── Domain: validation ────────────────────────────────────────────────────────

cmd_validation() {
  local action="${1:?Usage: scd.sh validation <action> [args...]}"; shift
  case "$action" in
    update)  _validation_update "$@" ;;
    report)  _validation_report "$@" ;;
    *) echo "Error: unknown validation action: $action" >&2; exit 1 ;;
  esac
}

_validation_update() {
  # scd.sh validation update <session> <file_path> <decisions_json>
  # v2: writes validator_decision + validator_confidence directly into observations
  local session="${1:?}" file_path="${2:?}" decisions="${3:?}"
  _check_session "$session"
  _atomic_jq "$session" --arg file "$file_path" --argjson decisions "$decisions" '
    (.files[] | select(.path == $file)).observations |=
      [to_entries[] | .value as $obs | .key as $idx |
        ($decisions[] | select(.index == $idx)) as $dec |
        if $dec then
          $obs + {
            "validator_decision": $dec.decision,
            "validator_confidence": $dec.confidence,
            "validator_reason": $dec.reason
          }
        else $obs end
      ] |
    [.files[].observations[] | .validator_decision? // empty] as $vals |
    .summary.validation = {
      "apply":    ([$vals[] | select(. == "apply")]    | length),
      "skip":     ([$vals[] | select(. == "skip")]     | length),
      "escalate": ([$vals[] | select(. == "escalate")] | length),
      "total":    ($vals | length)
    }
  '
  jq '.summary.validation' "$session"
}

_validation_report() {
  # scd.sh validation report <session_slug> <sessions_dir>
  # v2: consolidated report using review session only (no separate apply session)
  local slug="${1:?Usage: scd.sh validation report <slug> <sessions_dir>}"
  local sessions_dir="${2:?}"
  local review_session="${sessions_dir}/${slug}.json"
  local followup_session="${sessions_dir}/${slug}-followup.json"

  [[ -f "$review_session" ]] || { echo "Error: review session not found: $review_session" >&2; exit 1; }

  local has_followup="false"
  [[ -f "$followup_session" ]] && has_followup="true"

  jq -n \
    --slurpfile review "$review_session" \
    --argjson has_followup "$has_followup" \
    --arg slug "$slug" '
    $review[0] as $rev |
    ($rev.summary) as $rev_summary |
    [$rev.files[].observations[]] as $all_obs |

    # Review stats
    ($all_obs | length) as $total_obs |
    ([$all_obs[] | select(.level == "red")] | length) as $blocking_obs |

    # Validation stats (from validator_decision field on observations)
    ([$all_obs[] | select(.validator_decision != null)] | length) as $validated_count |
    ([$all_obs[] | select(.validator_decision == "apply")]    | length) as $val_apply |
    ([$all_obs[] | select(.validator_decision == "skip")]     | length) as $val_skip |
    ([$all_obs[] | select(.validator_decision == "escalate")] | length) as $val_escalate |

    # Escalations detail
    [$rev.files[] | .path as $fp | .observations[] |
      select(.validator_decision == "escalate") |
      {file: $fp, criterion, level, text, reason: .validator_reason}
    ] as $escalations |

    # Resolution stats (v2: resolution stored in observation)
    ([$all_obs[] | select(.resolution == "fixed")]    | length) as $fixed |
    ([$all_obs[] | select(.resolution == "posted")]   | length) as $posted_count |
    ([$all_obs[] | select(.resolution == "skipped")]  | length) as $skipped |
    ([$all_obs[] | select(.resolution == "escalated")]| length) as $escalated |

    # Followup stats (if exists)
    (if $has_followup then
      ([$rev.files[] | select(.status == "completed")] | length) as $resolved_files |
      { resolved: ($rev_summary.resolved // 0),
        partially: ($rev_summary.partially_resolved // 0),
        unresolved: ($rev_summary.unresolved // 0) }
    else { resolved: 0, partially: 0, unresolved: 0 } end) as $followup_stats |

    # Verdict
    (if ($val_escalate == 0) and ($skipped == 0 or $blocking_obs == 0) and
        ($followup_stats.unresolved == 0) and ($followup_stats.partially == 0)
     then "ready_to_merge"
     elif ($val_escalate > 0) or ($skipped > 0)
     then "attention_required"
     else "blocked" end) as $verdict |

    {
      slug: $slug, branch: $rev.branch, base: ($rev.base_branch // $rev.base),
      generated_at: (now | strftime("%Y-%m-%dT%H:%M:%SZ")),
      review: {
        total_files: ($rev.files | length), total_observations: $total_obs,
        blocking: $blocking_obs, green: ($rev_summary.green // 0),
        yellow: ($rev_summary.yellow // 0), red: ($rev_summary.red // 0)
      },
      validation: {
        validated: $validated_count, apply: $val_apply,
        skip: $val_skip, escalate: $val_escalate, escalations: $escalations
      },
      resolution: { fixed: $fixed, posted: $posted_count, skipped: $skipped, escalated: $escalated },
      followup: $followup_stats,
      verdict: $verdict
    }
  ' $(if [[ "$has_followup" == "true" ]]; then echo "$followup_session"; fi)
}

# ── Domain: context ───────────────────────────────────────────────────────────

cmd_context() {
  local action="${1:?Usage: scd.sh context <action> [args...]}"; shift
  case "$action" in
    resolve) _context_resolve "$@" ;;
    clear)   _context_clear "$@" ;;
    *) echo "Error: unknown context action: $action" >&2; exit 1 ;;
  esac
}

_context_resolve() {
  # scd.sh context resolve <type> <value> <sessions_dir> <branch> <config>
  # type: ticket | file | url
  local type="${1:?Usage: scd.sh context resolve <type> <value> <sessions_dir> <branch> <config>}"
  local value="${2:?}" sessions_dir="${3:?}" branch="${4:?}" config="${5:?}"
  local slug
  slug=$(echo "$branch" | sed 's|/|-|g')
  local context_file="${sessions_dir}/${slug}-context.md"
  local max_lines=200

  [[ -f "$config" ]] && max_lines=$(jq -r '.context.max_context_lines // 200' "$config" 2>/dev/null || echo "200")

  case "$type" in
    ticket)
      local platform_type
      platform_type=$(jq -r '.platform.type // empty' "$config" 2>/dev/null || true)
      local ticket_content=""
      if [[ "$platform_type" == "github" ]]; then
        ticket_content=$(gh issue view "$value" --json title,body,labels 2>/dev/null | \
          jq -r '"## Ticket: " + .title + "\n**Source:** GitHub Issue #" + (env.value) + "\n**Labels:** " + ([.labels[].name] | join(", ")) + "\n\n### Description\n" + .body' 2>/dev/null || true)
      elif [[ "$platform_type" == "gitlab" ]]; then
        ticket_content=$(glab issue view "$value" 2>/dev/null | head -n "$max_lines" || true)
        [[ -z "$ticket_content" ]] && ticket_content=$(glab issue view "$value" --output json 2>/dev/null | \
          jq -r '"## Ticket: " + .title + "\n\n### Description\n" + .description' 2>/dev/null || true)
      fi
      if [[ -z "$ticket_content" ]]; then
        # Try Jira if configured
        local jira_url jira_token_env jira_token
        jira_url=$(jq -r '.context.jira_api_url // empty' "$config" 2>/dev/null || true)
        jira_token_env=$(jq -r '.context.jira_auth_token_env // "JIRA_TOKEN"' "$config" 2>/dev/null || echo "JIRA_TOKEN")
        jira_token="${!jira_token_env:-}"
        if [[ -n "$jira_url" && -n "$jira_token" ]]; then
          ticket_content=$(curl -s -H "Authorization: Bearer $jira_token" \
            "${jira_url}/rest/api/3/issue/${value}" 2>/dev/null | \
            jq -r '"## Ticket: " + .fields.summary + "\n\n### Description\n" + (.fields.description // "N/A")' 2>/dev/null || true)
        fi
      fi
      [[ -z "$ticket_content" ]] && { echo "WARN: could not resolve ticket $value"; exit 0; }
      {
        echo "---"
        echo ""
        echo "$ticket_content"
        echo ""
      } >> "$context_file"
      echo "RESOLVED: ticket $value → $context_file"
      ;;

    file)
      [[ -f "$value" ]] || { echo "WARN: file not found: $value"; exit 0; }
      {
        echo "---"
        echo ""
        echo "## Spec: $value"
        head -n "$max_lines" "$value"
        local total_lines
        total_lines=$(wc -l < "$value")
        [[ "$total_lines" -gt "$max_lines" ]] && echo "[...truncated at $max_lines lines — total: $total_lines]"
        echo ""
      } >> "$context_file"
      echo "RESOLVED: file $value → $context_file"
      ;;

    url)
      local url_content=""
      if command -v curl &>/dev/null; then
        url_content=$(curl -sL --max-time 15 "$value" 2>/dev/null | \
          sed 's/<[^>]*>//g; /^[[:space:]]*$/d' | head -n "$max_lines" || true)
      fi
      [[ -z "$url_content" ]] && { echo "WARN: could not fetch URL $value"; exit 0; }
      {
        echo "---"
        echo ""
        echo "## URL: $value"
        echo "$url_content"
        echo ""
      } >> "$context_file"
      echo "RESOLVED: url $value → $context_file"
      ;;

    *) echo "Error: unknown context type: $type (valid: ticket, file, url)" >&2; exit 1 ;;
  esac

  # Ensure header at top of context file if it's new
  if ! grep -q "^# Review Context" "$context_file" 2>/dev/null; then
    local tmp="${context_file}.tmp"
    { echo "# Review Context"; echo ""; cat "$context_file"; } > "$tmp" && mv "$tmp" "$context_file"
  fi
}

_context_clear() {
  # scd.sh context clear <sessions_dir> <branch>
  local sessions_dir="${1:?}" branch="${2:?}"
  local slug
  slug=$(echo "$branch" | sed 's|/|-|g')
  local context_file="${sessions_dir}/${slug}-context.md"
  [[ -f "$context_file" ]] && rm "$context_file" && echo "CLEARED: $context_file" || echo "SKIP: no context file found"
}

# ── Domain: agent ─────────────────────────────────────────────────────────────

cmd_agent() {
  local action="${1:?Usage: scd.sh agent <action> [args...]}"; shift
  case "$action" in
    validate-output) _agent_validate_output "$@" ;;
    capture-output)  _agent_capture_output "$@" ;;
    *) echo "Error: unknown agent action: $action" >&2; exit 1 ;;
  esac
}

_agent_validate_output() {
  # scd.sh agent validate-output
  # stdin: raw agent output text
  # stdout: normalized observations JSON array
  # exit 2 if parsing fails
  local raw
  raw=$(cat)

  # Extract Observations JSON line
  local obs_line
  obs_line=$(echo "$raw" | grep -E '^Observations? JSON:' | head -1 || true)
  [[ -z "$obs_line" ]] && { echo "Error: no 'Observations JSON:' line in agent output" >&2; exit 2; }

  local obs_json
  obs_json=$(echo "$obs_line" | sed 's/^Observations\? JSON:[[:space:]]*//')

  # Validate JSON
  echo "$obs_json" | jq empty 2>/dev/null || { echo "Error: invalid JSON in Observations JSON line" >&2; exit 2; }

  # Normalize: add default values for missing v2 fields
  echo "$obs_json" | jq '
    map(
      .criterion     //= "conventions" |
      .severity      //= "suggestion" |
      .level         //= "yellow" |
      .text          //= "" |
      .detail        //= "" |
      .suggestion    //= null |
      .correction_prompt //= null |
      .line_start    //= null |
      .line_end      //= null
    )
  '
}

_agent_capture_output() {
  # scd.sh agent capture-output <session> <file_index>
  # stdin: raw agent task output (from PostToolUse hook tool_response)
  # Parses observations and persists them to the session
  local session="${1:?Usage: scd.sh agent capture-output <session> <file_index>}"
  local file_index="${2:?}"
  _check_session "$session"

  local raw
  raw=$(cat)

  # Validate + normalize
  local normalized
  if normalized=$(echo "$raw" | _agent_validate_output 2>/dev/null); then
    echo "$normalized" | _session_add_observations "$session" "$file_index"
    echo "CAPTURED: observations persisted for file index $file_index"
  else
    echo "Error: failed to parse agent output for file index $file_index" >&2
    exit 2
  fi
}

# ── Domain: test ──────────────────────────────────────────────────────────────

cmd_test() {
  local action="${1:?Usage: scd.sh test <action> [args...]}"; shift
  case "$action" in
    run-affected) _test_run_affected "$@" ;;
    *) echo "Error: unknown test action: $action" >&2; exit 1 ;;
  esac
}

_test_run_affected() {
  # scd.sh test run-affected <modified_file>
  # Identifies and runs tests related to the modified file
  # exit 0 = tests pass or no tests found
  # exit 2 = tests fail (Claude receives feedback for retry)
  local modified_file="${1:?Usage: scd.sh test run-affected <modified_file>}"

  # Try to find test files via naming convention
  local base_name
  base_name=$(basename "$modified_file" | sed 's/\.[^.]*$//')
  local dir_name
  dir_name=$(dirname "$modified_file")

  # Search patterns: same dir, tests/ dir, __tests__ dir
  local test_files=()
  while IFS= read -r f; do
    test_files+=("$f")
  done < <(find . \( -name "${base_name}.test.*" -o -name "${base_name}.spec.*" -o -name "${base_name}_test.*" \) \
    -not -path "*/node_modules/*" -not -path "*/.git/*" 2>/dev/null || true)

  if [[ ${#test_files[@]} -eq 0 ]]; then
    echo "INFO: no test files found for $modified_file"
    exit 0
  fi

  echo "INFO: running ${#test_files[@]} test file(s) for $modified_file"

  # Detect test runner and run scoped
  if [[ -f "package.json" ]] && command -v npx &>/dev/null; then
    if grep -q '"jest"' package.json 2>/dev/null || grep -q '"vitest"' package.json 2>/dev/null; then
      local runner="jest"
      grep -q '"vitest"' package.json 2>/dev/null && runner="vitest"
      if npx "$runner" --testPathPattern="$base_name" --passWithNoTests 2>&1; then
        echo "PASS: tests pass for $modified_file"
        exit 0
      else
        echo "FAIL: tests failed for $modified_file — fix-applier should retry or escalate"
        exit 2
      fi
    fi
  elif command -v go &>/dev/null && [[ "$modified_file" == *.go ]]; then
    local pkg_dir
    pkg_dir=$(dirname "$modified_file")
    if go test "./$pkg_dir/..." 2>&1; then
      echo "PASS: go tests pass for $modified_file"
      exit 0
    else
      echo "FAIL: go tests failed for $modified_file"
      exit 2
    fi
  elif command -v python3 &>/dev/null && [[ "$modified_file" == *.py ]]; then
    if python3 -m pytest "${test_files[@]}" -v 2>&1; then
      echo "PASS: pytest pass for $modified_file"
      exit 0
    else
      echo "FAIL: pytest failed for $modified_file"
      exit 2
    fi
  fi

  echo "INFO: no recognized test runner for $modified_file — skipping test verification"
  exit 0
}

# ── Domain: init ──────────────────────────────────────────────────────────────

cmd_init() {
  local action="${1:?Usage: scd.sh init <action> [args...]}"; shift
  case "$action" in
    detect-env) _init_detect_env "$@" ;;
    *) echo "Error: unknown init action: $action" >&2; exit 1 ;;
  esac
}

_init_detect_env() {
  # scd.sh init detect-env <config> [--force]
  # Detects OS, jq, gh/glab availability, scripts hash
  # Writes environment cache to config.json
  local config="${1:?Usage: scd.sh init detect-env <config> [--force]}"
  local force="${2:-}"

  # Check if cache is still valid (< 24h) unless --force
  if [[ "$force" != "--force" ]] && [[ -f "$config" ]]; then
    local probed_at
    probed_at=$(jq -r '.environment.probed_at // empty' "$config" 2>/dev/null || true)
    if [[ -n "$probed_at" ]]; then
      local probed_epoch now_epoch age_hours
      probed_epoch=$(date -d "$probed_at" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%SZ" "$probed_at" +%s 2>/dev/null || echo 0)
      now_epoch=$(date +%s)
      age_hours=$(( (now_epoch - probed_epoch) / 3600 ))
      if [[ "$age_hours" -lt 24 ]]; then
        echo "CACHE_HIT: environment cache is ${age_hours}h old (< 24h) — skipping probe"
        exit 0
      fi
    fi
  fi

  # Detect OS
  local os
  os=$(uname -s 2>/dev/null | tr '[:upper:]' '[:lower:]' || echo "unknown")

  # Detect jq
  local jq_available="false" json_strategy="readwrite"
  command -v jq &>/dev/null && jq_available="true" && json_strategy="jq"

  # Detect platform CLI
  local platform_cli="none" platform_cli_version="" platform_cli_authenticated="false"
  if command -v gh &>/dev/null; then
    platform_cli="gh"
    platform_cli_version=$(gh --version 2>/dev/null | head -1 | awk '{print $3}' || echo "")
    gh auth status &>/dev/null && platform_cli_authenticated="true" || true
  fi
  if command -v glab &>/dev/null; then
    local glab_auth="false"
    glab auth status &>/dev/null && glab_auth="true" || \
      glab api user &>/dev/null && glab_auth="true" || true
    if [[ "$platform_cli" == "none" ]] || [[ "$glab_auth" == "true" && "$platform_cli_authenticated" == "false" ]]; then
      platform_cli="glab"
      platform_cli_version=$(glab --version 2>/dev/null | head -1 | awk '{print $3}' || echo "")
      platform_cli_authenticated="$glab_auth"
    fi
  fi

  # Detect scripts installation
  local scripts_installed="false" scripts_hash=""
  local scripts_dir
  scripts_dir="$(dirname "$config")/../scripts"
  if [[ -d "$scripts_dir" ]] && [[ -f "$scripts_dir/scd.sh" ]]; then
    scripts_installed="true"
    scripts_hash=$(find "$scripts_dir" -name "*.sh" -exec sha256sum {} \; 2>/dev/null | sha256sum | awk '{print $1}' | head -c 8 || echo "")
  fi

  # Detect rules
  local rules_installed="false"
  [[ -f ".claude/rules/testing-principles.md" ]] || [[ -f ".claude/review/rules/testing-principles.md" ]] && rules_installed="true" || true

  local now_iso
  now_iso=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  # Write to config
  _atomic_jq "$config" \
    --arg os "$os" --arg jq "$jq_available" --arg strategy "$json_strategy" \
    --arg cli "$platform_cli" --arg cli_ver "$platform_cli_version" \
    --arg cli_auth "$platform_cli_authenticated" \
    --arg scripts "$scripts_installed" --arg hash "$scripts_hash" \
    --arg rules "$rules_installed" --arg now "$now_iso" '
    .environment = {
      os: $os,
      jq_available: ($jq == "true"),
      json_strategy: $strategy,
      platform_cli: $cli,
      platform_cli_version: $cli_ver,
      platform_cli_authenticated: ($cli_auth == "true"),
      scripts_installed: ($scripts == "true"),
      scripts_hash: $hash,
      rules_installed: ($rules == "true"),
      probed_at: $now
    }
  '

  echo "PROBED: os=$os jq=$jq_available cli=$platform_cli authenticated=$platform_cli_authenticated"
}

# ── Domain: config ────────────────────────────────────────────────────────────

cmd_config() {
  local action="${1:?Usage: scd.sh config <action> [args...]}"; shift
  case "$action" in
    update-state) _config_update_state "$@" ;;
    get)          _config_get "$@" ;;
    resolve-model) _config_resolve_model "$@" ;;
    *) echo "Error: unknown config action: $action" >&2; exit 1 ;;
  esac
}

_config_update_state() {
  # scd.sh config update-state [--nested] <config> <field_or_path> <value>
  if [[ "${1:-}" == "--nested" ]]; then
    shift
    local config="${1:?}" path_array="${2:?}" value="${3:?}"
    _check_config "$config"
    _atomic_jq "$config" --argjson path "$path_array" --argjson v "$value" 'setpath(["state"] + $path; $v)'
  else
    local config="${1:?}" field="${2:?}" value="${3:?}"
    _check_config "$config"
    _atomic_jq "$config" --arg f "$field" --argjson v "$value" '.state[$f] = $v'
  fi
}

_config_get() {
  # scd.sh config get <config> <key_path>
  # key_path: dot-notation e.g. "model_profile" or "pipeline.max_parallel_agents"
  local config="${1:?Usage: scd.sh config get <config> <key>}" key="${2:?}"
  _check_config "$config"
  jq -r ".$key // empty" "$config"
}

_config_resolve_model() {
  # scd.sh config resolve-model <config> <agent_name>
  # Returns the model to use for the given agent based on profile + overrides
  local config="${1:?Usage: scd.sh config resolve-model <config> <agent>}" agent="${2:?}"
  _check_config "$config"

  # Check model_overrides first
  local override
  override=$(jq -r --arg a "$agent" '.model_overrides[$a] // empty' "$config" 2>/dev/null || true)
  if [[ -n "$override" ]]; then
    echo "$override"
    return
  fi

  # Lookup in profile
  local profile
  profile=$(jq -r '.model_profile // "balanced"' "$config" 2>/dev/null || echo "balanced")

  # Profile tables
  case "$agent" in
    scout-alpha)
      echo "haiku" ;;
    code-reviewer|test-reviewer)
      case "$profile" in
        quality) echo "inherit" ;;   # opus via inherit (avoids org policy conflicts)
        budget)  echo "sonnet" ;;
        *)       echo "sonnet" ;;    # balanced
      esac ;;
    review-validator)
      case "$profile" in
        quality) echo "sonnet" ;;
        budget)  echo "haiku" ;;
        *)       echo "sonnet" ;;
      esac ;;
    fix-applier)
      case "$profile" in
        quality) echo "inherit" ;;
        budget)  echo "sonnet" ;;
        *)       echo "sonnet" ;;
      esac ;;
    *)
      echo "sonnet" ;;
  esac
}

# ── Main dispatcher ───────────────────────────────────────────────────────────

domain="${1:?Usage: scd.sh <domain> <action> [args...]
  Domains: session | followup | post | validation | context | agent | test | init | config}"; shift

case "$domain" in
  session)    cmd_session "$@" ;;
  followup)   cmd_followup "$@" ;;
  post)       cmd_post "$@" ;;
  validation) cmd_validation "$@" ;;
  context)    cmd_context "$@" ;;
  agent)      cmd_agent "$@" ;;
  test)       cmd_test "$@" ;;
  init)       cmd_init "$@" ;;
  config)     cmd_config "$@" ;;
  *) echo "Error: unknown domain: $domain (valid: session, followup, post, validation, context, agent, test, init, config)" >&2; exit 1 ;;
esac
