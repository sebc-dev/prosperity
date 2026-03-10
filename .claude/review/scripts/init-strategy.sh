#!/usr/bin/env bash
set -euo pipefail

# Usage: init-strategy.sh <config> <strategy>
# Sets json_strategy in config.json
# Example: bash .claude/review/scripts/init-strategy.sh .claude/review/config.json jq

config="${1:?Usage: init-strategy.sh <config> <strategy>}"
strategy="${2:?Usage: init-strategy.sh <config> <strategy>}"

if [[ ! -f "$config" ]]; then
  echo "Error: config file not found: $config" >&2
  exit 1
fi

tmp="${config}.tmp"
jq --arg s "$strategy" '.json_strategy = $s' "$config" > "$tmp" && mv "$tmp" "$config"

echo "json_strategy: $strategy"
