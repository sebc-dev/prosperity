## Why

Les ADR [0018](../../../docs/adr/0018-client-network-boundary-via-lib.md) et
[0019](../../../docs/adr/0019-single-gate-to-postgres.md) ont promu quatre invariants d'architecture
(A10–A13 de `docs/architecture.md`) qui sont vrais aujourd'hui **par habitude** : `client/src/lib`
est la seule zone du client qui parle au réseau et n'importe rien de l'UI ; `backend/shared/db.py`
et `alembic/env.py` sont les seules portes vers Postgres et les migrations n'importent des modules
que leurs `models`. Promus, ils sont opposables en review — mais **rien ne casse en CI** si un hook
importe `openapi-fetch` ou si une migration appelle un `service` : la review est le seul garde, alors
que l'ADR 0005 a son `.importlinter`. Chaque ADR a inscrit ce filet dans ses Conséquences « à poser par
un change » ; c'est celui-ci. Sert **EPIC-19 / STORY-S19.4** (`docs/roadmap/E19-architecture-backend.md`).
Aucun FR de `docs/vision.md` n'est servi directement : c'est un pilier technique, comme S19.1–S19.3.

## What Changes

- **Client — frontière réseau `ui -> lib` dans le lint bloquant** (`client/eslint.config.js`,
  `npm run lint`) : deux blocs `no-restricted-imports`. Sur la zone `ui`
  (`src/{app,pages,features,components,hooks}/**`, hors `*.test.*`), interdire `openapi-fetch`,
  `@powersync/web`, `@microsoft/fetch-event-source` avec un message qui renvoie vers `src/lib/`
  (A10). Sur `src/lib/**`, interdire les patterns `@/app/**`, `@/pages/**`, `@/features/**`,
  `@/components/**`, `@/hooks/**` (A11). `@powersync/react` et `@powersync/drizzle-driver` restent
  libres partout (lecture locale, pas réseau — ADR 0018 §Décision 3).
- **Client — test de la garde** par l'API ESLint (`ESLint.lintText` avec un `filePath` virtuel dans la
  zone visée), sous vitest : une fixture qui viole remonte `no-restricted-imports` en `error`, une
  fixture conforme ne remonte rien, un test de `ui` qui importe `@powersync/web` ne remonte rien.
- **Backend — deux tests unitaires** dans `tests/unit/test_architecture_gates.py`, patron de
  `tests/unit/test_importlinter_coverage.py` : (a) **A13** — les imports `backend.*` d'`alembic/env.py`
  et d'`alembic/versions/*.py` (AST) appartiennent à l'ensemble admis `backend.config`,
  `backend.shared.models`, `backend.modules.<m>.models` ; (b) **A12** — les appels
  `create_async_engine` / `async_engine_from_config` / `create_engine` sous `backend/` et `alembic/`
  n'apparaissent que dans `backend/shared/db.py` et `alembic/env.py`.
- **Docs** : `docs/ci.md` (la ligne « architecture » du backend nomme le test ; côté client, le lint
  porte la frontière) ; `docs/architecture.md` colonne « Vérifié par » de A10–A13 pointe la règle ou
  le test posé au lieu de « à poser par un change ».
- **Écart consigné vis-à-vis de l'ADR 0019** : sa Conséquence « `.importlinter` étendu à `alembic`
  (`root_packages`) » n'est pas réalisable — `alembic/` n'a pas d'`__init__.py` et porte le nom de la
  bibliothèque `alembic` que `env.py` importe (`from alembic import context`) ; grimp chargerait la
  lib. La garde A13 est un test AST de même valeur de preuve. La décision de l'ADR ne change pas ;
  l'ADR (immuable) n'est pas édité, le `design.md` porte l'écart.
- Rien n'est cassant : les quatre gardes sortent **vertes sur la base** (mesure du 2026-09-13 :
  0 import prohibé en production côté client, 2 engines, 7 imports `backend.*` dans `alembic/` tous
  admis). Aucun code de production ne change.

## Capabilities

### New Capabilities
- `architecture-gates` : les filets mécaniques des invariants **promus** de `docs/architecture.md` —
  ce qui échoue en lint ou en test unitaire quand un diff viole A10, A11, A12 ou A13, et ce qui reste
  silencieux quand il les respecte. Première spec de cette capacité ; un futur ADR qui promeut un
  invariant y ajoutera son exigence.

### Modified Capabilities
<!-- `quality-gate` (change `quality-gate-1-lint-strict`, non archivé) n'est pas modifiée : ses
     frontières de zones `boundaries` en `warn` dans la passe `analyse` restent telles quelles ;
     la promotion de l'arête `lib` en `error` et le retrait du bloc `lib` posé ici sont notés
     hors périmètre dans design.md. -->

## Impact

- `client/eslint.config.js` (deux blocs ajoutés), `client/tests/lint/network-boundary.test.ts`
  (nouveau ; `eslint` est déjà en devDependency, aucun paquet ajouté).
- `tests/unit/test_architecture_gates.py` (nouveau ; stdlib `ast` + `pathlib`, aucune dépendance).
- `docs/ci.md`, `docs/architecture.md` (colonne « Vérifié par »), `docs/roadmap/E19-architecture-backend.md`
  (S19.4 déjà ajoutée par ce propose).
- Aucun changement de `.importlinter`, de `pyproject.toml`, de `client/package.json`, du modèle LikeC4
  ni d'aucun code de production. Les checks existants de `.claude/quality.json` (`frontend-lint`,
  `backend-*`) jouent déjà `npm run lint` et `pytest tests/unit/` : les gardes entrent dans la gate
  sans nouveau check.
- Interaction avec `quality-gate-1-lint-strict` : fichiers disjoints (`eslint.config.analyse.js` vs
  `eslint.config.js` ; `tests/lint/boundaries.test.ts` vs `tests/lint/network-boundary.test.ts`) —
  les deux changes sont parallélisables, aucun n'est bloqué par l'autre.
