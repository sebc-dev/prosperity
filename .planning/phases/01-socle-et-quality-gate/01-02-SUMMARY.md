---
phase: 01-socle-et-quality-gate
plan: 02
subsystem: infra
tags: [quality-gate, typescript, eslint, biome, supply-chain, pnpm]

requires:
  - phase: 01-socle-et-quality-gate
    provides: "squelette `pnpm quality`, contrat `CheckDefinition`/`CheckResult`, `quality/tools.ts`, politique pnpm (plan 01-01)"
provides:
  - "Checks bloquants `typecheck` (tsc, identifiants `TSnnnn`), `format` (Biome formateur seul) et `lint` (ESLint type-aware, `--max-warnings` lu dans `quality/thresholds.json`)"
  - "`tsconfig.json` strict (noUncheckedIndexedAccess, exactOptionalPropertyTypes, erasableSyntaxOnly, lib ESNext.Temporal)"
  - "`eslint.config.mjs` : assertions `as`/`any`/`!` interdites, complexité plafonnée, règles domaine, hygiène des directives, règles de tests"
  - "`quality/thresholds.json` et `quality/layout.json` : source unique des seuils et des globs de couche, consommée par les plans 01-03, 01-06, 01-08, 01-09"
  - "`verifyNpmToolVersion` (`quality/tools.ts`) et `quality/check-kit.ts` (assemblage de résultat partagé par les checks)"
  - "Table des versions de dépendances approuvée par l'humain pour toute la phase (voir plus bas)"
affects: [01-03, 01-04, 01-05, 01-06, 01-07, 01-08, 01-09, 01-10, 01-11, 01-14]

actuals:
  tokens: 8100   # chars/4 sur le diff hors pnpm-lock.yaml (32 647 caractères)
  tasks: 3
  commits: 2     # MESURÉ : git rev-list --count d4238f0..144aa39 (la tâche 1 est une décision humaine sans commit)
plan_head_before: d4238f0e8f974958f8f672583b1b7371e313cf22
plan_head_after: 144aa39e9c80d8d90dd0219a5438f89740269fb8

tech-stack:
  added:
    - "eslint 10.15.0"
    - "typescript-eslint 8.72.2"
    - "eslint-plugin-sonarjs 4.2.2"
    - "@eslint-community/eslint-plugin-eslint-comments 4.8.1"
    - "@vitest/eslint-plugin 1.6.28"
    - "eslint-plugin-security 4.2.1"
    - "@biomejs/biome 2.6.7"
    - "@types/node 26.6.6"
  patterns:
    - "Les seuils et les globs de couche vivent dans deux fichiers JSON ; `eslint.config.mjs` les importe avec `with { type: 'json' }`"
    - "Verdict d'un check tiré de la sortie structurée (tsc texte, `eslint --format json`, `biome --reporter=json`) ; un code non nul sans issue lisible est un échec `tool-error`, jamais un succès"
    - "Version d'un outil npm vérifiée contre le pin exact de `package.json` (`verifyNpmToolVersion`)"

key-files:
  created:
    - tsconfig.json
    - biome.json
    - eslint.config.mjs
    - quality/thresholds.json
    - quality/layout.json
    - quality/check-kit.ts
    - quality/checks/typecheck.ts
    - quality/checks/format.ts
    - quality/checks/lint.ts
  modified:
    - package.json
    - pnpm-lock.yaml
    - quality/tools.ts
    - quality/run.ts
    - quality/checks/workflow-lint.ts

key-decisions:
  - "Dépendances : option (a) de Q1, versions cibles de CLAUDE.md quand elles ont plus de 7 jours, sinon pin de repli ; aucune liste d'exclusion d'âge (approuvé par l'humain, tâche 1)"
  - "`globs de couche` : défaut A de Q5 (disposition d'ARCHITECTURE.md), à confirmer au point de relecture D-01 du plan 01-14 ; changer la disposition ne touche que `quality/layout.json`"
  - "Les exceptions de `no-restricted-syntax` (Number( dans les DTO, Date dans le Clock, process.env dans config) sont générées bloc par bloc depuis `layout.json`, avec Math.round maintenu sur un fichier d'exception qui vit dans le périmètre pur (src/shared/clock.ts)"

requirements-completed: [QUAL-02, QUAL-09]

coverage:
  - id: D1
    description: "`pnpm quality --only typecheck` échoue sur un accès indexé non vérifié avec l'identifiant `TS2322`"
    requirement: QUAL-02
    verification:
      - kind: other
        ref: "fichier quality/zz-neg-types.ts (`const first: number = xs[0]`) : code de sortie 1, reports/gate.json contient `\"rule\": \"TS2322\"`"
        status: pass
    human_judgment: false
  - id: D2
    description: "`pnpm quality --only lint` échoue sur `as` (`@typescript-eslint/consistent-type-assertions`), sur `any`, sur `!`, sur une complexité cognitive > 10, sans avertissement toléré"
    requirement: QUAL-02
    verification:
      - kind: other
        ref: "src/zz-neg-lint.ts (`as number`) : code 1 avec la règle attendue ; lot de fichiers jetables : no-explicit-any, no-non-null-assertion, sonarjs/cognitive-complexity, no-restricted-syntax (parseFloat, Number(, new Date, Date.now, process.env, Math.round), no-console, vitest/no-disabled-tests, vitest/no-restricted-matchers, directive inutile (`unused-disable-directive`) et non décrite"
        status: pass
    human_judgment: false
  - id: D3
    description: "`pnpm quality --only format` échoue sur un fichier non formaté par Biome"
    requirement: QUAL-02
    verification:
      - kind: other
        ref: "fichier quality/zz-neg-format.ts mal formaté : code 1, issue `rule: format` avec le chemin du fichier"
        status: pass
    human_judgment: false
  - id: D4
    description: "`mise exec -- pnpm quality` rend `pass` avec `workflow-lint`, `typecheck`, `format`, `lint` passés ; le code de `quality/**` du plan 01-01 est conforme sans directive de désactivation ni seuil assoupli"
    requirement: QUAL-02
    verification:
      - kind: other
        ref: "mise exec -- pnpm quality && lecture de reports/gate.json (verdict pass, 4 checks passed) ; grep -rn 'eslint-disable' quality eslint.config.mjs : aucune ligne"
        status: pass
    human_judgment: false
  - id: D5
    description: "Installation en versions exactes sous `minimumReleaseAge: 10080` sans exclusion d'âge, après validation humaine ; `pnpm install --frozen-lockfile` passe"
    requirement: QUAL-09
    verification:
      - kind: other
        ref: "réponse `approved` de la tâche 1 ; `pnpm add -D --save-exact` puis `pnpm install --frozen-lockfile` (`Lockfile passes supply-chain policies`) ; grep -c minimumReleaseAgeExclude pnpm-workspace.yaml = 0"
        status: pass
    human_judgment: true

duration: ~20min (continuation : tâches 2 et 3 ; tâche 1 exécutée par l'agent précédent)
completed: 2026-11-21
status: complete
---

# Phase 1 Plan 02 : Typage strict, lint et format dans la gate Summary

**Trois checks bloquants dans `pnpm quality` (`typecheck` tsc 6.0.3, `format` Biome 2.6.7, `lint` ESLint 10.15.0 type-aware à zéro avertissement), `tsconfig.json` strict, `eslint.config.mjs` avec règles du domaine et hygiène des directives, et deux fichiers JSON uniques pour les seuils et les globs de couche, le tout sous la politique supply-chain de pnpm après validation humaine de la table de versions.**

## Performance

- **Duration :** ~20 min pour cette continuation ; la tâche 1 (checkpoint) a été exécutée par l'agent précédent
- **Tasks :** 3 (1 checkpoint humain sans commit, 2 auto)
- **Files :** 9 créés, 5 modifiés (hors `pnpm-lock.yaml`)
- **Commits (mesurés) :** `git rev-list --count d4238f0..144aa39` donne 2

## Tâche 1 : réponse humaine et table des versions approuvées

Réponse humaine au checkpoint `human-verify` (`gate="blocking-human"`) : **`approved`**, « installer la table telle quelle ». Aucun `pnpm add` d'un paquet `SUS` n'a eu lieu avant cette réponse (`git log -p -- package.json` ne montre que `typescript` avant le commit de la tâche 2).

Table approuvée (âges mesurés le 2026-11-21 19:26 UTC par `npm view <paquet> time --json`, seuil `minimumReleaseAge` 10080 minutes = 7 jours, option (a) de Q1, aucune exclusion d'âge). Les plans 01-03, 01-05 et 01-09 installent leurs lignes depuis cette table.

| Paquet | Version | Note |
|---|---|---|
| eslint | 10.15.0 | cible |
| typescript-eslint | 8.72.2 | repli (8.73.0 mûrit le 2026-11-23) |
| eslint-plugin-sonarjs | 4.2.2 | |
| @eslint-community/eslint-plugin-eslint-comments | 4.8.1 | |
| @vitest/eslint-plugin | 1.6.28 | |
| eslint-plugin-security | 4.2.1 | |
| @biomejs/biome | 2.6.7 | repli (2.6.8 mûrit le 2026-11-22) |
| @types/node | 26.6.6 | |
| vitest, @vitest/coverage-v8 | 5.1.0 | repli (5.1.1 mûrit le 2026-11-25) |
| fast-check | 4.10.2 | repli (4.10.3 mûrit le 2026-11-25) |
| @fast-check/vitest | 0.5.0 | |
| @stryker-mutator/core, @stryker-mutator/vitest-runner, @stryker-mutator/typescript-checker | 10.1.1 | |
| dependency-cruiser | 18.7.2 | repli (18.8.0 mûrit le 2026-11-23) |
| knip | 6.45.1 | repli (6.47.0 mûrit le 2026-11-27) |
| jscpd | 5.4.3 | |
| kysely | 0.29.9 | |
| pg, @types/pg | 8.23.1 | |
| testcontainers, @testcontainers/postgresql | 12.2.1 | repli (12.2.2 mûrit le 2026-11-26) |

Tous les verdicts `SUS` avaient pour seule raison `too-new`. Aucun paquet hors de cette liste. Ce plan a installé les huit premières lignes de la table qui concernent le lint, les types et le format : `@types/node`, `eslint`, `typescript-eslint`, `eslint-plugin-sonarjs`, `@eslint-community/eslint-plugin-eslint-comments`, `@vitest/eslint-plugin`, `eslint-plugin-security`, `@biomejs/biome`, tous en versions exactes (`--save-exact`).

## Accomplishments

- `typecheck` : `tsc --noEmit -p tsconfig.json --pretty false`, issues `TSnnnn` extraites des lignes `chemin(ligne,col): error TSnnnn`, codes 0, 1 et 2 lus comme résultats normaux, tout autre code ou code non nul sans erreur lisible en `tool-error`.
- `format` : `biome format --reporter=json` (sans écriture), une issue `rule: format` par fichier non conforme ; configuration Biome formateur seul (linter et assist désactivés, espaces, largeur 100, guillemets simples).
- `lint` : `eslint . --format json --max-warnings <lint.maxWarnings>` ; une directive de désactivation inutile (`ruleId` nul) sort en `unused-disable-directive`.
- `eslint.config.mjs` : `strictTypeChecked` + `stylisticTypeChecked`, `sonarjs` recommandé, hygiène des directives (`require-description`, `no-unlimited-disable`, `no-unused-disable`, `disable-enable-pair`), `reportUnusedDisableDirectives: 'error'`, règles de tests Vitest, règles du domaine pour `src/**`.
- Le code de `quality/**` du plan 01-01 est conforme au typage, au lint et au format sans aucun commentaire de désactivation ni seuil assoupli (six corrections : ternaire imbriqué, `String()` superflu, deux tris sans comparateur, regex à retour arrière, conversion de chaîne).

## Task Commits

1. **Tâche 1 : vérification de légitimité des dépendances** - aucun commit (checkpoint `human-verify`, réponse `approved`)
2. **Tâche 2 : typage strict, format, installation** - `1df04a8` (feat)
3. **Tâche 3 : lint, seuils et globs uniques** - `144aa39` (feat)

## Constats

- **Règles du domaine par exception de fichier.** Dans une config plate, un bloc postérieur remplace la liste `no-restricted-syntax` d'un bloc antérieur. Le fichier de configuration génère donc un bloc par exception (DTO, Clock, config) à partir de `layout.json`, chaque bloc portant la liste complète moins le sélecteur levé. Vérifié par des fichiers jetables : `Number(` passe dans `src/mcp/contracts/**` et reste interdit ailleurs, `new Date` passe dans `src/shared/clock.ts` mais `Math.round` y reste interdit (fichier du périmètre pur), `process.env` passe dans `src/config/**`.
- **`@typescript-eslint` 8.72.2 avec TypeScript 6.0.3** : aucun avertissement de pair à l'installation, lint type-aware opérationnel (`projectService`).
- **Détail du lint.** `sonarjs.configs.recommended` n'a signalé que des motifs réels du code de 01-01 (six issues) ; aucune règle n'a dû être désactivée.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Assemblage de résultat partagé dans `quality/check-kit.ts`**
- **Found during:** Tâche 2
- **Issue :** trois nouveaux checks et `workflow-lint` auraient recopié la même fonction d'assemblage de `CheckResult` ; la gate de duplication (`jscpd`, plan 01-03) l'aurait rejetée.
- **Fix :** création de `quality/check-kit.ts` (`buildResult`, `failedResult`, `versionMismatchIssue`, `toolErrorIssue`) ; `workflow-lint.ts` refactoré dessus ; `isRecord` et `readJsonRecord` exportés depuis `quality/tools.ts`.
- **Files modified :** `quality/check-kit.ts` (nouveau, absent de `files_modified`), `quality/checks/workflow-lint.ts`, `quality/tools.ts`
- **Commit :** `1df04a8`

**2. [Rule 1 - Bug] Motif de directive inutile écrit sans le littéral de la directive**
- **Found during:** Tâche 3
- **Issue :** le motif `/unused eslint-disable directive/` de `lint.ts` contenait le littéral que le contrôle d'acceptation « aucune directive de désactivation dans `quality/` » recherche, ce qui l'aurait fait échouer.
- **Fix :** motif `/unused eslint(?:-)disable directive/i`, avec commentaire explicatif.
- **Files modified :** `quality/checks/lint.ts`
- **Commit :** `144aa39`

**Total deviations :** 2 auto-corrigées. **Impact :** aucun changement de périmètre ; un fichier supplémentaire (`quality/check-kit.ts`) hors de la liste du plan, justifié par la gate de duplication à venir.

## Auth Gates

Aucune. Le checkpoint de la tâche 1 est un `human-verify` de légitimité des paquets, traité comme prévu.

## Known Stubs

Aucun.

## Threat Flags

Aucun. Mitigations du registre de menaces appliquées : T-01-07 (checkpoint humain avant installation, versions exactes, aucune exclusion d'âge), T-01-08 (`strictDepBuilds` inchangé, installation sans construction de paquet), T-01-09 (`require-description`, `no-unused-disable`, `reportUnusedDisableDirectives: 'error'`, `--max-warnings 0` lu dans `thresholds.json`), T-01-SC (aucun paquet `SUS` installé sans la réponse `approved`).

## Notes pour les plans suivants

- `eslint-plugin-security` est installé mais sa passe advisory n'est pas branchée ici ; elle rejoint les checks de sécurité du plan 01-04.
- `@vitest/eslint-plugin` est configuré ; `vitest` lui-même n'est pas encore installé (plan 01-03). Les règles de tests ont été vérifiées sur des fichiers jetables ; elles se re-valideront avec de vrais tests.
- Les globs de `quality/layout.json` sont le défaut A de Q5 : à confirmer au point de relecture D-01 du plan 01-14.

## Self-Check: PASSED

- Fichiers présents : `tsconfig.json`, `biome.json`, `eslint.config.mjs`, `quality/thresholds.json`, `quality/layout.json`, `quality/check-kit.ts`, `quality/checks/typecheck.ts`, `quality/checks/format.ts`, `quality/checks/lint.ts`.
- Commits dans l'historique : `1df04a8`, `144aa39`.
- `mise exec -- pnpm quality` : verdict `pass`, quatre checks `passed`.
