---
phase: 01-socle-et-quality-gate
plan: 05
subsystem: database
tags: [postgresql, kysely, testcontainers, vitest, roles, migrations, coverage, quality-gate]

requires:
  - phase: 01-socle-et-quality-gate
    provides: "contrat `CheckDefinition`, `quality/check-kit.ts`, `vitest.config.ts` (projet `unit`, périmètre `GATE_COVERAGE_SCOPE`), table de versions approuvée (plans 01-01 à 01-03)"
provides:
  - "Rôles séparés (D-10) : `prosperity_migrator` provisionné hors migration (`src/db/provision.ts`), `prosperity_app` créé par `db/migrations/0001_foundation.sql` sans aucun droit DDL"
  - "`SqlFileMigrationProvider` et `migrateToLatest` (`Migrator` importé de `kysely/migration`), forward-only, erreur qui nomme la migration en échec"
  - "Harnais Testcontainers : un conteneur `postgres:18.7-trixie@sha256:eb63372c…` par run, base template `prosperity_tpl` migrée sous `prosperity_migrator`, une base par fichier de test (`createTestDatabase`, `createEmptyDatabase`)"
  - "Projet Vitest `integration`, tests de fondation et méta-tests (`[meta:rls-owner-member-id]`, `[meta:app-role-no-ddl]`, `[meta:migrator-role]`)"
  - "Checks bloquants `integration` et `coverage` (`ci-only` au pré-push) ; `quality/vitest-kit.ts` partagé avec `unit`"
affects: [01-06, 01-08, 01-09, 01-12, 01-13, 01-14]

actuals:
  tokens: 10800  # chars/4 sur le diff hors pnpm-lock.yaml (43 380 caractères)
  tasks: 3
  commits: 3     # MESURÉ : git rev-list --count 6bfea7a..HEAD (hors commit de ce SUMMARY)
plan_head_before: 6bfea7a387f6adf1585504c88250c80e4616c2ed
plan_head_after: df609b6b6e19bc048cb43e50c5efa3087e11ebe3

tech-stack:
  added:
    - "kysely 0.29.9"
    - "pg 8.23.1 et @types/pg 8.23.1"
    - "testcontainers 12.2.1 et @testcontainers/postgresql 12.2.1"
  patterns:
    - "Le rôle de migration n'a pas de `LOGIN` en test : le pool démarre chaque session sous ce rôle par l'option de connexion `-c role=prosperity_migrator`"
    - "La base template ne garde aucune connexion ouverte (`destroy()` avant toute copie) ; chaque fichier de test copie le template (`CREATE DATABASE … TEMPLATE prosperity_tpl`)"
    - "Un check Vitest est une configuration (`VitestRun`) passée à `runVitestCheck` : projets, rapport, environnement, Docker requis, règle des tests en échec, issues supplémentaires"
    - "`sql.raw` est levé par la configuration ESLint pour le seul fournisseur de migrations, jamais par un commentaire de désactivation"

key-files:
  created:
    - db/migrations/0001_foundation.sql
    - src/db/provision.ts
    - src/db/sql-migration-provider.ts
    - src/db/migrate.ts
    - test/global-setup.ts
    - test/db.ts
    - test/foundation.int.test.ts
    - test/meta.int.test.ts
    - quality/checks/integration.ts
    - quality/checks/coverage.ts
    - quality/vitest-kit.ts
  modified:
    - package.json
    - pnpm-lock.yaml
    - eslint.config.mjs
    - vitest.config.ts
    - stryker.config.mjs
    - quality/checks/unit.ts

key-decisions:
  - "Le rôle de migration démarre ses sessions par `options: '-c role=prosperity_migrator'` : PostgreSQL 18.7 accepte ce paramètre de démarrage, le repli `max: 1` + `SET ROLE` n'a pas été nécessaire"
  - "La couverture des fichiers de `src/db/` est mesurée dans les workers (tests `[foundation:migrate-fresh-db]` et `[foundation:migrate-error-names-migration]`), pas dans `globalSetup` (processus principal non instrumenté)"
  - "Stryker garde le projet `integration` hors de ses runs par la variable `GATE_INTEGRATION=off`, posée par `stryker.config.mjs` (les workers forkés l'héritent)"

patterns-established:
  - "Un test d'intégration obtient sa base par `createTestDatabase()` (copie du template migré) et la supprime par `drop()` en `afterAll`"
  - "Le SQLSTATE d'un rejet se lit par `error instanceof DatabaseError ? error.code : …`, jamais par une assertion de type"

requirements-completed: [QUAL-08, QUAL-05]

duration: ~25min
completed: 2026-11-21
status: complete
---

# Phase 1 Plan 05 : Socle base de données et tests d'intégration sur PostgreSQL 18 réel Summary

**Rôles séparés `prosperity_migrator` (migrations, propriétaire) et `prosperity_app` (sans DDL), migration forward-only `0001_foundation.sql` jouée par le `Migrator` de Kysely sous le rôle de migration sur un PostgreSQL 18.7 Testcontainers épinglé par digest, méta-tests de cloisonnement posés avant toute table, et deux nouveaux checks de gate : `integration` et `coverage` (run fusionné `unit` + `integration`, plancher 85/80 sur tout `src/**`, `src/db` compris).**

## Performance

- **Duration :** ~25 min
- **Tasks :** 3
- **Files :** 11 créés, 6 modifiés (hors `pnpm-lock.yaml`)
- **Commits (mesurés) :** `git rev-list --count 6bfea7a..HEAD` donne 3 (hors le commit de ce SUMMARY)

## Accomplishments

- **Rôles séparés (D-10).** `provisionMigrator(admin)` crée de façon idempotente `prosperity_migrator` (`NOLOGIN NOSUPERUSER NOINHERIT NOCREATEDB CREATEROLE NOBYPASSRLS NOREPLICATION`) hors migration, par un administrateur du cluster. `0001_foundation.sql`, jouée sous ce rôle, crée `prosperity_app` (`NOLOGIN NOINHERIT NOCREATEDB NOCREATEROLE NOBYPASSRLS`), retire `CREATE` sur `public` à `PUBLIC`, crée le schéma `prosperity` (donc possédé par le rôle de migration), accorde `USAGE` et les privilèges par défaut `SELECT, INSERT, UPDATE, DELETE` au rôle app. Aucune table, aucun `ALTER ROLE`.
- **Exécution par Kysely.** `SqlFileMigrationProvider` (fichiers `.sql` triés, clé = nom sans extension, aucun `down`, `sql.raw` levé par la configuration ESLint pour ce seul fichier) et `migrateToLatest` (`Migrator` de `kysely/migration`, erreur qui nomme la migration en échec).
- **Harnais Testcontainers.** `test/global-setup.ts` démarre un conteneur `postgres:18.7-trixie@sha256:eb63372c…`, provisionne le rôle, crée `prosperity_tpl OWNER prosperity_migrator`, vérifie `current_user = prosperity_migrator`, migre, détruit la connexion du template et fournit `pgAdminUri` par `provide()`. `test/db.ts` : une base par fichier de test (`TEMPLATE prosperity_tpl`) et une base vide (`TEMPLATE template0`) pour tester la migration elle-même. Aucun mock.
- **Tests de fondation (7)** : version 18.7, `uuidv7()` de version 7, rejet `42501` du `CREATE TABLE` sous `prosperity_app` dans `prosperity` et `public`, schéma et historique Kysely possédés par `prosperity_migrator`, migration enregistrée, idempotence du provisionnement et de la migration sur base vide, migration invalide nommée dans l'erreur (le fichier `README.txt` est ignoré).
- **Méta-tests (3)** : `[meta:rls-owner-member-id]` (passe à vide, aucune table), `[meta:app-role-no-ddl]` (aucun `CREATE` sur un schéma non système, aucune propriété, attributs du rôle), `[meta:migrator-role]` (ni `SUPERUSER`, ni `BYPASSRLS`, ni `CREATEDB`, rôle app non membre, toute relation de `prosperity` possédée par `prosperity_migrator`).
- **Check `integration`** : `vitest run --project integration`, Docker vérifié d'abord (`docker-unavailable`, jamais `skipped`), un échec = une issue dont la règle est l'identifiant entre crochets, seed dans la note, `skipped: ci-only` en profil push.
- **Check `coverage`** : un seul processus `vitest run --project unit --project integration --exclude 'quality/**' --coverage` avec `GATE_COVERAGE_SCOPE=all` ; `reports/coverage-all/` fusionne les deux projets (total mesuré : 98,43 % lignes, 97,22 % branches ; `migrate.ts` 87,5 % / 80 %, `provision.ts` et `sql-migration-provider.ts` 100 %). Issues : `coverage-threshold`, `coverage-run-test-failed`, `coverage-scope-incomplete` (fichier suivi de `src/db/` absent du rapport, ou aucun `*.int.test.ts` dans le run), `docker-unavailable`.

## Task Commits

1. **Tâche 1 : rôles séparés, migration 0001 et `Migrator` Kysely** - `1489d31` (feat)
2. **Tâche 2 : migration appliquée sur PostgreSQL 18.7 réel via Testcontainers** - `5e60ab3` (feat)
3. **Tâche 3 : méta-tests, checks `integration` et `coverage`** - `df609b6` (feat)

## Preuves de vérification

- `pnpm quality --only typecheck,lint,format` : `pass` après chaque tâche.
- `pnpm vitest run --project integration test/foundation.int.test.ts` : 7 tests passés, ligne `Running tests with seed` présente.
- `pnpm quality --only integration` : `passed`, note `seed 1795292271485 (rejouable : --sequence.seed=…)`, `[meta:rls-owner-member-id]` présent dans `reports/vitest-integration.json` (10 tests au total).
- `pnpm quality --profile push --only integration` et `--only coverage` : `skipped`, `"skipped_reason": "ci-only"`.
- `pnpm quality --only coverage` : `passed` ; résumé fusionné avec les trois fichiers de `src/db/`, le canari `src/shared/money/` et un total de 98,43 % / 97,22 %.
- **Contrôle négatif du plancher sur `src/db/`** : un fichier non testé de 300 branches ajouté sous `src/db/` fait échouer `coverage` (code 1, deux issues `coverage-threshold`) ; le fichier est supprimé ensuite.
- `DOCKER_HOST=tcp://127.0.0.1:1 pnpm quality --only integration,coverage` : les deux checks échouent avec `docker-unavailable`.
- `pnpm quality` complet : verdict `pass` (14 checks) ; `lint-security` est advisory (30 signaux faibles du code de `quality/`, aucun dans `src/db` ni `test/`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Duplication de l'exécution Vitest entre `unit`, `integration` et `coverage`**
- **Found during:** Tâche 3
- **Issue :** trois checks auraient recopié l'analyse du rapport JSON, des lignes de seuil et de la seed ; le futur check de duplication (`jscpd`, plan 01-08) l'aurait rejeté.
- **Fix :** création de `quality/vitest-kit.ts` (`runVitestCheck`, `VitestRun`, `reportFiles`) ; `quality/checks/unit.ts` réduit à sa configuration. Comportement du check `unit` inchangé (vérifié : `passed`, seed, mêmes issues). Les trois fichiers de checks portent chacun la règle `docker-unavailable` ou sa mention en commentaire pour les critères de grep, la logique vit dans le kit.
- **Files modified :** `quality/vitest-kit.ts` (nouveau), `quality/checks/unit.ts` (absents de `files_modified`)
- **Commit :** `df609b6`

**2. [Rule 3 - Blocking] Stryker joue tous les projets Vitest, donc démarrerait PostgreSQL à chaque mutant**
- **Found during:** Tâche 2 (note du SUMMARY 01-03)
- **Issue :** le runner Vitest de Stryker n'a pas d'option de projet ; l'ajout du projet `integration` l'aurait fait entrer dans les runs de mutation (Docker, conteneur par mutant).
- **Fix :** `vitest.config.ts` n'ajoute le projet `integration` que si `GATE_INTEGRATION` n'est pas `off` ; `stryker.config.mjs` pose `GATE_INTEGRATION=off` (les workers forkés héritent de l'environnement). Le check `mutation` reste `passed` sur le plan complet.
- **Files modified :** `vitest.config.ts`, `stryker.config.mjs` (absent de `files_modified`)
- **Commit :** `5e60ab3`

**3. [Rule 1 - Bug] `drop(): Promise<void>` déclaré comme méthode et déstructuré**
- **Found during:** Tâche 2 (lint)
- **Issue :** `@typescript-eslint/unbound-method` signalait trois déstructurations de `drop`.
- **Fix :** propriété `drop: () => Promise<void>` au lieu de la signature de méthode du contrat d'interface (même usage).
- **Files modified :** `test/db.ts`
- **Commit :** `5e60ab3`

**4. [Rule 1 - Bug] Critère `grep -c '42501'` ≥ 2 non satisfait par une assertion sur une seule ligne**
- **Found during:** Tâche 2 (critères d'acceptation)
- **Fix :** deux assertions séparées (`states[0]`, `states[1]`).
- **Files modified :** `test/foundation.int.test.ts`
- **Commit :** `5e60ab3`

**Total deviations :** 4 auto-corrigées. **Impact :** trois fichiers supplémentaires hors de `files_modified` (`quality/vitest-kit.ts`, `quality/checks/unit.ts`, `stryker.config.mjs`) ; fichiers partagés modifiés de façon additive (`package.json`, `pnpm-lock.yaml`, `eslint.config.mjs`, `vitest.config.ts`).

### Adaptations sans écart de contenu

- `migrateToLatest` reçoit le chemin absolu des migrations (`resolve(import.meta.dirname, '..', 'db', 'migrations')`) dans les tests plutôt que `'db/migrations'` : indépendant du répertoire courant du worker.
- L'augmentation du module `vitest` (`ProvidedContext.pgAdminUri`) vit dans `test/global-setup.ts`, comme prévu ; `tsc` la voit pour tout le projet.

## Auth Gates

Aucune.

## Known Stubs

Aucun.

## Threat Flags

Aucun nouveau point de surface hors du `threat_model`. Mitigations appliquées : T-01-17 (attributs du rôle app, `REVOKE CREATE`, tests `42501` et `[meta:app-role-no-ddl]`), T-01-18 (`[meta:rls-owner-member-id]` posé avant toute table ; la preuve qu'il mord relève de l'auto-test du plan 01-12), T-01-19 (image épinglée par digest), T-01-20 (`sql.raw` limité au seul fournisseur par la configuration ESLint ; règle Semgrep `prosperity.sql-concatenation` du plan 01-04), T-01-59 (run fusionné, tests de `src/db/` exécutés dans les workers, `coverage-scope-incomplete`, contrôle négatif), T-01-42 (`current_user` vérifié dans `globalSetup`, tests `[foundation:migrations-run-as-migrator]` et `[meta:migrator-role]`), T-01-SC (uniquement kysely 0.29.9, pg et @types/pg 8.23.1, testcontainers et @testcontainers/postgresql 12.2.1 de la table approuvée, `--save-exact`, politique supply-chain de pnpm respectée).

## Notes pour les plans suivants

- **Plan 01-12 (auto-tests) :** le cas `db-table-without-rls` doit ajouter une table avec `owner_member_id` sans RLS dans une migration jetable et constater l'échec de `[meta:rls-owner-member-id]`. `createTestDatabase()` copie un template migré avec toutes les migrations de `db/migrations`.
- **Plans `knip` et `dependency-cruiser` :** `src/db/**` n'est importé que par `test/**` jusqu'aux phases suivantes ; `test/global-setup.ts` est un point d'entrée Vitest (`globalSetup`). `src/db/migrate.ts` et `provision.ts` ne sont pas importés depuis `src/` : à déclarer comme points d'entrée prévus, sans `ignore` fourre-tout.
- **Plan 01-14 (CI) :** les checks `integration` et `coverage` lancent chacun leur conteneur PostgreSQL ; le runner de CI doit offrir Docker. Variables d'environnement introduites : `GATE_INTEGRATION` (`off` posé par `stryker.config.mjs`).
- **Couverture :** `src/db/migrate.ts` reste à 87,5 % lignes / 80 % branches (la branche « erreur sans résultat de migration » n'est pas atteignable sans simuler une panne du `Migrator`) ; le plancher global (85/80) est tenu largement.
- **Environnement local :** le check `sast` signale `pack-scan-unavailable` (packs Semgrep du registre injoignables hors ligne) : constat du plan 01-04, sans lien avec ce plan.

## Self-Check: PASSED

- Fichiers présents : `db/migrations/0001_foundation.sql`, `src/db/{provision,sql-migration-provider,migrate}.ts`, `test/{global-setup,db,foundation.int.test,meta.int.test}.ts`, `quality/checks/{integration,coverage}.ts`, `quality/vitest-kit.ts`.
- Commits dans l'historique : `1489d31`, `5e60ab3`, `df609b6`.
- `mise exec -- pnpm quality` : verdict `pass`, `integration` et `coverage` passés.
