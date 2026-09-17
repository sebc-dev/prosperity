## Context

Voir `proposal.md` — Why. État courant qui façonne l'approche :

- **Client.** `client/eslint.config.js` est une config plate `tseslint.config(...)` (type-checked par
  `projectService`), jouée par `npm run lint` — bloquant en CI et check `frontend-lint` de
  `.claude/quality.json`. Elle ne porte aucune règle d'import. Le change `quality-gate-1-lint-strict`
  (non archivé, 0 ticket livré) posera une **seconde** config `eslint.config.analyse.js` avec
  `eslint-plugin-boundaries` en `warn` ; ses fichiers sont disjoints des nôtres. Les 54 imports
  `ui -> lib` passent tous par l'alias `@/lib/*` (`tsconfig` `paths`) ; aucun import relatif ne
  franchit une zone. `eslint` 9 et `vitest` sont en devDependencies ; il n'existe pas encore de
  `client/tests/lint/`.
- **Backend.** `.importlinter` (`root_package = backend`) garde le graphe des modules (ADR 0005) ;
  `alembic/` n'est **pas** un paquet Python (`alembic/env.py`, `alembic/versions/*.py`, pas
  d'`__init__.py`) et son nom est celui de la bibliothèque `alembic` qu'`env.py` importe. Le patron
  d'un « test d'architecture » existe : `tests/unit/test_importlinter_coverage.py` parse un fichier du
  dépôt et asserte, depuis `tests/unit/` (`uv run pytest tests/unit/ -n auto`, la commande par défaut
  d'un ticket backend selon `docs/ci.md`).
- **Modèle.** `docs/architecture/model.c4` porte `prosperity.client.ui` (5 `sourceDir`),
  `prosperity.client.lib`, `prosperity.api.shared`, `prosperity.api.migrations` (`alembic`) et
  `prosperity.db` ; les relations `ui -> lib`, `lib -> api`, `lib -> powersync`, `shared -> db`,
  `migrations -> db`, `migrations -> {shared, 5 modules}` sont déjà écrites (ADR 0019).

## Goals / Non-Goals

**Goals :**
- Faire échouer `npm run lint` sur une violation de A10 ou A11, et `uv run pytest tests/unit/` sur une
  violation de A12 ou A13, avec un message qui nomme le fichier et l'import ou l'appel fautif.
- Zéro faux positif sur la base : les quatre gardes sont vertes au merge (mesure du 2026-09-13).
- Prouver chaque garde par un test qui **la fait échouer** sur une fixture, pas seulement par « la base
  passe » — un garde qu'on n'a jamais vu rouge n'est pas prouvé.
- Aucun paquet ajouté, aucun code de production modifié, aucune édition de `.importlinter`.

**Non-Goals :**
- Promouvoir l'arête `lib` de `boundaries` en `error` dans `eslint.config.analyse.js`, ou retirer le
  bloc `lib` posé ici quand `boundaries` le couvrira : c'est un ticket de suivi une fois
  `quality-gate-1` ticket 03 mergé, pas ce change.
- Interdire les imports **relatifs** `../components/...` depuis `lib` : `no-restricted-imports` filtre
  la chaîne importée, pas le chemin résolu ; aucun import relatif inter-zone n'existe, et `boundaries`
  (qui résout) les couvrira en avis. Limite déclarée, pas un trou à boucher ici.
- Garder les autres frontières de zones du client (`pages -> app`, etc.) : aucun ADR ne les promeut.
- Un check `.claude/quality.json` dédié : les gardes entrent par les checks existants
  (`frontend-lint`, tests unitaires backend).

## Decisions

1. **Client : `no-restricted-imports` (règle core ESLint) dans `eslint.config.js`, pas une config à
   part ni `eslint-plugin-boundaries`.** Pourquoi : c'est le lint **bloquant** existant — opposable
   dès le merge, sans nouvelle commande ni nouveau check ; aucun paquet ajouté ; indépendant de
   `quality-gate-1` dont rien n'est livré. `boundaries` ferait mieux (résolution des chemins) mais
   n'existe pas encore dans le dépôt et son adoption est le sujet d'un autre change. La règle core
   plutôt que `@typescript-eslint/no-restricted-imports` : les `import type` sont interdits aussi dans
   `ui` en production (un type de `@powersync/web` dans un hook trahit une fuite d'abstraction), et
   les tests sont exemptés par `files`/`ignores`, pas par la règle.
2. **Deux objets de config, un par sens.**
   - Zone `ui` : `files: ['src/{app,pages,features,components,hooks}/**/*.{ts,tsx}']`,
     `ignores: ['**/*.test.{ts,tsx}']`, `paths: [{ name, message }]` pour les trois paquets, le
     message renvoyant vers `src/lib/` (`lib/api`, `lib/powersync`, `lib/sse`).
   - Zone `lib` : `files: ['src/lib/**/*.{ts,tsx}']`, `patterns: [{ group: ['@/app', '@/app/**',
     '@/pages', '@/pages/**', '@/features', '@/features/**', '@/components', '@/components/**',
     '@/hooks', '@/hooks/**'], message }]`. Pas d'`ignores` : un test de `lib` qui importe un
     composant est aussi une inversion.
   Chaque objet porte un commentaire qui cite **ADR 0018** et l'invariant (A10 / A11), dans le ton des
   commentaires existants du fichier (D5, D9, D11).
3. **Test client par l'API programmatique d'ESLint, sous vitest.** `client/tests/lint/network-boundary.test.ts`
   instancie `new ESLint({ cwd: <client/> })` (charge `eslint.config.js`) et appelle
   `lintText(source, { filePath })`. Le `filePath` est celui d'un **fichier réel** de la zone visée
   (`src/hooks/use-current-user.ts`, `src/lib/powersync/connector.ts`, `src/pages/setup.tsx`…) :
   `projectService` exige un fichier connu du `tsconfig` pour typer, et ESLint linte le **texte
   fourni**, pas le disque. Les assertions filtrent `messages` sur `ruleId === 'no-restricted-imports'`
   et `severity === 2` — les autres règles (type-check sur une fixture minimale) ne sont pas le sujet.
   Un test par scénario de la spec, `SC-<NN><lettre>` dans le nom. Alternative écartée : une fixture
   sur disque sous `tests/lint-fixtures/` — elle entrerait dans le périmètre linté ou exigerait un
   `ignores`, et `quality-gate-1` ticket 01 prévoit son propre harnais de fixtures ; ne pas préempter.
4. **Backend : un module `tests/unit/test_architecture_gates.py`, deux fonctions pures + deux tests
   « base propre ».** `_backend_imports(source: str) -> list[str]` parcourt l'AST (`ast.Import`,
   `ast.ImportFrom`, `level == 0`) et rend les noms `backend.*` ; `_is_allowed_migration_import(name)`
   accepte exactement `backend.config`, `backend.shared.models` et le motif
   `backend.modules.<m>.models` (aussi `backend.modules.<m>.models.<x>`).
   `_engine_calls(source) -> list[str]` parcourt les `ast.Call` dont `func` est un `Name` ou un
   `Attribute` d'identifiant dans `{create_async_engine, async_engine_from_config, create_engine}` —
   une mention en docstring ou commentaire n'est pas un `Call`, d'où le scénario « mention sans
   appel ». Les scénarios d'échec sont des `pytest.mark.parametrize` sur des **sources en chaîne**
   (fixtures inline) qui appellent la fonction pure ; les scénarios « base propre » scannent
   `alembic/**/*.py` et `backend/**/*.py` du dépôt (`REPO_ROOT` comme dans
   `test_importlinter_coverage.py`) et assertent `not violations` avec un message qui liste
   `fichier: import|appel`. Pourquoi l'AST et pas `grep` : `create_engine` apparaît en commentaire
   dans `backend/config.py` ; un grep casserait sur la base.
5. **Pas de `.importlinter` pour A13 — écart consigné vis-à-vis de l'ADR 0019 §Conséquences.** La
   Conséquence prévoyait `root_packages = backend, alembic` + contrat `forbidden`. Non réalisable :
   `alembic/` n'est pas un paquet, et `import alembic` résout la bibliothèque (`from alembic import
   context`, `env.py:31`). Renommer le dossier (`migrations/`) est une décision structurante qui
   toucherait `alembic.ini`, la CI, le runbook et le modèle — un ADR, pas ce change. Le test AST a la
   même valeur de preuve (mêmes imports, même échec CI). L'ADR est immuable : il n'est pas édité, et
   `docs/roadmap/E19-architecture-backend.md` §S19.4 porte déjà la note d'écart.
6. **`docs/architecture.md` colonne « Vérifié par »** de A10–A13 : remplacer « à poser par un change »
   par la règle (`client/eslint.config.js` — `no-restricted-imports`, bloc `ui` / bloc `lib`) ou le
   test (`tests/unit/test_architecture_gates.py::test_…`). `docs/ci.md` : la ligne « Lint, format,
   types, architecture » du backend mentionne que les tests unitaires portent aussi des gardes
   d'architecture (A12/A13) ; côté client, une phrase sur le lint qui porte A10/A11. `runbooks/ci.md`
   n'est pas touché : rien ne change dans ce qui bloque une PR (les commandes sont les mêmes).

Conformité aux invariants : le change ne touche aucun code de production ; ses fichiers sont des
configs et des tests. A01–A09 (`backend/modules`) ne sont pas concernés ; A10–A13 sont l'objet même
du change et sortent verts. D01–D09 hors sujet. ADR contraignants : 0018, 0019 (portés), 0005
(patron `.importlinter` non modifié).

## Architecture

**Éléments touchés (FQN) :** `prosperity.client` (`client/eslint.config.js` — rattaché au conteneur,
aucun `sourceDir` de composant ne couvre la racine de `client/`), `prosperity.client.ui` et
`prosperity.client.lib` (les zones que la règle borne — aucun fichier sous leurs `sourceDir` n'est
édité), `prosperity.api.migrations` et `prosperity.api.shared` (les éléments que le test A12/A13
borne — aucun fichier édité). `tests/unit/` et `client/tests/lint/` sont `unmapped` (tests, non
modélisés).

**Relations ajoutées / retirées :** aucune. Les gardes matérialisent des relations **déjà** dans le
modèle (`ui -> lib`, `shared -> db`, `migrations -> db`, `migrations -> {shared, models}`) et
l'**absence** des inverses. Aucun `.c4` édité ; `likec4 validate --no-layout --json --project
prosperity docs/architecture` : valid (état du 2026-09-13).

## Risks / Trade-offs

- [`projectService` refuse un `filePath` virtuel inconnu du tsconfig → le test client casse au
  premier `lintText`] → utiliser le chemin d'un fichier **réel** de la zone ; si un fichier cité est
  un jour renommé, le test échoue avec un message ESLint explicite, pas en silence. Un `it` de garde
  vérifie `existsSync(filePath)` avant de linter.
- [Un import relatif `../../components/x` depuis `lib` passe la règle] → limite déclarée (Non-Goals) ;
  `boundaries` de `quality-gate-1` le couvrira en avis ; aucun cas aujourd'hui.
- [Le bloc `lib` doublonnera `boundaries` quand ticket 03 arrivera] → coût d'un doublon en `error` +
  `warn` sur la même arête : deux messages sur une violation, aucune divergence de verdict. Ticket de
  suivi (retirer le bloc `lib`, promouvoir l'arête en `error`) noté dans la PR du ticket client.
- [Un futur `backend/modules/<m>/models/` en **paquet** (dossier) casse le motif
  `backend.modules.<m>.models`] → le motif accepte `backend.modules.<m>.models` et tout sous-chemin
  `backend.modules.<m>.models.<x>` ; un scénario le couvre.
- [Le scan « base propre » de `backend/**/*.py` lit ~130 fichiers à chaque run unitaire] → `ast.parse`
  de 130 fichiers ≈ centaines de ms, sous `-n auto` ; négligeable devant testcontainers. Pas de cache.
- [`create_engine` synchrone légitime un jour (script de maintenance)] → c'est une violation d'A12
  voulue : le script passe par `shared.db` ou l'ADR 0019 se supersède. Le test le dira.

## Migration Plan

Non applicable : configuration de lint et tests, pas de déploiement. Rollback = revert de la PR.
Les deux tickets (client / backend) touchent des fichiers disjoints et sont parallélisables ; aucune
dépendance entre eux ni avec `quality-gate-1-lint-strict`.
