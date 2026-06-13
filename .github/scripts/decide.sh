#!/usr/bin/env bash
# Décide quels périmètres lancer en CI (S18.1, E18). Logique extraite du workflow pour être
# testable hors GitHub (cf. decide.test.sh). Entrées via env (F_* = 'true'/'false' produits par
# dorny/paths-filter), sortie via $GITHUB_OUTPUT. Aucune interpolation ${{ }} ici (anti-injection).
#
#   EVENT      : github.event_name ('pull_request' | 'push' | 'workflow_dispatch')
#   F_BACKEND  : ≥1 fichier dans le périmètre backend
#   F_FRONTEND : ≥1 fichier dans client/
#   F_CI       : ≥1 fichier de CI (.github/**)
#   F_UNKNOWN  : ≥1 fichier hors de TOUTE catégorie connue (fail-safe)
set -euo pipefail

backend="${F_BACKEND:-false}"
frontend="${F_FRONTEND:-false}"

if [ "${EVENT:-}" != "pull_request" ]; then
  # push main / workflow_dispatch → full run (filet post-merge)
  backend=true
  frontend=true
elif [ "${F_CI:-false}" = "true" ]; then
  # un changement de CI se re-teste intégralement
  backend=true
  frontend=true
elif [ "${F_UNKNOWN:-false}" = "true" ]; then
  # fail-safe : ≥1 fichier non classé → on lance plutôt que skipper (même mêlé à du classé)
  backend=true
fi

{
  echo "backend=${backend}"
  echo "frontend=${frontend}"
} >>"${GITHUB_OUTPUT:-/dev/stdout}"
