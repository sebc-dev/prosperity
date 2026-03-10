#!/usr/bin/env bash
set -euo pipefail

# Usage: classify-followup.sh <previous_session> <diff_output_file>
# diff_output_file: result of `git diff --find-renames --name-status previous_head..HEAD`
# Stdout: JSON classification ready for creating the followup session

previous_session="${1:?Usage: classify-followup.sh <previous_session> <diff_output_file>}"
diff_file="${2:?Missing diff_output_file}"

if [[ ! -f "$previous_session" ]]; then
  echo "Error: previous session not found: $previous_session" >&2
  exit 1
fi

if [[ ! -f "$diff_file" ]]; then
  echo "Error: diff file not found: $diff_file" >&2
  exit 1
fi

diff_content=$(cat "$diff_file")

jq --arg diff "$diff_content" '

  # Parse diff lines into objects
  ($diff | split("\n") | map(select(length > 0)) | map(
    split("\t") |
    if .[0][0:1] == "R" then
      { old: .[1], new: .[2], status: "R" }
    elif .[0] == "D" then
      { old: .[1], new: null, status: "D" }
    else
      { old: null, new: (.[1] // empty), status: .[0] }
    end
  )) as $changes |

  # Sets for classification
  ($changes | map(
    if .status == "R" then .new
    elif .status == "D" then .old
    else .new
    end
  ) | map(select(. != null))) as $modified_paths |

  ($changes | map(select(.status == "R")) |
    if length > 0 then map({(.old): .new}) | add else {} end
  ) as $rename_map |

  ($changes | map(select(.status == "D")) | map(.old)) as $deleted_paths |

  .user_comments as $comments |
  .files as $files |

  # Helper: extract comments for a path ($p captures value, not filter)
  def comments_for($p): [$comments[] | select(.file == $p) | .comment];

  # Helper: format file context ($rtype captures value)
  def format_file($rtype):
    .path as $fpath |
    {
      path: .path,
      category: .category,
      review_type: $rtype,
      original_note: (.note // ""),
      original_blocking: (.blocking // 0),
      original_green: (.green // 0),
      original_yellow: (.yellow // 0),
      original_red: (.red // 0),
      original_observations: (.observations // []),
      original_comments: comments_for($fpath)
    };

  # Corrections: blocking > 0 AND (modified or renamed or deleted)
  [$files[] | select((.blocking // 0) > 0) |
    .path as $p |
    if ($modified_paths | index($p)) then
      format_file("correction")
    elif ($rename_map[$p]) then
      . as $f | .path = $rename_map[$p] |
      format_file("correction") + { original_path: $f.path }
    elif ($deleted_paths | index($p)) then
      format_file("correction") + { resolution: "auto_resolved_deleted" }
    else
      null
    end
  | select(. != null)] as $corrections |

  # Unaddressed: blocking > 0 AND NOT in any change
  [$files[] | select((.blocking // 0) > 0) |
    .path as $p |
    if ($modified_paths | index($p) | not) and
       (($rename_map[$p] // null) == null) and
       ($deleted_paths | index($p) | not) then
      format_file("unaddressed")
    else
      null
    end
  | select(. != null)] as $unaddressed |

  # Paths already handled
  ([$corrections[].path] + [$unaddressed[].path]) as $handled |

  # New: modified files NOT already handled
  [$modified_paths[] |
    . as $p |
    if ($handled | index($p) | not) and ($deleted_paths | index($p) | not) then
      ($files | map(select(.path == $p)) | .[0] // null) as $prev |
      if $prev then
        $prev | format_file("new")
      else
        { path: $p, category: "unknown", review_type: "new",
          original_note: "", original_blocking: 0,
          original_green: 0, original_yellow: 0, original_red: 0,
          original_observations: [], original_comments: [] }
      end
    else
      null
    end
  | select(. != null)] as $new |

  {
    corrections: $corrections,
    unaddressed: $unaddressed,
    new: $new,
    stats: {
      corrections: ($corrections | length),
      unaddressed: ($unaddressed | length),
      new: ($new | length)
    }
  }
' "$previous_session"
