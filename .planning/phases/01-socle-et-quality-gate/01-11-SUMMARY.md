---
phase: 01-socle-et-quality-gate
plan: 11
subsystem: infra
tags: [quality-gate, selftest, eslint, typescript, dependency-cruiser, knip, jscpd]

requires:
  - phase: 01-socle-et-quality-gate
    provides: "runner d'auto-test `quality/selftest/run.ts`, format de cas `expected.json` + `patch`|`apply.ts`, checks `lint`, `typecheck`, `arch`, `deadcode`, `duplication` (plans 01-01 à 01-10)"
provides:
  - "Six cas d'auto-test QUAL-02 : `lint-explicit-any`, `lint-non-null-assertion`, `lint-cognitive-complexity`, `lint-parsefloat`, `lint-unused-directive`, `types-unchecked-index` (règle TS figée : `TS2322`)"
  - "Quatre cas d'auto-test QUAL-03 : `arch-mcp-imports-db` (`mcp-tools-no-db`), `arch-cycle` (`no-circular`), `deadcode-unused-export` (`exports`), `dup-new-clone` (`new-clone`)"
affects: [01-12, 01-13, 01-14, 01-15]

actuals:
  tokens: 4200   # chars/4 sur le diff (~16 800 caractères, 20 fichiers de cas)
  tasks: 2
  commits: 2     # MESURÉ : git rev-list --count 8ac5806..HEAD (hors commit de ce SUMMARY)
plan_head_before: 8ac580643875e8d37de91a944ab9c44dce3cc8f2
plan_head_after: 76cf6359baf71fb0feaa07feb2cf5800a99997a5

tech-stack:
  added: []
  patterns:
    - "Un cas = une violation ; les fichiers créés portent le préfixe `selftest-` et ne vivent que dans le patch, jamais dans `src/` du dépôt"
    - "Un cas qui modifie un fichier existant passe par `apply.ts` (échec « case-stale » si la cible a disparu) ; un cas qui crée des fichiers passe par `patch`"
    - "La directive de désactivation du cas `lint-unused-directive` vit dans un `patch` sous `quality/` : le compteur d'échappatoires exclut ce dossier"

key-files:
  created:
    - quality/selftest/cases/lint-explicit-any/{expected.json,patch}
    - quality/selftest/cases/lint-non-null-assertion/{expected.json,patch}
    - quality/selftest/cases/lint-cognitive-complexity/{expected.json,patch}
    - quality/selftest/cases/lint-parsefloat/{expected.json,patch}
    - quality/selftest/cases/lint-unused-directive/{expected.json,patch}
    - quality/selftest/cases/types-unchecked-index/{expected.json,patch}
    - quality/selftest/cases/arch-mcp-imports-db/{expected.json,patch}
    - quality/selftest/cases/arch-cycle/{expected.json,patch}
    - quality/selftest/cases/deadcode-unused-export/{expected.json,apply.ts}
    - quality/selftest/cases/dup-new-clone/{expected.json,patch}
  modified: []

key-decisions:
  - "Règle effective du cas `types-unchecked-index` : `TS2322` (`Type 'number | undefined' is not assignable to type 'number'`), émise sous `noUncheckedIndexedAccess`, lue sur la sortie de `tsc` puis figée"
  - "Chaque cas lint a été rejoué isolément sur le fichier créé : exactement une règle se déclenche (aucune règle voisine ne brouille la cause démontrée)"

patterns-established:
  - "Le cas `arch-mcp-imports-db` crée `src/mcp/tools/` et `src/modules/selftest/adapters/db/` seulement dans le worktree jetable : ces dossiers n'existent pas encore dans le dépôt"

requirements-completed: [QUAL-02, QUAL-03]

coverage:
  - id: D1
    description: "Les violations de typage et de lint du critère de succès 2 (`any`, `!`, complexité cognitive > 10, `parseFloat`, directive inutile, accès indexé non vérifié) sont rejetées pour la règle attendue"
    requirement: QUAL-02
    verification:
      - kind: other
        ref: "node quality/selftest/run.ts --case 'lint-explicit-any,lint-non-null-assertion,lint-cognitive-complexity,lint-parsefloat,lint-unused-directive,types-unchecked-index' --report reports/selftest-01-11-qual02.json : 6 cas passed/detected"
        status: pass
    human_judgment: false
  - id: D2
    description: "Les violations d'architecture, de code mort et de duplication du critère de succès 2 (outil MCP -> adapters/db, cycle, export mort, bloc dupliqué) sont rejetées pour la règle attendue"
    requirement: QUAL-03
    verification:
      - kind: other
        ref: "node quality/selftest/run.ts --case 'arch-*,deadcode-*,dup-*' --report reports/selftest-01-11-qual03.json : 4 cas passed/detected"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-11-22
status: complete
---

# Phase 01 Plan 11: Cas d'auto-test QUAL-02 et QUAL-03 Summary

**Dix cas d'auto-test (un par violation) prouvent que la gate rejette `any`, `!`, la complexité cognitive, `parseFloat`, la directive inutile, l'accès indexé non vérifié (`TS2322`), l'import `adapters/db` depuis un outil MCP, le cycle, l'export mort et le bloc dupliqué, chacun pour la règle attendue.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 2
- **Files created:** 20 (10 dossiers de cas), aucun fichier de production ni de configuration modifié

## Accomplishments

- Six cas QUAL-02 (`lint-*`, `types-unchecked-index`), chacun un `patch` qui crée un seul fichier `src/shared/selftest-*.ts` ; rapport `reports/selftest-01-11-qual02.json` : 6/6 `passed` (`detected`).
- Quatre cas QUAL-03 : trois `patch` (`arch-mcp-imports-db` crée un adaptateur db de module et un outil MCP qui l'importe, `arch-cycle` crée deux fichiers qui s'importent, `dup-new-clone` crée deux fichiers de `src/shared/` partageant un bloc de plus de 9 lignes) et un `apply.ts` (`deadcode-unused-export` ajoute un export jamais importé à `money.ts`) ; rapport `reports/selftest-01-11-qual03.json` : 4/4 `passed`.
- Vérification de causalité hors runner : chaque fichier de cas lint, appliqué seul dans le dépôt, ne déclenche que sa règle (`eslint --format json`) ; les cas d'architecture ne produisent que `mcp-tools-no-db` et `no-circular` (`depcruise`) ; `tsc` n'émet que `TS2322`. Les fichiers temporaires ont été retirés (`git status` propre).
- Gate complète : `verdict : pass` (`lint-security` advisory, 161 issues contre 159 avant ce plan).

## Task Commits

1. **Tâche 1 : cas QUAL-02 (typage, lint)** - `3bf92a4` (feat)
2. **Tâche 2 : cas QUAL-03 (architecture, code mort, duplication)** - `76cf635` (feat)

**Plan metadata :** commit de ce SUMMARY (docs)

## Files Created/Modified

Voir `key-files`. `quality/**` est un chemin protégé : la PR demandera l'approbation de gate.

## Decisions Made

Voir `key-decisions`.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Le worktree d'exécution n'avait pas de `node_modules` : `pnpm install --frozen-lockfile --offline` (store local) a suffi, sans modifier le lockfile ni `package.json`.
- Le garde de commande de l'agent refuse les commandes qui mêlent `git` à d'autres commandes : les commandes git ont été jouées séparément. Pour la même raison, le ledger de commits de plan sous le dossier git du worktree n'a pas pu être écrit ; la base `8ac5806` (fournie par l'orchestrateur) a servi à mesurer `commits`.

## Known Stubs

Aucun.

## Threat Flags

Aucun nouvel élément de surface hors du `<threat_model>` du plan. T-01-46 : une violation par cas, vérifiée règle par règle hors runner ; `matchesExpected` exige la règle attendue. T-01-SC : aucun paquet ajouté.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Le plan 01-12 ajoute ses cas (sécurité, tests, intégrité) dans le même dossier ; le plan 01-13 joue l'ensemble des cas au nightly et en CI sur chemin protégé.
- `dup-new-clone` repose sur `.jscpd.json` (`minTokens` 50, `minLines` 5) et `--baseline-from-ref` : abaisser ces seuils sans réviser le cas le laisserait vert, mais la gate d'intégrité protège `.jscpd.json`.

## Self-Check: PASSED

- Dix dossiers de cas présents sous `quality/selftest/cases/`, chacun avec `expected.json` et exactement un fichier parmi `patch` et `apply.ts`.
- Commits présents : `3bf92a4`, `76cf635` (ancêtres de HEAD).
- Gate complète : `verdict : pass`.
