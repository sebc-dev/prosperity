---
phase: 01-socle-et-quality-gate
plan: 10
subsystem: infra
tags: [quality-gate, selftest, git-worktree, gitleaks, eslint, integrity]

requires:
  - phase: 01-socle-et-quality-gate
    provides: "contrat `CheckDefinition`/`CheckResult`/`CheckContext` (`quality/gate-report.ts`), `quality/check-kit.ts`, `quality/tools.ts` (`runTool`, `runMiseTool`), `quality/protected-paths.{ts,json}`, checks `lint`, `secrets`, `integrity` et `GATE_BASE_DIR`/`GATE_APPROVED_KINDS` (plans 01-01 à 01-09)"
provides:
  - "Runner d'auto-test `quality/selftest/run.ts` (D-07a) : worktrees jetables au HEAD committé, contrôle propre par check, patch ou `apply.ts`, verdict seulement si le check visé échoue pour la règle attendue, `--jobs`, `--case` en globs séparés par des virgules"
  - "Check bloquant `selftest` (`quality/checks/selftest.ts`) : déclencheur D-08, `skip-ci-only` au pré-push"
  - "Champ `CheckContext.selected` et `writeJsonAtomic` (`quality/gate-report.ts`)"
  - "Format des cas `quality/selftest/cases/<id>/` (`expected.json` + `patch` ou `apply.ts`) et trois cas témoins : `lint-type-assertion`, `sec-generated-secret`, `integrity-threshold-lowered`"
  - "Outillage de test `quality/selftest/fixture.ts` (mini-dépôt git avec faux gate), réutilisable par les plans 01-11 à 01-13"
affects: [01-11, 01-12, 01-13, 01-14, 01-15]

actuals:
  tokens: 17350   # chars/4 sur le diff complet (69 415 caractères, hors lockfile)
  tasks: 2
  commits: 3      # MESURÉ : git rev-list --count bee7a97..HEAD (hors commit de ce SUMMARY)
plan_head_before: bee7a97bbb3f3451ae61e4d307d6744f2f689a64
plan_head_after: 435111094de533484397bea86acc79046ae56a69

tech-stack:
  added: []
  patterns:
    - "Un cas d'auto-test est vert seulement si le check visé a échoué pour la règle attendue : un échec d'infrastructure (`tool-error`, `tool-version-mismatch`, `check-crashed`, `config-error`, `invalid-base`, `missing-trusted-report`) n'est jamais une détection, même attendu"
    - "Le cas applique UNE violation sur une copie jetable committée ; le contrôle de causalité joue d'abord le check sur la copie propre"
    - "Le nom d'un worktree jetable porte le pid du lanceur (`selftest-<id>-<pid>-<hex6>`) : un run suivant ne retire que ceux dont le lanceur est mort, jamais ceux d'un run parallèle vivant"
    - "Un secret de test est généré à l'application (`crypto.randomBytes`), jamais committé"

key-files:
  created:
    - quality/selftest/run.ts
    - quality/selftest/case-runner.ts
    - quality/selftest/cases.ts
    - quality/selftest/context.ts
    - quality/selftest/worktrees.ts
    - quality/selftest/fixture.ts
    - quality/selftest/run.test.ts
    - quality/selftest/cycle.test.ts
    - quality/checks/selftest.ts
    - quality/checks/selftest.test.ts
    - quality/selftest/cases/lint-type-assertion/{expected.json,patch}
    - quality/selftest/cases/sec-generated-secret/{expected.json,apply.ts}
    - quality/selftest/cases/integrity-threshold-lowered/{expected.json,apply.ts}
  modified:
    - quality/gate-report.ts
    - quality/run.ts
    - quality/run.test.ts
    - quality/checks/approvals.test.ts
    - quality/checks/deps.test.ts
    - knip.json

key-decisions:
  - "Reconnaissance de la règle attendue : égalité, ou suffixe précédé d'un point (`rules.prosperity.<id>` pour `prosperity.<id>`). Un suffixe sans frontière (`tool-error` pour `error`) ne compte pas"
  - "Les cas (`expected.json`, `patch`, `apply.ts`) sont lus dans le dépôt qui lance le runner, pas dans la copie jetable : un cas non encore committé se joue pendant son écriture. `apply.ts` s'exécute dans un processus `node` séparé (jamais dans celui du runner)"
  - "Les fils reçoivent un environnement local : `GITHUB_ACTIONS`, `CI`, `GITHUB_EVENT_NAME`, `GITHUB_BASE_REF`, `GATE_FORCE_SELFTEST`, `GATE_SELFTEST_CASES` et tout `GIT_*` retirés ; `MISE_TRUSTED_CONFIG_PATHS` complété avec le dossier du run (mise refuse sinon `mise.toml` d'un dossier inconnu). Sans `GIT_*`, un run lancé depuis un hook git ne se trompe pas de dépôt"
  - "Un signal d'arrêt supprime les dossiers du processus ; les entrées de worktree restantes sont prunées au démarrage suivant (`git worktree prune`), les worktrees d'un lanceur mort sont retirés"
  - "`GATE_SELFTEST_CASES` vide équivaut à absent ; non vide, il est passé tel quel à `--case`"

patterns-established:
  - "Plans 01-11 et 01-12 : un dossier de cas par violation, `expected.json` + exactement un fichier parmi `patch` et `apply.ts`, fichiers créés préfixés `selftest-`, `install: link` pour les cas qui modifient `package.json` ou le lockfile"
  - "Les tests de la gate se font sur un mini-dépôt git (`fixture.ts`) dont `quality/run.ts` est un faux gate, jamais sur le vrai dépôt"

requirements-completed: [QUAL-02, QUAL-04, QUAL-06]

coverage:
  - id: D1
    description: "Le runner n'accepte un cas que si le check visé échoue pour la règle attendue ; outil absent, mauvaise règle, patch inapplicable, cas périmé, check passé ou contrôle rouge sont tous rouges"
    requirement: QUAL-02
    verification:
      - kind: test
        ref: "quality/selftest/run.test.ts#matchesExpected ; quality/selftest/cycle.test.ts#ne rend vert que le cas dont le check échoue pour la règle attendue"
        status: pass
    human_judgment: false
  - id: D2
    description: "Contrôle de causalité : chaque check visé est joué une fois sur la copie propre avant les cas, avec l'environnement local et le `--base` du HEAD"
    requirement: QUAL-02
    verification:
      - kind: test
        ref: "quality/selftest/cycle.test.ts#joue le contrôle propre une fois par check avant les cas ; #rend rouge, avec control-failed"
        status: pass
    human_judgment: false
  - id: D3
    description: "`--case` / `GATE_SELFTEST_CASES` : union de globs, élément vide ou sans cas = code 2 sans worktree ni rapport"
    requirement: QUAL-02
    verification:
      - kind: test
        ref: "quality/selftest/run.test.ts#selectCases ; #CLI node quality/selftest/run.ts"
        status: pass
      - kind: other
        ref: "node quality/selftest/run.ts --case 'zz-nomatch-*' --report reports/selftest-nomatch.json : code 2, aucun rapport, aucun worktree"
        status: pass
    human_judgment: false
  - id: D4
    description: "Concurrence (QUAL-03) : cas parallèles isolés, rapport atomique, aucun worktree restant après interruption"
    requirement: QUAL-04
    verification:
      - kind: test
        ref: "quality/selftest/cycle.test.ts#exécute des cas en parallèle sans interférence ; run.test.ts#cleanupStaleWorktrees"
        status: pass
      - kind: other
        ref: "run réel interrompu par SIGTERM : dossiers supprimés, entrée 'prunable' ; le run suivant la prune (git worktree list sans selftest-)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Check `selftest` : déclenché sur chemin protégé en CI (union base et tête), `GATE_FORCE_SELFTEST=1` ou `--only` ; sinon `passed` « non déclenché » ; `skipped: ci-only` au pré-push"
    requirement: QUAL-04
    verification:
      - kind: test
        ref: "quality/checks/selftest.test.ts#check selftest : déclencheur D-08"
        status: pass
      - kind: other
        ref: "pnpm quality --profile push --only selftest : skipped_reason ci-only dans reports/gate.json, aucun worktree selftest-"
        status: pass
    human_judgment: false
  - id: D6
    description: "Trois cas témoins verts sur le vrai dépôt, un par famille (lint, secrets, intégrité), chacun pour sa règle ; secret généré à l'application, aucun jeton littéral"
    requirement: QUAL-06
    verification:
      - kind: other
        ref: "node quality/selftest/run.ts : 3 cas passed/detected (reports/selftest.json), aucun worktree restant ; GATE_FORCE_SELFTEST=1 GATE_SELFTEST_CASES=lint-type-assertion pnpm quality --only selftest : passed"
        status: pass
      - kind: other
        ref: "grep -rnE 'ghp_[0-9A-Za-z]{36}' quality : aucun résultat"
        status: pass
    human_judgment: false

duration: 35min
completed: 2026-11-22
status: complete
---

# Phase 01 Plan 10: Auto-test de la gate Summary

**Un runner joue chaque violation sur une copie jetable du dépôt (worktree git au HEAD committé, vraie configuration) et ne rend un cas vert que si le check visé échoue pour la règle attendue ; trois cas témoins (lint `as`, secret généré, seuil baissé) sont verts sur le vrai dépôt, et le check `selftest` se déclenche en CI sur tout chemin protégé (D-08).**

## Performance

- **Duration:** ~35 min (non chronométré avec précision)
- **Tasks:** 2 (la tâche 1 en cycle TDD : 1 commit rouge, 1 commit vert)
- **Files modified:** 22 (16 créés, 6 modifiés)
- **Auto-test réel des 3 cas :** ~23 s (lint ~10 s, secret ~2 s, intégrité ~1 s)

## Accomplishments

- `quality/selftest/run.ts` : sélection (`selectCases`, union triée de globs, erreur nommée avant tout worktree), `git worktree prune` + retrait des worktrees d'un lanceur mort, un worktree propre `selftest-base-…` (installation, contrôle de chaque check visé), puis un pool de `--jobs` worktrees `selftest-<id>-…`. Chaque cas : application (`git apply --index` ou `apply.ts` dans un processus séparé), commit avec `LEFTHOOK=0` dans le seul processus fils, installation (`frozen`, ou lien symbolique de `node_modules` pour `link`), `node quality/run.ts --only <check> --profile full --base <sha> --report <worktree>/reports/gate.json` avec `GATE_BASE_DIR` = copie propre et `GATE_APPROVED_KINDS` vide. Rapport `reports/selftest.json` écrit atomiquement, tableau imprimé, code 1 si un cas est rouge, 2 sur erreur d'usage.
- Raisons de verdict : `detected`, `not-detected`, `wrong-rule`, `tool-failure`, `check-crashed`, `install-failed`, `case-not-applicable`, `control-failed`, `selftest-error`.
- `quality/checks/selftest.ts` : bloquant, `skip-ci-only`. Déclenché par `--only`, `GATE_FORCE_SELFTEST=1`, ou en CI quand `git diff --name-only <base>...HEAD` contient un chemin de l'union des listes protégées de la base et de la tête ; un diff incalculable déclenche (échec fermé). Chaque cas rouge devient l'issue `case-not-detected:<id>`.
- Trois cas témoins : `lint-type-assertion` (patch créant `src/shared/selftest-cast.ts`), `sec-generated-secret` (`apply.ts`, jeton `ghp_` tiré de `crypto.randomBytes`), `integrity-threshold-lowered` (`apply.ts`, `mutation.break` 80 vers 70, « case-stale » si le seuil n'est plus à 80).
- Gate complète : `verdict : pass` (`selftest` y est `passed`, « non déclenché » en local).

## Task Commits

1. **Tâche 1 (RED)** : tests de `matchesExpected`, `selectCases`, du cycle sur mini-dépôt, du nettoyage, de la CLI et du déclencheur - `604927c` (test)
2. **Tâche 1 (GREEN)** : runner, check `selftest`, `CheckContext.selected`, entrées knip - `dc90c25` (feat)
3. **Tâche 2** : trois cas témoins - `4351110` (feat)

**Plan metadata :** commit de ce SUMMARY (docs)

## TDD Gate Compliance

- **RED** (`604927c`) : 41 tests, 31 en échec sur assertion (stubs de signature seulement, pour qu'aucun échec ne vienne d'un import). Cible : `matchesExpected > pour la règle exacte`, attendu `true`, obtenu `false`.
  Évaluation sémantique : le test cible s'exécute bien et échoue sur l'assertion prévue ; aucun échec de chargement ni de fixture ; les 10 tests verts sont les cas « faux » du stub (`false` attendu).
  **Le classifieur `gsd_run check tdd-red-evidence` a rendu `invalid_record`** (rapports TAP de Vitest avec diffs `toEqual` sur plusieurs lignes : « Non-TAP data in report ») sur `--reporter=tap` comme sur `tap-flat`. L'évaluation machine n'a donc pas pu être obtenue ; elle est remplacée par l'inspection manuelle ci-dessus. Les rapports sont sous `.gsd/tdd-evidence/01-10/` (ignorés par git).
- **GREEN** (`dc90c25`) : 41 tests passent, puis 70 sur les dossiers `quality/selftest` et `quality/checks`.
- **REFACTOR** : aucun commit (le découpage en fichiers de moins de 300 lignes a été fait dans le commit GREEN).

## Files Created/Modified

Voir `key-files` ci-dessus. `quality/**` et `knip.json` sont des chemins protégés : la PR demandera l'approbation de gate.

## Decisions Made

Voir `key-decisions` ci-dessus.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Découpage en plusieurs fichiers (limite `max-lines` 300 de la gate)**
- **Found during:** Tâche 1 (lint)
- **Issue :** un seul `run.ts` (430 lignes) et un seul `run.test.ts` (585 lignes), avec des `describe` de plus de 60 lignes, dépassent `max-lines` et `max-lines-per-function`, bloquants sur `quality/**`. Abaisser un seuil est exclu.
- **Fix :** `run.ts` (orchestration + CLI), `case-runner.ts`, `context.ts`, `cases.ts`, `worktrees.ts` ; tests répartis entre `run.test.ts` (fonctions pures, nettoyage, CLI), `cycle.test.ts` (runner sur mini-dépôt) et `quality/checks/selftest.test.ts` ; helpers dans `fixture.ts`. `run.ts` ré-exporte `runSelftest`, `matchesExpected` et `selectCases` comme le plan le prévoit ; `run.test.ts` contient bien les tables de `selectCases`.
- **Files modified:** les fichiers listés ci-dessus
- **Commit:** `dc90c25`

**2. [Rule 2 - Missing critical] Règle attendue avec frontière, et liste des règles d'infrastructure**
- **Found during:** Tâche 1 (conception de `matchesExpected`)
- **Issue :** « se termine par » sans frontière ferait correspondre `tool-error` à une règle attendue `error`, et un cas dont la règle attendue serait `tool-error` serait vert par accident (menace T-01-33).
- **Fix :** suffixe précédé d'un point seulement (couvre `rules.prosperity.<id>`), et six règles d'infrastructure jamais comptées comme détection. Testé.
- **Commit:** `dc90c25`

**3. [Rule 2 - Missing critical] Environnement des processus fils assaini**
- **Found during:** Tâche 1
- **Issue :** un run lancé depuis un hook git hérite de `GIT_DIR`/`GIT_INDEX_FILE` et agirait sur le mauvais dépôt ; `mise` refuse le `mise.toml` d'un dossier temporaire non approuvé ; `GATE_FORCE_SELFTEST`/`GATE_SELFTEST_CASES` hérités feraient récurser les cas.
- **Fix :** voir `key-decisions` (variables retirées, `MISE_TRUSTED_CONFIG_PATHS` complété).
- **Commit:** `dc90c25`

**4. [Rule 3 - Blocking] Gestion de signal sans commande synchrone du PATH**
- **Found during:** Tâche 1 (lint `sonarjs/no-os-command-from-path` sur `execFileSync('git')`)
- **Fix :** le gestionnaire de `SIGINT`/`SIGTERM` supprime les dossiers (`rmSync`) ; `git worktree prune` au démarrage suivant retire les entrées. Vérifié par un run réel tué en `SIGTERM`.
- **Commit:** `dc90c25`

### Ajouts mineurs hors liste du plan (sans changer un contrat)

- Option `--root <dossier>` de la CLI (défaut : racine du dépôt) pour jouer la CLI sur un mini-dépôt dans les tests ; `GATE_SELFTEST_CASES` est aussi lu par la CLI quand `--case` est absent.
- Champ optionnel `detail` dans chaque cas du rapport (données de diagnostic), `writeGateReport` délègue à `writeJsonAtomic`.
- Les contextes de test existants (`quality/run.test.ts`, `quality/checks/{approvals,deps}.test.ts`) portent désormais `selected: false`.

**Total deviations:** 4 auto-fixed (2 Rule 2, 2 Rule 3). **Impact :** aucun seuil, ignore ou échappatoire ajouté ; le contrat publié (CLI, variables, rapport, règle `case-not-detected:<id>`) est celui du plan.

## Issues Encountered

- `lint-security` (advisory) est passé de 142 à 159 issues : vraisemblablement les nouveaux fichiers sous `quality/` (non ventilé fichier par fichier). Sans effet sur le verdict, advisory.
- Le premier `git worktree list` de la vérification montrait une entrée `selftest-…` : c'était le nom du dossier temporaire des tests (préfixe `selftest-unit-`), pas un worktree restant ; préfixe renommé `gate-fixture-`.
- Le garde de commande de l'agent refuse les commandes mêlant `git` à d'autres commandes (`&&`, `;`) : les vérifications `<automated>` combinées du plan ont été jouées en commandes séparées, avec les mêmes tests.

## Known Stubs

Aucun.

## Threat Flags

Aucun nouvel élément de surface hors du `<threat_model>` du plan. Mitigations jouées : T-01-31 (jeton généré, `grep -rnE 'ghp_[0-9A-Za-z]{36}' quality` vide), T-01-32 (`LEFTHOOK=0` seulement dans l'environnement du fils, nettoyage en `finally` et prune au démarrage), T-01-33 (règle attendue exigée, contrôle propre, `case-not-applicable` et `control-failed` rouges), T-01-SC (aucun paquet ajouté).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Les plans 01-11 et 01-12 ajoutent leurs cas dans `quality/selftest/cases/` au format fixé ici et les jouent avec `node quality/selftest/run.ts --case '<globs>'` ; le plan 01-13 joue les 27 cas et force l'auto-test au nightly (`GATE_FORCE_SELFTEST=1`).
- Le cas `lint-type-assertion` est celui que le scénario `blocked-check` du plan 01-13 réutilise.
- Le runner lit les cas dans le dépôt courant mais applique les violations au HEAD **committé** : un nouveau cas dont le code de gate dépend (check ajouté) doit être committé avant d'être joué.
- Dans un clone neuf, l'installation des worktrees repose sur le store pnpm (`--offline` d'abord, réseau en repli).

## Self-Check: PASSED

- Fichiers créés présents : `quality/selftest/{run,case-runner,cases,context,worktrees,fixture}.ts`, `quality/selftest/{run,cycle}.test.ts`, `quality/checks/selftest{,.test}.ts`, les trois dossiers de `quality/selftest/cases/`.
- Commits présents : `604927c`, `dc90c25`, `4351110` (ancêtres de HEAD).
- Gate complète : `verdict : pass`.
