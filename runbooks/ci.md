# Runbook — CI (workflows GitHub Actions)

> Story S18.1 (E18 DevX/CI). `.github/workflows/push.yml` est **path-scopé** : seuls les jobs
> pertinents au périmètre changé tournent, et `ci-required` est l'**unique required check**.
> Logique de gating : `.github/scripts/decide.sh` (testée par `.github/scripts/decide.test.sh`).

## ⚠️ Branch protection — action manuelle (sinon le gating est neutralisé)

Le gating ne sert à rien tant que les *branch protection rules* exigent les jobs individuels :
un job `skipped` (PR docs-only) laisse un check requis « en attente » → **PR bloquée non-mergeable**.

**À faire une fois, sur GitHub** (*Settings → Branches → `main` → Require status checks*) :

1. **Retirer** des checks requis : `backend-lint`, `backend-unit`, `backend-integration`,
   `backend-e2e`, `backend-sync`, `backend-migrations` (et tout autre job individuel).
2. **Ajouter** comme **seul** check requis : **`ci-required`**.

`ci-required` (`needs:` tous les jobs, `if: always()`) passe si chaque job est `success` **ou**
`skipped`, et échoue (allow-list) dès qu'un job requis est `failure`/`cancelled`. Il inclut
`changes` et `ci-selftest` dans son `needs:` → une panne du **gating lui-même** fait échouer le
check (pas de fail-open silencieux).

## Matrice de déclenchement (sur une PR)

`changes` (job) classe les fichiers modifiés via `dorny/paths-filter`, puis `decide.sh` décide :

| Fichiers modifiés (PR) | `backend` | `frontend` (S14.7) | Jobs backend |
|---|---|---|---|
| `backend/**`, `tests/**`, `alembic/**`, `pyproject.toml`, `uv.lock`, `compose/**`, `compose.dev.yml`, `.env.example`, `powersync/**`, `scripts/**` | ✅ | — | **tournent** |
| `client/**` uniquement | — | ✅ | **skipped** |
| `**/*.md`, `docs/**` uniquement | — | — | **skipped** (`ci-required` vert) |
| `.github/workflows/**`, `.github/actions/**`, `.github/scripts/**` | ✅ | ✅ | **full run** (un changement de CI se re-teste) |
| chemin **non classé** (ex. `Makefile`), seul **ou mêlé** à du classé | ✅ (fail-safe) | selon | **tournent** |
| **push `main`** / `workflow_dispatch` | ✅ | ✅ | **full run** (filet post-merge) |

Notes :
- `'**/*.md'` matche aussi `backend/README.md` → une PR ne touchant qu'un README backend skippe
  les jobs backend (volontaire : un README ne casse pas les tests).
- **Fail-safe** : `decide.sh` lance `backend` dès que le filtre `unknown` (négation : tout ce qui
  n'est dans aucune catégorie) est vrai — y compris quand un fichier non classé accompagne un
  fichier `client/**` (on lance plutôt que skipper).

## Ajouter / modifier un périmètre

1. Étendre les filtres de `changes` dans `push.yml` (et la liste de **négations** du filtre
   `unknown` en miroir — sinon un nouveau chemin classé déclencherait le fail-safe à tort).
2. Ajuster `decide.sh` si une nouvelle sortie est nécessaire ; **ajouter le cas** dans
   `decide.test.sh` (couvert par `ci-selftest`).
3. Ajouter le nouveau job au `needs:` de **`ci-required`** (sinon il ne gate pas le required check).

### Coordination S14.7 (#211) — jobs frontend

Les jobs frontend `frontend-lint` / `frontend-unit` / `frontend-build` / `frontend-openapi-check`
sont **livrés ✓ par S14.7** (#211). Ils :
- sont gatés par `if: needs.changes.outputs.frontend == 'true'` (output câblé par S18.1) ;
- utilisent la composite action `./.github/actions/setup-node-cached` (cache npm + node_modules) ;
- sont ajoutés au `needs:` de `ci-required`.

`frontend-lint` lance `npm run lint` **+ `npm run typecheck`** (garantit `tsc --noEmit`, séparé du
`vite build` de `frontend-build`). `frontend-openapi-check` (`npm run gen:api:check`) échoue si le
client typé n'a pas été régénéré depuis `openapi.json`.

## Cache

- **Backend (`uv`)** : `astral-sh/setup-uv` `enable-cache: true` + `cache-dependency-glob: uv.lock`
  sur les 5 jobs backend qui installent (tous sauf le placeholder `backend-sync`) → cache hit visible
  dans les logs.
- **Frontend (npm)** : composite action `setup-node-cached` (cache `~/.npm` + `client/node_modules`).
  ⚠️ **Cache-poisoning** : `node_modules` contient l'addon natif compilé `better-sqlite3`. Mitigations :
  (a) les jobs frontend (S14.7) **ne consomment aucun secret** (`permissions: contents: read`),
  donc un cache empoisonné n'exfiltre rien ; (b) le scoping de cache GHA isole les caches d'une PR de
  ceux de la base (`main`) — une PR ne peut pas écrire dans le scope de la base ; (c) la `key` inclut
  `.nvmrc` (version Node ≈ ABI) → pas de restauration d'un binaire d'une autre ABI.
- **Docker (`powersync-smoke`, nightly)** : les jobs compose **pullent** des images (pas de build).
  **Décision (D6)** : par défaut, **pin par digest** des images dans `compose.dev.yml` (déterminisme) ;
  un cache `save/load` keyé sur les digests résolus n'est ajouté **que si** une mesure prouve un gain
  de pull-time net (sur GitHub les images communes sont souvent déjà chaudes). **Statut** : non
  implémenté (aucune mesure réalisée) — à reprendre comme suivi mesuré.

## Performance des tests backend (vitesse)

Trois leviers, **mesurés** sur la suite d'intégration (1237 tests) :

- **Parallélisme `pytest-xdist`** : `backend-unit` lance `-n auto` ; `backend-integration`
  lance `-n auto --dist loadscope`. `loadscope` groupe les tests par **module** → les fixtures
  `module`/`session` (`committed_engine`, `db_engine`) restent sur un seul worker. Chaque worker
  démarre **son propre** conteneur Postgres (`postgres_container` est session-scopé = par
  processus xdist) → isolation naturelle, aucune coordination inter-worker. Sur un runner GHA le
  nombre de conteneurs = nombre de vCPU (borné).
- **Postgres jetable accéléré** (`tests/conftest.py::postgres_container`) : `fsync=off`,
  `synchronous_commit=off`, `full_page_writes=off`. La base de test étant jetable, la durabilité
  est sans objet → on supprime le coût de sync disque qui domine une suite write-heavy. **Jamais**
  ces flags sur une vraie base.
- **Profil Hypothesis `ci`** (`env: HYPOTHESIS_PROFILE: ci`, 50 exemples vs 100 par défaut) sur
  `backend-unit`/`backend-integration`. Le balayage profond (500) reste au **nightly**
  (`HYPOTHESIS_PROFILE: nightly`). Cf. Stratégie de tests §9.3.

**Mesure de référence (local, 4 workers)** : intégration **829 s → 225 s** (×3,7, mêmes 1237
tests) avec xdist + flags Postgres ; le profil `ci` réduit en plus les modules property-based
(le plus lourd : 70 s → 37 s). Re-mesurer si la suite grossit.

## Validation d'un changement de CI

- **Forme** : `actionlint .github/workflows/*.yml` (local ; gate dur = job `ci-selftest`).
- **Logique de gating** : `bash .github/scripts/decide.test.sh` (force-full / fail-safe / préséance /
  valeurs par défaut + contrat exit-code ; local + `ci-selftest`).
- **Comportement** : PRs synthétiques (docs-only / `client/`-only / backend-only / `.github`-only /
  mixte `client/`+non-classé). Pour valider la branche **échec** de `ci-required` (allow-list) :
  - via un job backend **lourd** : introduire une faute (ex. lint) dans `backend/**` → `backend-lint` rouge ;
  - via un job frontend (gating du **code applicatif**, pas que le lint) : casser un cas de test dans
    `client/src/**` (ex. une assertion de `lib/sse/client.test.ts`) → `frontend-unit` rouge — prouve
    que le job exécute réellement les tests et n'est pas un faux-vert `skipped` ;
  - via le **gating lui-même** (fail-closed) : casser `decide.test.sh` → `ci-selftest` rouge ;
  dans les trois cas, observer `ci-required` **rouge** + PR non-mergeable, puis revert.
- Toute PR touchant `.github/**` force un **full run** (auto-validation).
