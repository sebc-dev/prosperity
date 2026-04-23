#!/usr/bin/env bash
#
# Wipe + seed the Prosperity database with a deterministic demo dataset.
# Requires the backend to be running with SPRING_PROFILES_ACTIVE=dev.
#
# Usage:
#   ./scripts/seed.sh                      # hits http://localhost:8080
#   API=http://other:8080 ./scripts/seed.sh
#
set -euo pipefail

API="${API:-http://localhost:8080}"
URL="$API/api/dev/reset-and-seed"

echo "→ Seeding via $URL"
response=$(curl -sS -w "\n%{http_code}" -X POST -H "Content-Type: application/json" "$URL")
body=$(echo "$response" | sed '$d')
status=$(echo "$response" | tail -n1)

if [[ "$status" != "200" ]]; then
  echo "✗ Seed failed (HTTP $status)"
  echo "$body"
  exit 1
fi

echo "✓ Seeded:"
echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
echo ""
echo "  Login: demo@prosperity.local / demo1234"
