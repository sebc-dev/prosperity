---
phase: 01-socle-et-quality-gate
plan: 03
subsystem: infra
tags: [quality-gate, vitest, fast-check, stryker, mutation, coverage, money, bigint]

requires:
  - phase: 01-socle-et-quality-gate
    provides: "contrat `CheckDefinition`/`CheckResult`, `quality/check-kit.ts`, `quality/tools.ts`, `quality/thresholds.json`, `quality/layout.json`, table de versions approuvée (plans 01-01 et 01-02)"
provides:
  - "Check bloquant `unit` : Vitest projet `unit` en ordre aléatoire (fichiers et tests), seed dans la note, couverture du périmètre pur à 100 %"
  - "`vitest.config.ts` : seuils tirés de `quality/*.json`, périmètre `GATE_COVERAGE_SCOPE` (`all` par défaut, `pure`, autre valeur = erreur), reporters `text`/`json-summary`/`json`"
  - "Check bloquant `mutation` : Stryker 10.1.1 limité au diff (source colocalisé d'un test modifié inclus), seuil `break` 80, un issue par mutant survivant"
  - "Module canari `src/shared/money` : `Result`, `Money`, `money`, `parseAmount`, `formatMoney`, `allocate`, testé par exemples et par propriétés fast-check"
  - "`quality/run.test.ts` : verdict, profils, écriture atomique, vérification de version, code 2, check `mutation`"
affects: [01-04, 01-05, 01-06, 01-08, 01-09, 01-10, 01-12, 01-13, 01-14]

actuals:
  tokens: 9900   # chars/4 sur le diff hors pnpm-lock.yaml (39 886 caractères)
  tasks: 3
  commits: 6     # MESURÉ : git rev-list --count 415b558..66f47ea (hors commit de ce SUMMARY)
plan_head_before: 415b558e98ed3833a30cf0bbf054a429c601a9c4
plan_head_after: 66f47eaacf03a1bafc024fdd470920ef0c444d4e

tech-stack:
  added:
    - "vitest 5.1.0 et @vitest/coverage-v8 5.1.0"
    - "fast-check 4.10.2 et @fast-check/vitest 0.5.0"
    - "@stryker-mutator/core, vitest-runner, typescript-checker 10.1.1"
  patterns:
    - "Le périmètre de couverture est choisi par la variable `GATE_COVERAGE_SCOPE` lue dans `vitest.config.ts` ; seul le check `unit` pose `pure`, dans l'environnement de son processus fils"
    - "Verdict du check `unit` tiré du rapport JSON de Vitest et des lignes `ERROR: Coverage for …`, jamais du seul code de sortie ; rapport antérieur supprimé avant le run"
    - "Mutation limitée au diff : StrykerJS n'a pas de `--since`, la liste de fichiers est passée par `--mutate a.ts,b.ts`"

key-files:
  created:
    - vitest.config.ts
    - test/setup/fast-check.ts
    - quality/checks/unit.ts
    - quality/checks/mutation.ts
    - quality/run.test.ts
    - stryker.config.mjs
    - src/shared/money/money.ts
    - src/shared/money/money.test.ts
    - src/shared/money/money.properties.test.ts
    - src/shared/money/allocate.ts
    - src/shared/money/allocate.test.ts
    - src/shared/money/allocate.properties.test.ts
  modified:
    - package.json
    - pnpm-lock.yaml
    - eslint.config.mjs

key-decisions:
  - "`disableBail: true` conservé dans `stryker.config.mjs` (mesure de stabilité : 20 exécutions identiques) ; aucune relance des survivants ajoutée, `thresholds.mutation.break` reste à 80"
  - "`formatMoney` n'utilise `Intl.NumberFormat('fr-FR')` que pour le groupement des unités (reçues en `bigint`), pas pour la chaîne décimale entière : voir Deviations"
  - "`allocate` calcule un rang (nombre de parts qui devancent) au lieu de trier : le tie-break par indice n'est plus un mutant équivalent masqué par la stabilité du tri"

patterns-established:
  - "Un test de propriété s'écrit `test.prop([...])(titre, corps)` ; la règle `vitest/no-standalone-expect` le reconnaît par `additionalTestBlockFunctions`"
  - "Un test colocalisé `x.test.ts` ou `x.<suffixe>.test.ts` fait muter `x.ts` quand il est modifié"

requirements-completed: [QUAL-05, QUAL-01]

duration: ~33min (dont ~15 min de mesure de stabilité en arrière-plan)
completed: 2026-11-21
status: complete
---

# Phase 1 Plan 03 : Tests unitaires, couverture et mutation dans la gate Summary

**Vitest 5.1.0 (ordre aléatoire, seed loguée, couverture plancher par périmètre) et Stryker 10.1.1 (mutation limitée au diff, seuil bloquant 80) branchés dans `pnpm quality`, prouvés sur un vrai module canari `src/shared/money` (`bigint` de centimes, plus grand reste, 100 % de couverture, 98,94 % de mutation) testé par exemples et par propriétés fast-check.**

## Performance

- **Duration :** ~33 min (dont ~15 min d'attente de la mesure de stabilité, 20 exécutions de Stryker)
- **Tasks :** 3 (tâche 2 en TDD : RED, GREEN, REFACTOR)
- **Files :** 12 créés, 3 modifiés (hors `pnpm-lock.yaml`)
- **Commits (mesurés) :** `git rev-list --count 415b558..66f47ea` donne 6 (hors le commit de ce SUMMARY)

## Accomplishments

- `vitest.config.ts` : `passWithNoTests: false`, `allowOnly: false`, `sequence.shuffle` sur fichiers et tests, projet `unit` (`src/**/*.test.ts`, `quality/**/*.test.ts`), couverture v8 configurée à la racine. Seuils par glob de `layout.pure` (100 %) et plancher global 85/80, tous lus dans `quality/thresholds.json` et `quality/layout.json`. Aucun dossier de `src/` n'est retiré (`src/db` compris). Périmètre `all` par défaut (`reports/coverage-all`), `pure` pour le check `unit` (`reports/coverage`), autre valeur : erreur à la configuration.
- Check `unit` : `vitest run --project unit --coverage` avec `GATE_COVERAGE_SCOPE=pure` posé dans l'environnement du fils ; une issue par test en échec (identifiant entre crochets en tête de titre, sinon nom complet), une issue `coverage-threshold` par seuil non tenu, un fichier de test en échec sans détail devient `test-file-failed`, la seed va dans `note` (`seed 1795290007384 (rejouable : --sequence.seed=…)`).
- Canari `src/shared/money` : `parseAmount` parseur maison chaîne vers `bigint` (espaces, U+00A0, U+202F, `€` final ignorés, deux décimales au plus, aucun flottant), `money()` n'accepte que `EUR`, `formatMoney` rend « 84,00 € » (U+202F entre milliers, U+00A0 avant `€`), `allocate` au plus grand reste avec signe réappliqué. 100 tests au total, couverture 100 % lignes, branches, fonctions, instructions.
- Check `mutation` : `stryker run --mutate <fichiers du diff>`, score = (Killed + Timeout) / (Killed + Timeout + Survived + NoCoverage), `failed` sous 80 avec une issue par mutant survivant (`survived:<mutator>`, fichier, ligne), `passed` avec la note « aucun fichier mutable modifié » quand le diff est vide. Preuve de bout en bout : avec un test `allocate` volontairement affaibli (branche jetable), le check échoue (score 9,09 %, 40 survivants listés) ; avec les vrais tests il passe à 98,94 %.
- `quality/run.test.ts` (vrais processus, aucun mock) : verdict (profil `full` en CI avec un bloquant `skipped`, profil `push` avec `ci-only`, autre raison, advisory), écriture atomique, `tool-version-mismatch`, code 2 sur `--only` inconnu, check `mutation`.

## Task Commits

1. **Tâche 1 : tests unitaires dans la gate** - `f1b401b` (feat)
2. **Tâche 2 : canari `src/shared/money`, RED** - `555e1a5` (test)
3. **Tâche 2 : canari `src/shared/money`, GREEN** - `5f7bd9c` (feat)
4. **Tâche 2 : REFACTOR de `allocate`** - `15fa7d5` (refactor)
5. **Tâche 3 : mutation Stryker limitée au diff** - `714f51f` (feat)
6. **Durcissement de la base git du check `mutation`** - `66f47ea` (fix)

## TDD (tâche 2)

- **RED :** `money.test.ts`, `allocate.test.ts`, `allocate.properties.test.ts`, `money.properties.test.ts` plus deux squelettes aux signatures finales (`money.ts`, `allocate.ts`) au comportement volontairement faux (`unsupported-currency`, `invalid-amount`, `invalid-weights`, chaîne vide). Test cible : `parseAmount > lit « 84 » comme 8400n centimes`. Run de `money.test.ts` : 35 échecs sur 62 (les 27 réussites sont les refus que le squelette renvoie par construction). Le reporter `tap-flat` a été refusé par le classifieur (`invalid_record`, « Non-TAP data » : les valeurs `actual`/`expected` multilignes cassent le YAML) ; relance avec le reporter `junit` de Vitest, `gsd-tools check tdd-red-evidence` rend `RED_EVIDENCE_OK` (`target_test_failed`). Évaluation sémantique : le test cible s'exécute et échoue sur son assertion `toEqual` (`{ ok: false, error: 'invalid-amount' }` reçu pour `{ ok: true, value: 8400n }` attendu), aucun échec d'import, de syntaxe ou de fixture. Le fichier de preuve vit sous `.gsd/tdd-evidence/01-03/` (ignoré).
- **GREEN :** `money.ts` et `allocate.ts` réels, 100 tests verts, couverture 100 %.
- **REFACTOR :** rang par comparaison de restes dans `allocate` (comportement inchangé, tests verts, un mutant équivalent de moins).

## Mesure de stabilité Stryker (Q2, A1, bug #6335)

Canari muté : `src/shared/money/money.ts` et `allocate.ts` (94 mutants comptés), 10 exécutions avec `disableBail: true` et 10 sans, alternées, sur la même machine. Chaque exécution : code de sortie 0, 93 tués, 1 survivant.

| Exécution | avec `disableBail` : score / survivants | sans `disableBail` : score / survivants |
|---|---|---|
| 1 | 98,94 % / 1 | 98,94 % / 1 |
| 2 | 98,94 % / 1 | 98,94 % / 1 |
| 3 | 98,94 % / 1 | 98,94 % / 1 |
| 4 | 98,94 % / 1 | 98,94 % / 1 |
| 5 | 98,94 % / 1 | 98,94 % / 1 |
| 6 | 98,94 % / 1 | 98,94 % / 1 |
| 7 | 98,94 % / 1 | 98,94 % / 1 |
| 8 | 98,94 % / 1 | 98,94 % / 1 |
| 9 | 98,94 % / 1 | 98,94 % / 1 |
| 10 | 98,94 % / 1 | 98,94 % / 1 |

Le survivant est toujours le même : `allocate.ts` `EqualityOperator` sur `total.amountMinor < 0n` remplacé par `<= 0n`. Il est équivalent (pour un total nul, la valeur absolue et le signe réappliqué donnent 0 dans les deux cas) ; il ne peut pas être tué et pèse 1 point de score sur 94.

**Mitigation retenue :** `disableBail: true` reste dans `stryker.config.mjs`, conformément à la règle du plan (10 exécutions avec `disableBail` stables). Aucune relance des survivants n'est ajoutée. Réserve honnête : le bug #6335 ne s'est reproduit dans aucune des 20 exécutions, y compris sans `disableBail` ; l'efficacité de `disableBail` contre ce bug n'est donc pas démontrée par cette mesure (A1 reste non prouvée), et le canari (4 tests par mutant en moyenne) est petit. Le seuil `thresholds.mutation.break` reste à 80 : un faux survivant ne peut biaiser le score que vers le bas. Si un faux survivant apparaît sur un module plus gros, la relance limitée aux survivants (`--mutate fichier:Ldébut-Lfin`) est le repli prévu.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `eslint.config.mjs` ne reconnaît pas `test.prop` comme un bloc de test**
- **Found during:** Tâche 2 (GREEN)
- **Issue :** les huit `expect` des tests de propriétés étaient signalés par `vitest/no-standalone-expect`.
- **Fix :** option `additionalTestBlockFunctions: ['test.prop']` sur cette règle, sans désactivation de règle ni directive.
- **Files modified :** `eslint.config.mjs` (absent de `files_modified`)
- **Commit :** `5f7bd9c`

**2. [Rule 1 - Bug] `%j` ne sérialise pas un `bigint` dans les titres d'`it.each`**
- **Found during:** Tâche 2 (GREEN)
- **Issue :** `allocate.test.ts` échouait à la collecte (`Do not know how to serialize a BigInt`). Le RED a été mesuré sur `money.test.ts` ; ce défaut de `allocate.test.ts` n'est apparu qu'au premier run complet.
- **Fix :** `%s` à la place de `%j`.
- **Files modified :** `src/shared/money/allocate.test.ts`
- **Commit :** `5f7bd9c`

**3. [Rule 1 - Bug] `formatMoney` : chaîne décimale vers `Intl.NumberFormat` impossible à typer sans assertion**
- **Found during:** Tâche 2 (GREEN)
- **Issue :** le plan prescrit de passer la chaîne décimale exacte à `Intl.NumberFormat('fr-FR', { style: 'currency' })`. `format()` n'accepte en type qu'un `number`, un `bigint` ou un `StringNumericLiteral` ; une chaîne construite est refusée (TS2769, vérifié avec et sans `as const`) et `as` est interdit.
- **Fix :** les unités (`bigint`) passent par `Intl.NumberFormat('fr-FR')` pour le groupement (U+202F), les centimes sont formés à la main, U+00A0 et `€` sont ajoutés. La sortie est identique à celle attendue (« 84,00 € », « 1 234 567,89 € », « -12,50 € », « 0,05 € »).
- **Files modified :** `src/shared/money/money.ts`
- **Commit :** `5f7bd9c`

**4. [Rule 2 - Missing critical] Base git du check `mutation` pouvant être prise pour une option**
- **Found during:** Tâche 3 (relecture avant SUMMARY)
- **Issue :** `ctx.base` vient de `--base` ou de `GITHUB_BASE_REF` et est passé à `git diff` ; une valeur commençant par `-` serait lue comme une option.
- **Fix :** refus (`invalid-base`) avant tout appel git et séparateur `--` ; deux tests ajoutés à `quality/run.test.ts`.
- **Files modified :** `quality/checks/mutation.ts`, `quality/run.test.ts`
- **Commit :** `66f47ea`

**Total deviations :** 4 auto-corrigées. **Impact :** deux fichiers supplémentaires touchés hors de `files_modified` (`eslint.config.mjs`, aucun nouveau fichier) ; aucun changement de périmètre.

### Adaptations sans écart de contenu

- Test `verifyMiseToolVersion` : un pin faux sur un outil réel ferait installer cet outil par `mise exec`. La fixture épingle `node = "0.0.1"` et le test pose `MISE_DISABLE_TOOLS=node` et `MISE_TRUSTED_CONFIG_PATHS` (variables restaurées après le test) : mise n'installe rien, `node` du PATH répond, la version trouvée est comparée au pin faux (`ok: false`). Le cas `tool-version-mismatch` du check lui-même est testé sur le check `lint` avec une fixture npm.
- Le RED de la tâche 2 utilise des squelettes de modules (signatures finales, comportement faux) dans le commit `test(...)`, pour que le test cible échoue sur une assertion et non sur un import manquant (sinon `INVALID_RED`).
- `formatMoney` : constantes `NBSP`/`NNBSP` écrites par échappement Unicode (U+00A0, U+202F) dans les tests et le module, pour éviter des caractères invisibles dans le source.

## Auth Gates

Aucune.

## Known Stubs

Aucun. Les squelettes du RED ont été remplacés au GREEN.

## Threat Flags

Aucun nouveau point de surface hors du `threat_model`. Mitigations appliquées : T-01-10 (mutation bloquante à 80 sur le diff, source des tests modifiés inclus ; couverture 100 % sur `layout.pure` ; règles `@vitest/eslint-plugin`), T-01-11 (mesure de 20 exécutions, seuil fixé dans `quality/thresholds.json`, jamais abaissé), T-01-12 (parseur `bigint` maison, aucun `Number(`, `parseFloat` ni `Math.round` dans le module, propriétés fast-check d'aller-retour), T-01-58 (périmètre `all` par défaut sans dossier exclu, `pure` posé uniquement par le check `unit` dans l'environnement de son fils, valeur inconnue refusée), T-01-SC (uniquement les versions de la table approuvée au plan 01-02, `pnpm install --frozen-lockfile` passe).

## Notes pour les plans suivants

- **Plan 01-05 (intégration, check `coverage`) :** `vitest.config.ts` n'a que le projet `unit`. Le runner Vitest de Stryker n'a pas d'option de projet : il joue tous les projets de la config. Quand le projet `integration` sera ajouté, il faudra le tenir hors des runs de mutation (config dédiée ou filtre), sans quoi chaque mutant démarrerait PostgreSQL.
- **Plan 01-12 (auto-tests) :** le cas `tests-weak-assertion` peut affaiblir `allocate.test.ts` et `allocate.properties.test.ts` ; le check `mutation` relie bien chaque test modifié à `allocate.ts` (vérifié sur une branche jetable : score 9,09 %, échec).
- **Plans `knip` et `dependency-cruiser` :** `money`, `parseAmount`, `formatMoney`, `allocate` ne sont importés que par leurs tests jusqu'à la phase 3 (D-09). La configuration knip devra traiter `src/shared/money` comme un point d'entrée prévu, sans `ignore` fourre-tout.
- **Variables d'environnement introduites :** `GATE_COVERAGE_SCOPE` (`all` | `pure`), `FAST_CHECK_NUM_RUNS` (défaut 100), `GATE_MUTATION_SCOPE` (`all` au nightly).
- **Mutant équivalent connu :** `allocate.ts` `total.amountMinor < 0n` en `<= 0n` ; il fixe le score du canari à 98,94 % et n'a pas besoin de directive.
- **Outils d'écriture :** l'outil d'écriture de fichiers de l'agent convertit les échappements Unicode (U+00A0, U+202F) écrits dans le contenu en caractères littéraux ; les constantes concernées ont été réécrites par `sed`.

## Self-Check: PASSED

- Fichiers présents : `vitest.config.ts`, `test/setup/fast-check.ts`, `stryker.config.mjs`, `quality/checks/unit.ts`, `quality/checks/mutation.ts`, `quality/run.test.ts`, `src/shared/money/{money,allocate}.ts` et leurs quatre fichiers de tests.
- Commits dans l'historique : `f1b401b`, `555e1a5`, `5f7bd9c`, `15fa7d5`, `714f51f`, `66f47ea`.
- `mise exec -- pnpm quality` : verdict `pass`, six checks `passed` (`format`, `lint`, `mutation`, `typecheck`, `unit`, `workflow-lint`).
- Couverture de `src/shared/money/*` : 100 % lignes et branches (`reports/coverage/coverage-summary.json`).
