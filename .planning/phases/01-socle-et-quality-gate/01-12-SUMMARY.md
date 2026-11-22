---
phase: 01-socle-et-quality-gate
plan: 12
subsystem: infra
tags: [quality-gate, selftest, semgrep, zizmor, osv-scanner, stryker, rls, supply-chain]

requires:
  - phase: 01-socle-et-quality-gate
    provides: "runner d'auto-test `quality/selftest/run.ts`, format de cas `expected.json` + `patch`/`apply.ts` et trois cas témoins (plan 01-10) ; checks `sast`, `workflow-audit`, `cve`, `unit`, `mutation`, `escape-hatches`, `integrity`, `integration`, `deps` (plans 01-04 à 01-09)"
provides:
  - "14 cas d'auto-test `quality/selftest/cases/<id>/`, verts sur le vrai dépôt (D-07a), chacun pour la règle attendue"
  - "Test faible déterministe du canari (D-09) : `tests-weak-assertion`, score de mutation mesuré 18,18 % (seuil 80)"
  - "Preuve que le méta-test RLS (D-10), le cliquet d'échappatoires (exclusion de couverture comprise) et les gardes d'intégrité/dépendances mordent"
  - "`integrity-protected-path-changed`, réutilisable comme changement de démonstration par `demo-prs.ts` (plan 01-13)"
affects: [01-13, 01-14, 01-15]

actuals:
  tokens: 4771    # chars/4 sur le diff complet (19 084 caractères)
  tasks: 3
  commits: 4      # MESURÉ : git rev-list --count 8ac5806..HEAD (hors commit de ce SUMMARY)
plan_head_before: 8ac580643875e8d37de91a944ab9c44dce3cc8f2
plan_head_after: 45c2ec65a80e70d3c9237d08297646a23cb6a343

tech-stack:
  added: []
  patterns:
    - "Un cas = une violation, un patch entièrement déterminé ; un cas qui modifie un fichier existant passe par `apply.ts` et échoue en « case-stale » si sa cible a disparu"
    - "Les violations (workflow non épinglé, table sans RLS, lockfile vulnérable, `ms`) ne vivent que dans les cas, jamais dans l'arbre du dépôt"

key-files:
  created:
    - quality/selftest/cases/sast-sql-concatenation/{expected.json,patch}
    - quality/selftest/cases/sast-handler-without-principal/{expected.json,patch}
    - quality/selftest/cases/sast-insecure-random/{expected.json,patch}
    - quality/selftest/cases/wf-unpinned-action/{expected.json,patch}
    - quality/selftest/cases/cve-high-severity/{expected.json,apply.ts}
    - quality/selftest/cases/tests-weak-assertion/{expected.json,apply.ts}
    - quality/selftest/cases/tests-coverage-drop/{expected.json,patch}
    - quality/selftest/cases/escape-hatch-added/{expected.json,patch}
    - quality/selftest/cases/integrity-assertion-removed/{expected.json,apply.ts}
    - quality/selftest/cases/integrity-protected-path-changed/{expected.json,apply.ts}
    - quality/selftest/cases/db-table-without-rls/{expected.json,patch}
    - quality/selftest/cases/deps-added-unapproved/{expected.json,apply.ts}
    - quality/selftest/cases/deps-policy-weakened/{expected.json,apply.ts}
    - quality/selftest/cases/escape-hatch-coverage-ignore/{expected.json,patch}
  modified: []

key-decisions:
  - "`cve-high-severity` : règle figée sur `GHSA-35jh-r3h4-6jhm` (lodash 4.17.20, injection de commande), lue sur la sortie réelle d'osv-scanner ; l'entrée est insérée dans `packages:` et `snapshots:` du lockfile v9, avant `lodash@4.18.1`, sans réinstaller (`install: link`)"
  - "`tests-weak-assertion` remplace `allocate.test.ts` par un texte constant embarqué (un seul test `[selftest:weak-allocate]`, cinq appels, uniquement `ok` vérifié) et supprime `allocate.properties.test.ts` : seul `allocate.ts` est muté"
  - "`integrity-protected-path-changed` abaisse `minTokens` de `.jscpd.json` de 10 (50 vers 40) : un resserrement, donc seule la règle de chemin protégé mord"

patterns-established:
  - "Un patch de création de fichier déclare dans l'en-tête de hunk le nombre exact de lignes ajoutées : `git apply` tolère un compte trop court et tronque silencieusement le fichier (voir Deviations)"

requirements-completed: [QUAL-04, QUAL-05, QUAL-06, QUAL-08, QUAL-09]

coverage:
  - id: D1
    description: "SQL concaténé, handler sans `Principal`, `Math.random` pour un jeton, action non épinglée et CVE de score >= 7 sont chacun rejetés pour la règle attendue"
    requirement: QUAL-04
    verification:
      - kind: other
        ref: "node quality/selftest/run.ts --case 'sast-*,wf-*,cve-*' --report reports/selftest-01-12-qual04.json : 5 cas passed/detected"
        status: pass
    human_judgment: false
  - id: D2
    description: "Le test faible du canari fait échouer `mutation` (`mutation-score-below-break`) et une branche non testée fait échouer `unit` (`coverage-threshold`)"
    requirement: QUAL-05
    verification:
      - kind: other
        ref: "node quality/selftest/run.ts --case 'tests-weak-assertion,tests-coverage-drop,…' --report reports/selftest-01-12-qual0506.json : 5 cas passed/detected"
        status: pass
    human_judgment: false
  - id: D3
    description: "Échappatoire ajoutée, exclusion de couverture `v8 ignore` écrite dans le code, assertion retirée et chemin protégé modifié sont bloqués sans approbation"
    requirement: QUAL-06
    verification:
      - kind: other
        ref: "qual0506 (escape-hatch-added, integrity-assertion-removed, integrity-protected-path-changed) et qual0809 (escape-hatch-coverage-ignore) : passed/detected"
        status: pass
    human_judgment: false
  - id: D4
    description: "Une table à `owner_member_id` sans RLS fait échouer `integration` avec `meta:rls-owner-member-id` (D-10)"
    requirement: QUAL-08
    verification:
      - kind: other
        ref: "node quality/selftest/run.ts --case 'db-*,…' --report reports/selftest-01-12-qual0809.json : db-table-without-rls passed/detected"
        status: pass
    human_judgment: false
  - id: D5
    description: "Dépendance ajoutée sans `deps-approved` (`dependency-added`) et politique pnpm affaiblie (`supply-chain-policy-weakened`) sont bloquées"
    requirement: QUAL-09
    verification:
      - kind: other
        ref: "qual0809 : deps-added-unapproved et deps-policy-weakened passed/detected"
        status: pass
    human_judgment: false

duration: 45min
completed: 2026-11-22
status: complete
---

# Phase 01 Plan 12: Cas d'auto-test sécurité, force des tests, anti-contournement, base et dépendances Summary

**Quatorze cas d'auto-test déterministes (patch ou `apply.ts`) prouvent sur le vrai dépôt que la gate rejette, pour la bonne règle, SQL concaténé, handler sans `Principal`, `Math.random`, action non épinglée, CVE >= 7, test faible (score de mutation 18,18 %), couverture en baisse, échappatoire (`v8 ignore` compris), assertion retirée, chemin protégé, table sans RLS, dépendance non approuvée et politique pnpm affaiblie.**

## Performance

- **Duration:** ~45 min
- **Tasks:** 3 (aucune en TDD : le livrable est un jeu de données de test, vérifié par le runner)
- **Files created:** 14 dossiers de cas (28 fichiers), aucun code de production
- **Commits de tâche :** 3, plus 1 commit de formatage

## Accomplissements

- **Tâche 1 (QUAL-04)** : `sast-sql-concatenation`, `sast-handler-without-principal`, `sast-insecure-random` (patchs créant `src/shared/selftest-*.ts` et `src/mcp/tools/selftest-handler.ts`), `wf-unpinned-action` (`.github/workflows/selftest.yml` avec `actions/checkout@v4`, règle `unpinned-uses` de zizmor), `cve-high-severity` (lodash 4.17.20 dans le lockfile, règle `GHSA-35jh-r3h4-6jhm`). 5 cas verts.
- **Tâche 2 (QUAL-05, QUAL-06)** : `tests-weak-assertion`, `tests-coverage-drop`, `escape-hatch-added` (`@ts-expect-error` décrit), `integrity-assertion-removed`, `integrity-protected-path-changed`. 5 cas verts.
- **Tâche 3 (QUAL-06, QUAL-08, QUAL-09)** : `db-table-without-rls` (migration 0002 jouée sous `prosperity_migrator` dans le Postgres 18 du test), `deps-added-unapproved` (`ms` 2.1.3, `link`), `deps-policy-weakened` (`minimumReleaseAge` 10080 vers 1440), `escape-hatch-coverage-ignore` (`/* v8 ignore next */` sur une branche `else` non testée, règle `v8 ignore`). 4 cas verts.

### Mesure du test faible (T-01-47)

Rejoué à part dans un worktree jetable, avec le même patch : `quality/run.ts --only mutation` sur le diff du cas.

- Fichier muté : `src/shared/money/allocate.ts` seul (36 survivants, tous sur ce fichier)
- **Score : 18,18 % (8 mutants détectés sur 44), seuil `thresholds.mutation.break` = 80**
- **Survivants : 36** (mutateurs `ConditionalExpression`, `EqualityOperator`, `LogicalOperator`, `MethodExpression`, `ArrowFunction`, `ArithmeticOperator`)
- Issue de tête : `mutation-score-below-break`, « score 18.18 % sous le seuil 80 % »

## Task Commits

1. **Tâche 1 : cas QUAL-04** - `3becb34` (feat)
2. **Tâche 2 : cas QUAL-05 et QUAL-06** - `63bf14c` (feat)
3. **Tâche 3 : cas QUAL-08, QUAL-09 et `v8 ignore`** - `e4e6ffe` (feat)
4. **Mise en forme Biome de `cve-high-severity/apply.ts`** - `45c2ec6` (style)

**Plan metadata :** commit de ce SUMMARY (docs)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] En-tête de hunk trop court dans `wf-unpinned-action/patch`**
- **Found during:** Tâche 1 (premier run : `wf-unpinned-action` rouge, `not-detected (statut passed)`)
- **Issue :** le hunk annonçait 12 lignes pour 13 ; `git apply` a accepté le patch et tronqué la dernière ligne (`persist-credentials: false`), laissant `with:` vide. zizmor a alors écarté le fichier (« input does not match expected validation schema », simple WARN) et le check `workflow-audit` est passé.
- **Fix :** en-tête corrigé en `+1,13`. Cas vert pour `unpinned-uses`.
- **Files modified:** `quality/selftest/cases/wf-unpinned-action/patch`
- **Commit:** `3becb34` (corrigé avant le commit)

**2. [Rule 1 - Bug] Mise en forme Biome de `cve-high-severity/apply.ts`**
- **Found during:** vérification finale (`pnpm quality`, check `format` rouge, 1 fichier)
- **Fix :** `biome format --write`, deux lignes réécrites.
- **Commit:** `45c2ec6`

**Total deviations:** 2 auto-fixed (2 Rule 1). **Impact :** aucun seuil, ignore ou échappatoire ajouté ; aucun contrat modifié.

## Issues Encountered

- **Fragilité observée, hors périmètre (à signaler, non corrigée) :** le check `workflow-audit` rend `passed` quand zizmor ne peut pas valider un workflow (schéma invalide, simple WARN sur stderr) : un workflow cassé est donc ignoré au lieu d'être refusé. À traiter côté plan 01-08 (ou nightly) si on veut que « workflow illisible » échoue.
- **Flake ponctuel de `sast` :** un run de `sast-handler-without-principal` (cinq cas lancés ensemble) a rendu `tool-error` (`tool-failure`), puis vert à tous les runs suivants (dont le run de vérification final). Vraisemblablement un échec réseau transitoire du registre Semgrep (`p/typescript`, etc. sont téléchargés à chaque run). Non reproduit ; à surveiller au plan 01-13 (27 cas en parallèle).
- `lint-security` (advisory) est passé de 159 à 171 issues (nouveaux fichiers sous `quality/selftest/cases/`) ; sans effet sur le verdict.
- Le garde de commande de l'agent refuse les commandes mêlant `git` à d'autres commandes, ou dont le texte cite `.github` ; les vérifications ont été jouées en commandes séparées avec les mêmes contrôles.
- `pnpm install` a dû être joué dans le worktree (`--frozen-lockfile --offline`), `node_modules` n'étant pas versionné.

## Known Stubs

Aucun.

## Threat Flags

Aucun nouvel élément de surface hors du `<threat_model>`. Mitigations jouées : T-01-47 (patch fixe, portée de mutation limitée à `allocate.ts`, score consigné), T-01-48 (`test -f` sur le workflow et `selftest-ignored.ts` : absents ; `db/migrations` ne contient que `0001_foundation.sql` ; `git diff --exit-code` sur `src/shared/money`, `.jscpd.json`, `package.json`, `pnpm-workspace.yaml` : vide ; aucun worktree `selftest-` restant), T-01-SC (aucun paquet ajouté au dépôt).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Les 14 cas sont rejouables par `node quality/selftest/run.ts --case '<globs>'` ; le plan 01-13 joue l'ensemble (27 cas avec le plan 01-11) et peut réutiliser `integrity-protected-path-changed` comme changement de démonstration.
- Les cas `integration` (Docker) et `cve`/`deps` (réseau) exigent leurs services ; sans Docker, `integration` rend `docker-unavailable` et le cas est rouge, jamais vert par accident.
- Gate complète sur le dépôt : `verdict : pass`.

## Self-Check: PASSED

- Dossiers de cas présents : 14 de ce plan, plus 3 témoins (17 au total dans ce worktree), chacun avec `expected.json` et exactement un fichier parmi `patch` et `apply.ts`.
- Commits présents : `3becb34`, `63bf14c`, `e4e6ffe`, `45c2ec6` (ancêtres de HEAD).
- Rapports de vérification : `reports/selftest-01-12-qual04.json` (5/5), `…-qual0506.json` (5/5), `…-qual0809.json` (4/4), tous `passed`.
- `pnpm quality` : `verdict : pass`.
