# CI — le cap, en une page

Ce fichier est le **cap CI** que `ticket-briefer` lit pour dériver la commande de test d'un ticket :
s'il existe, il fait foi. Il **résume** ; ce qui bloque une PR, la matrice de déclenchement, le cache
et la branch protection sont dans [`runbooks/ci.md`](../runbooks/ci.md), qui fait autorité (ne pas
doubler ici).

Dépôt **bi-stack** : backend Python (`uv`, racine du dépôt) et frontend TypeScript (`npm`, dans
`client/`). Un ticket touche en général une seule stack ; la commande de test est celle de sa stack.

## Backend — `uv`, depuis la racine

| Ce que la CI joue | Commande locale | Prérequis |
|---|---|---|
| Lint, format, types, architecture | `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run lint-imports` | — |
| **Tests unitaires** (commande de test par défaut d'un ticket backend) | `uv run pytest tests/unit/ -n auto` | — |
| Tests d'intégration DB | `uv run pytest tests/integration/ --ignore=tests/integration/test_migrations_schema.py -n auto --dist loadscope` | Docker (testcontainers Postgres) |
| Schéma des migrations | `uv run pytest tests/integration/test_migrations_schema.py` | Docker |
| E2E backend | `uv run pytest tests/e2e/` | Docker |

Un ticket qui touche `repository.py`, une migration Alembic ou les sync rules joue aussi les tests
d'intégration. Un test seul : `uv run pytest tests/unit/<fichier>.py::<test> -q`.

## Frontend — `npm`, depuis `client/`

| Ce que la CI joue | Commande locale | Prérequis |
|---|---|---|
| Lint + format | `npm run lint` | — |
| Types | `npm run typecheck` | — |
| **Tests** (commande de test par défaut d'un ticket frontend) | `npm run test` | — |
| Build | `npm run build` | — |
| Client OpenAPI à jour | `npm run gen:api:check` | `openapi.json` régénéré si le backend a changé |

## Ce qui bloque une PR

Le job `ci-required` agrège les jobs déclenchés par les chemins modifiés (matrice dans
`runbooks/ci.md`). Une PR qui ne touche que `docs/**` ou des `*.md` ne joue rien et reste verte. La
quality gate du plugin (`.claude/quality.json`) est volontairement **absente** : lint, typecheck et
tests sont déjà joués par `push.yml`, les rejouer par ticket serait une double exécution. Le filet
escape-hatches du plugin n'est pas posé non plus : les linters le portent (`runbooks/ci.md`
§ Escape-hatches).
