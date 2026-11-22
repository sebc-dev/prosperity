---
phase: 01-socle-et-quality-gate
plan: 09
subsystem: infra
tags: [quality-gate, dependency-cruiser, knip, jscpd, architecture, dead-code, duplication]

requires:
  - phase: 01-socle-et-quality-gate
    provides: "contrat `CheckDefinition`/`CheckResult`, `quality/check-kit.ts`, `quality/tools.ts` (`runTool`, `isRecord`, `verifyNpmToolVersion`), `quality/layout.json` (`depcruise.*`), `CheckContext.base` (plans 01-01 à 01-05)"
provides:
  - "`.dependency-cruiser.cjs` : 7 règles bloquantes (`no-circular`, `not-to-unresolvable`, `domain-is-pure`, `mcp-tools-no-db`, `cross-module-public-only`, `db-access-restricted`, `no-dev-deps-in-src`), expressions de couche lues dans `layout.json`"
  - "Check bloquant `arch` (`quality/checks/arch.ts`) : verdict lu dans `summary.error` / `summary.violations` du JSON de depcruise"
  - "Check bloquant `deadcode` (`quality/checks/deadcode.ts`) + `knip.json` : une issue par type knip, sans `ignore`"
  - "Check bloquant `duplication` (`quality/checks/duplication.ts`) + `.jscpd.json` : `new-clone` bloque, `clone-in-tests` est consultatif"
  - "Scripts `package.json` : `typecheck`, `lint`, `format`, `test`, `mutation`, `arch`, `deadcode`, `duplication`"
affects: [01-10, 01-11, 01-12, 01-13, 01-14, 01-15]

actuals:
  tokens: 4654   # chars/4 sur le diff complet (18 617 caractères, hors pnpm-lock.yaml)
  tasks: 2
  commits: 2     # MESURÉ : git rev-list --count beb3687..HEAD (hors commit de ce SUMMARY)
plan_head_before: beb368795a620891464f12d3b3bb831ecbfc849a
plan_head_after: ae3c5099a3690df5b01a570425dc85307479d77d

tech-stack:
  added: [dependency-cruiser 18.7.2, knip 6.45.1, jscpd 5.4.3]
  patterns:
    - "Un check lit la sortie structurée de l'outil, jamais son code de sortie seul : depcruise rend 0 avec des violations, jscpd rend 1 pour un clone de test pourtant consultatif"
    - "Un rapport d'outil est supprimé avant le run (`rm`) pour qu'un rapport périmé ne soit jamais lu à la place de celui du run"

key-files:
  created:
    - .dependency-cruiser.cjs
    - knip.json
    - .jscpd.json
    - quality/checks/arch.ts
    - quality/checks/deadcode.ts
    - quality/checks/duplication.ts
  modified:
    - package.json
    - pnpm-lock.yaml
    - quality/gate-report.ts
    - quality/approval-evidence.ts
    - quality/approval-evidence-fixtures.ts
    - stryker.config.mjs

key-decisions:
  - "dependency-cruiser est configuré avec `enhancedResolveOptions` (`exportsFields: ['exports']`, `conditionNames` import/require/node/default/types) : sans cela `kysely/migration` (clé `exports` en chaîne) est signalé non résolu et `not-to-unresolvable` échoue sur du code valide"
  - "`tsPreCompilationDeps: true` : les imports de types seuls (`import type`) sont vus et classés `type-only`, ce qui permet l'exception de `domain-is-pure`"
  - "`db-access-restricted` exclut aussi `depcruise.db` de ses sources : les fichiers de `src/db` s'importent entre eux"
  - "`duplication` ne délègue pas le verdict au code de sortie de `--fail-on-new-clones` (qui compterait aussi les clones de tests) : il lit `duplicates[].isNew` du rapport JSON ; le flag reste dans la commande comme second garde-fou"
  - "knip : les scripts `package.json` (`format`, `lint`, `mutation`, `arch`, `deadcode`, `duplication`…) rendent les binaires visibles ; `eslint.config` de knip liste `eslint.security.config.mjs` pour que `eslint-plugin-security` soit vu utilisé ; `--production` non activé (Q6)"

patterns-established:
  - "Un nouveau dossier de module entre dans `quality/layout.json` et dans `.dependency-cruiser.cjs` dans le même diff (en-tête du fichier)"
  - "Un export, un type ou une dépendance sans usage se supprime ou se dé-exporte ; jamais d'`ignore`"

requirements-completed: [QUAL-03]

coverage:
  - id: D1
    description: "Les frontières d'architecture (`mcp-tools-no-db`, `no-circular`, `domain-is-pure`, `cross-module-public-only`, `db-access-restricted`) font échouer `arch` pour la règle attendue"
    requirement: QUAL-03
    verification:
      - kind: other
        ref: "mise exec -- pnpm quality --only arch avec src/mcp/tools/zz.ts important src/modules/zz/adapters/db/repo.ts : code 1, règle mcp-tools-no-db dans reports/gate.json"
        status: pass
      - kind: other
        ref: "mise exec -- pnpm quality --only arch sur 4 fichiers jetables : cross-module-public-only, domain-is-pure, no-circular, not-to-unresolvable ; sur src/modules/a/application/m.ts important src/db : db-access-restricted, composition/ autorisé"
        status: pass
    human_judgment: false
  - id: D2
    description: "Un export inutilisé fait échouer `deadcode` avec la règle `exports`"
    requirement: QUAL-03
    verification:
      - kind: other
        ref: "ajout de `export const zzUnused = 1;` à src/shared/money/money.ts puis mise exec -- pnpm quality --only deadcode : code 1, règle exports ; fichier restauré (git diff --exit-code propre)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Un clone nouveau hors tests dans `src/` fait échouer `duplication` ; un clone entre fichiers de tests est listé sans bloquer"
    requirement: QUAL-03
    verification:
      - kind: other
        ref: "deux fichiers identiques src/zz/a.ts et b.ts : règle new-clone, check failed ; src/zz/a.test.ts et b.test.ts : règle clone-in-tests, check passed"
        status: pass
    human_judgment: false
  - id: D4
    description: "Le dépôt actuel passe `arch`, `deadcode` et `duplication` sans exception ajoutée, et la gate complète rend `verdict : pass`"
    requirement: QUAL-03
    verification:
      - kind: other
        ref: "mise exec -- pnpm install --frozen-lockfile && mise exec -- pnpm quality : verdict pass, arch/deadcode/duplication passed"
        status: pass
    human_judgment: false

duration: 45min
completed: 2026-11-22
status: complete
---

# Phase 01 Plan 09: Frontières d'architecture, code mort et duplication Summary

**Trois checks bloquants (`arch` par dependency-cruiser, `deadcode` par knip, `duplication` par jscpd) lisent chacun la sortie JSON de leur outil et rendent le dépôt vert sans aucune exception ; la règle `mcp-tools-no-db` interdit à un outil MCP d'atteindre la base.**

## Performance

- **Duration:** 45 min
- **Tasks:** 2
- **Files modified:** 12 (6 créés, 6 modifiés, hors `pnpm-lock.yaml`)

## Accomplishments

- `.dependency-cruiser.cjs` : sept règles `error`, expressions lues dans `quality/layout.json`. `quality/checks/arch.ts` lance `depcruise src --config .dependency-cruiser.cjs --output-type json` et lit `summary.error` et `summary.violations` (code de sortie 0 même en échec, Pitfall 3) ; une violation sans entrée lisible devient `tool-error`, jamais « passé ».
- `knip.json` : entrées explicites (scripts de gate, `test/global-setup.ts`, `test/setup/fast-check.ts`), projet `src/quality/test`, aucun `ignore`. `quality/checks/deadcode.ts` produit une issue par élément de chaque type knip (`files`, `exports`, `types`, `dependencies`, `devDependencies`, `unlisted`, `binaries`, …), la règle étant le type.
- `.jscpd.json` + `quality/checks/duplication.ts` : `jscpd --config .jscpd.json --baseline-from-ref <ctx.base> --fail-on-new-clones`, rapport lu dans `reports/jscpd/jscpd-report.json` après suppression de l'ancien. Les noms du rapport sont relatifs à `src` : le check les préfixe pour les issues.
- Huit scripts `package.json` pour l'humain et pour que knip voie les binaires utilisés.

## Task Commits

1. **Tâche 1 : frontières d'architecture** - `cddc062` (feat)
2. **Tâche 2 : code mort et duplication** - `ae3c509` (feat)

**Plan metadata :** commit de ce SUMMARY (docs)

## Files Created/Modified

- `.dependency-cruiser.cjs` - 7 règles de frontière, `enhancedResolveOptions` pour `exports`
- `quality/checks/arch.ts` - check `arch`
- `knip.json` - entrées et projet explicites, config eslint de knip
- `.jscpd.json` - détection TypeScript sur `src/`
- `quality/checks/deadcode.ts` - check `deadcode`
- `quality/checks/duplication.ts` - check `duplication`
- `package.json`, `pnpm-lock.yaml` - dependency-cruiser, knip, jscpd ; scripts ; suppression de `testcontainers`
- `quality/gate-report.ts`, `quality/approval-evidence.ts`, `quality/approval-evidence-fixtures.ts`, `stryker.config.mjs` - correction des constats knip

## Decisions Made

Voir `key-decisions` ci-dessus. Exception nommée prévue par le plan (`ignoreBinaries: ["mise"]`) : **non nécessaire**, le greffon lefthook de knip ne signale pas `mise`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `kysely/migration` non résolu par dependency-cruiser**
- **Found during:** Tâche 1
- **Issue :** la base de RESEARCH ne passe pas `enhancedResolveOptions` ; `exports["./migration"]` étant une chaîne, `not-to-unresolvable` échouait sur `src/db/migrate.ts` et `src/db/sql-migration-provider.ts`.
- **Fix :** `enhancedResolveOptions: { exportsFields: ['exports'], conditionNames: [...] }` dans `.dependency-cruiser.cjs`.
- **Verification :** `pnpm quality --only arch` passe ; le même run signale toujours un import réellement non résoluble.
- **Committed in:** `cddc062`

**2. [Rule 1 - Bug] Dépendance `testcontainers` jamais importée**
- **Found during:** Tâche 2 (knip `devDependencies`)
- **Issue :** seul `@testcontainers/postgresql` est importé (`test/global-setup.ts`) ; `testcontainers` figurait en direct dans `package.json` (table 01-02).
- **Fix :** retirée de `package.json` ; reste présente en transitif de `@testcontainers/postgresql`. Aucun paquet ajouté.
- **Committed in:** `ae3c509`

**3. [Rule 1 - Bug] Exports inutilisés du code des plans précédents**
- **Found during:** Tâche 2 (knip `exports`/`types`)
- **Issue :** `CheckStatus` (`quality/gate-report.ts`), `PullInfo` (`quality/approval-evidence.ts`), `OTHER_SHA`, `EVENT_PAGES`, `RUN_PAGES` (`quality/approval-evidence-fixtures.ts`) exportés sans usage externe.
- **Fix :** `export` retiré (les symboles restent utilisés dans leur fichier). Aucune règle assouplie.
- **Committed in:** `ae3c509`

**4. [Rule 3 - Blocking] `@stryker-mutator/api` non listé**
- **Found during:** Tâche 2 (knip `unlisted`)
- **Issue :** `stryker.config.mjs` importait un type de `@stryker-mutator/api/core` dans un commentaire JSDoc ; le paquet est transitif, et l'ajouter en direct aurait été un paquet hors de la table approuvée (T-01-SC).
- **Fix :** annotation de type retirée (remplacée par un commentaire) ; aucune option Stryker modifiée. `eslint-plugin-security` et `@biomejs/biome` n'ont demandé qu'une entrée `eslint.config` dans `knip.json` et le script `format`.
- **Committed in:** `ae3c509`

---

**Total deviations:** 4 auto-fixed (3 Rule 1, 1 Rule 3)
**Impact on plan:** corrections nécessaires pour que le dépôt passe `deadcode` sans `ignore`. `stryker.config.mjs`, `quality/**` et `package.json` sont des chemins protégés : la PR demandera l'approbation de gate habituelle. Les paquets dependency-cruiser, knip et jscpd ont été installés ensemble dans le commit de la tâche 1 (une seule mise à jour du lockfile) ; knip et jscpd ne sont utilisés qu'à partir de la tâche 2.

## Issues Encountered

- **Alias shell interactifs** (`cp -i`, `rm -i`) dans l'environnement de l'agent : un premier essai de l'auto-test `deadcode` n'a rien modifié (invites sans réponse) et a rendu `passed` ; refait avec `command cp -f`, fichier restauré (`git diff --exit-code src/shared/money/money.ts` propre). La commande `<automated>` du plan suppose un `cp` non interactif.
- `lint-security` (advisory) reste `failed` avec 142 issues : sans effet sur le verdict, antérieur à ce plan.

## Known Stubs

Aucun.

## Threat Flags

Aucun nouvel élément de surface hors du `<threat_model>` du plan.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- La gate complète est verte (`verdict : pass`) avec `arch`, `deadcode` et `duplication` passés ; le plan 01-10 couvre l'arête de concurrence signalée pour QUAL-03.
- Dès que `src/index.ts` existera (phase 2), activer `knip --production` (Q6, décision réversible à consigner dans `docs/quality-gate.md`, plan 01-13).
- Contre l'ancien `main` Python (première PR), `jscpd` ne voit aucun TypeScript dans la base : tout clone TypeScript est nouveau (voulu, Pitfall 13).

## Self-Check: PASSED

- Fichiers créés présents : `.dependency-cruiser.cjs`, `knip.json`, `.jscpd.json`, `quality/checks/{arch,deadcode,duplication}.ts`.
- Commits `cddc062` et `ae3c509` présents sur la branche.
- Critères d'acceptation : sept règles nommées (7), `layout.json` cité (3), `summary` dans `arch.ts` (5), `"ignore"` absent de `knip.json` (0), `fail-on-new-clones` une fois dans `duplication.ts`, huit scripts, `git diff --exit-code src/shared/money/money.ts` propre.
- `mise exec -- pnpm install --frozen-lockfile && mise exec -- pnpm quality` : `verdict : pass`.

---
*Phase: 01-socle-et-quality-gate*
*Completed: 2026-11-22*
