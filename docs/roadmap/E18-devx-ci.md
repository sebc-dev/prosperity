# E18 — DevX / CI (optimisation des workflows)

> **Durée estimée** : 1-2 jours
> **Statut** : not started
> **Dépend de** : E01 (workflows `push.yml`/`nightly.yml` posés)
> **Bloque** : — (transverse ; bénéficie à S14.7 #211 qui ajoutera les jobs frontend dans la structure)
> **ADRs activés** : aucun (infra CI, pas de code applicatif)

---

## Objectif

Rendre la CI **proportionnée au changement** : ne lancer que les jobs pertinents au périmètre touché par chaque PR (backend vs frontend vs docs/infra), maximiser le **parallélisme** et le **cache**, sans jamais casser les *required checks* ni la couverture sur `main`.

Aujourd'hui (`push.yml`) tous les jobs backend (`backend-lint`, `backend-unit`, `backend-integration`, `backend-e2e`, `backend-migrations`) tournent sur **chaque** push et PR, **sans filtre de chemin** : une PR docs-only ou `client/`-only paie le plein tarif backend. Le cache `uv` et le parallélisme par job sont déjà en place ; il manque le **gating par périmètre**, l'**agrégateur de statut requis**, et la **structure de cache frontend** (anticipée pour S14.7).

C'est un epic **transverse** (outillage), hors séquence fonctionnelle MVP — comme E17, son numéro ne reflète pas l'ordre d'exécution.

---

## Stories

### S18.1 — CI path-scopée + parallélisme + cache

| Phase | Description | Diff |
|---|---|---|
| **P18.1.1** | Job léger `changes` (filtre de chemins via `dorny/paths-filter`) exposant des outputs `backend`/`frontend`/`docs`/`ci` ; gating `if: needs.changes.outputs.X == 'true'` sur chaque job lourd ; **job agrégateur `ci-required`** (`needs:` tous les jobs, passe si chacun est `success` **ou** `skipped`) → c'est LUI le *required check* GitHub (les jobs skippés ne bloquent plus le merge). Sur push `main`, filet : full run. | ~120 |
| **P18.1.2** | Cache & parallélisme : durcir le cache `uv` existant ; poser la **structure de cache frontend** (`actions/setup-node` `cache: npm` + cache du build natif `better-sqlite3`/`node_modules`) prête pour les jobs de S14.7 ; cache des images/layers Docker pour les jobs `compose` (`powersync-smoke`) ; fail-fast lint avant les jobs coûteux là où le gain > le coût de sérialisation. | ~90 |
| **P18.1.3** | `runbooks/ci.md` : **matrice de déclenchement** (quel chemin → quels jobs), le pattern agrégateur, la liste des *required checks* à régler dans les *branch protection rules*, et la procédure d'ajout d'un nouveau périmètre. | ~60 |

---

## Récapitulatif

| ID | Type | Diff | Cumul |
|---|---|---|---|
| S18.1 (3 phases) | CI path-scopée + cache + runbook | ~270 | ~270 |
| **Total** | **1 story / 3 phases** | **~270 lignes** | |

---

## Critères d'acceptation

- [ ] Une PR **docs-only** ne déclenche **aucun** job lourd backend/frontend (seul `changes` + `ci-required` tournent, verts)
- [ ] Une PR **`client/`-only** ne lance pas les jobs backend (et une PR backend-only ne lancera pas les jobs frontend une fois S14.7 livré)
- [ ] Un changement de `**.github/workflows/**` **relance tout** (filet de sécurité)
- [ ] Sur **push `main`**, la suite pertinente complète tourne (post-merge, filet)
- [ ] Le *required check* (`ci-required`) reste **stable** : il passe quand des jobs sont `skipped`, échoue dès qu'un job requis échoue
- [ ] Cache `uv`/npm effectif (cache hit visible dans les logs) ; jobs en parallèle ; `concurrency` annule les runs obsolètes sur PR
- [ ] `runbooks/ci.md` documente la matrice de déclenchement + les *branch protection rules*

---

## Notes pour l'implémenteur

- ⚠️ **Ne pas** utiliser `paths:`/`paths-ignore:` natifs sur `on:` pour gater : ils filtrent le **workflow entier**, et un *required check* devient alors `skipped` (jamais `success`) → la PR reste **bloquée non-mergeable**. Le pattern monorepo correct est : un job `changes` (path-filter) + `if:` par job + un job **agrégateur toujours lancé** qui synthétise `success | skipped` → c'est cet agrégateur qui est le *required check*.
- **Globs de chemins** : `backend` = `backend/**`, `tests/**`, `alembic/**`, `pyproject.toml`, `uv.lock`, `compose/**`, `scripts/**` ; `frontend` = `client/**` ; `docs` = `**/*.md`, `docs/**` ; `ci` = `.github/workflows/**` (force le full run). Un chemin non classé doit **par défaut** déclencher le périmètre concerné (fail-safe = lancer plutôt que skipper).
- **`push main` vs PR** : path-scoping sur les **PR** (où le gain est maximal et le risque faible — la PR re-tourne au merge) ; sur **push `main`**, lancer le full suite pertinent comme filet post-merge.
- Le `concurrency.cancel-in-progress: true` actuel (push.yml) reste — il annule les runs obsolètes d'une même PR.
- **Frontend** : cette story pose la **structure** (gating + cache) ; les **jobs frontend eux-mêmes** (`frontend-lint`/`frontend-unit`/`frontend-build` : eslint+prettier+tsc, `vitest run`, `vite build` + check régénération OpenAPI/drizzle) sont livrés par **S14.7 (#211)** et se branchent sur les outputs `changes.frontend`. Coordination : S18.1 ne crée pas ces jobs, il garantit qu'ils seront *gated* et *cachés* correctement.
- **better-sqlite3** : addon natif compilé à l'install (vitest node) → prévoir le cache du prebuild/`node_modules` pour éviter une recompilation à chaque run (cf. note S14.3 #207).
- **Sécurité** : conserver `permissions: contents: read` (least-privilege) ; `dorny/paths-filter` est pinné par SHA, pas par tag mouvant. Aucun secret introduit (jobs read-only).
- **Hors scope** : déploiement/release (E16) ; activation des seuils de couverture frontend (S14.7) ; signature/build mobile Capacitor (E14 S14.5).
