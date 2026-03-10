#!/usr/bin/env bash
set -euo pipefail

# Mutations atomiques du sous-objet `state` dans config.json
# Usage:
#   update-config-state.sh <config> <field> <value>
#   update-config-state.sh --nested <config> <path_json_array> <value>
#
# Examples:
#   update-config-state.sh .claude/review/config.json "env_cache" '{"jq":true}'
#   update-config-state.sh --nested .claude/review/config.json '["steps_status","config"]' '"done"'

if [[ "${1:-}" == "--nested" ]]; then
  shift
  config="${1:?Usage: update-config-state.sh --nested <config> <path_json_array> <value>}"
  path_array="${2:?}"
  value="${3:?}"
  tmp="${config}.tmp"
  jq --argjson path "$path_array" --argjson v "$value" 'setpath(["state"] + $path; $v)' "$config" > "$tmp" && mv "$tmp" "$config"
else
  config="${1:?Usage: update-config-state.sh <config> <field> <value>}"
  field="${2:?}"
  value="${3:?}"
  tmp="${config}.tmp"
  jq --arg f "$field" --argjson v "$value" '.state[$f] = $v' "$config" > "$tmp" && mv "$tmp" "$config"
fi
