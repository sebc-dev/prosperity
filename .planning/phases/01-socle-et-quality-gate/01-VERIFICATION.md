---
phase: 01-socle-et-quality-gate
verified: 2026-11-25T16:00:00Z
status: human_needed
score: 5/5 must-haves verified
covered_files:
  - .claude/settings.json
  - .dependency-cruiser.cjs
  - .github/CODEOWNERS
  - .github/workflows/nightly.yml
  - .github/workflows/quality-verdict.yml
  - .github/workflows/quality.yml
  - .planning/phases/01-socle-et-quality-gate/01-01-PLAN.md
  - .planning/phases/01-socle-et-quality-gate/01-01-SUMMARY.md
  - .planning/phases/01-socle-et-quality-gate/01-02-PLAN.md
  - .planning/phases/01-socle-et-quality-gate/01-02-SUMMARY.md
  - .planning/phases/01-socle-et-quality-gate/01-03-PLAN.md
  - .planning/phases/01-socle-et-quality-gate/01-03-SUMMARY.md
  - .planning/phases/01-socle-et-quality-gate/01-04-PLAN.md
  - .planning/phases/01-socle-et-quality-gate/01-04-SUMMARY.md
  - .planning/phases/01-socle-et-quality-gate/01-05-PLAN.md
  - .planning/phases/01-socle-et-quality-gate/01-05-SUMMARY.md
  - .planning/phases/01-socle-et-quality-gate/01-06-PLAN.md
  - .planning/phases/01-socle-et-quality-gate/01-06-SUMMARY.md
  - .planning/phases/01-socle-et-quality-gate/01-07-PLAN.md
  - .planning/phases/01-socle-et-quality-gate/01-07-SUMMARY.md
  - .planning/phases/01-socle-et-quality-gate/01-08-PLAN.md
  - .planning/phases/01-socle-et-quality-gate/01-08-SUMMARY.md
  - .planning/phases/01-socle-et-quality-gate/01-09-PLAN.md
  - .planning/phases/01-socle-et-quality-gate/01-09-SUMMARY.md
  - .planning/phases/01-socle-et-quality-gate/01-10-PLAN.md
  - .planning/phases/01-socle-et-quality-gate/01-10-SUMMARY.md
  - .planning/phases/01-socle-et-quality-gate/01-11-PLAN.md
  - .planning/phases/01-socle-et-quality-gate/01-11-SUMMARY.md
  - .planning/phases/01-socle-et-quality-gate/01-12-PLAN.md
  - .planning/phases/01-socle-et-quality-gate/01-12-SUMMARY.md
  - .planning/phases/01-socle-et-quality-gate/01-13-PLAN.md
  - .planning/phases/01-socle-et-quality-gate/01-13-SUMMARY.md
  - .planning/phases/01-socle-et-quality-gate/01-14-PLAN.md
  - .planning/phases/01-socle-et-quality-gate/01-14-SUMMARY.md
  - .planning/phases/01-socle-et-quality-gate/01-15-PLAN.md
  - .planning/phases/01-socle-et-quality-gate/01-15-SUMMARY.md
  - eslint.config.mjs
  - quality/approvals.ts
  - quality/integrity.ts
  - quality/protected-paths.json
  - quality/protected-paths.ts
  - quality/run.ts
  - quality/thresholds.json
  - quality/verdict.ts
  - semgrep/prosperity.yml
  - src/shared/money/allocate.ts
  - stryker.config.mjs
  - vitest.config.ts
covered_digest: "v4:sha256:08363995298480762953f8f06f68ff8f2a295de97be5374e8ca987ab191385ba"
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Dans une session agent neuve, demander l'outil Write (pas Edit) sur un chemin protégé, par exemple `quality/thresholds.json` ou `.github/workflows/quality.yml`."
    expected: "Refus par les permissions (« denied by your permission settings »). Le dépôt n'a que 66 règles `Edit(...)` et aucune règle `Write(...)` ; la doctrine du plan veut qu'`Edit` couvre Write et NotebookEdit."
    why_human: "Le refus (b) de Write est déclaré par l'humain sans message exact (01-14-SUMMARY, « Points ouverts »). L'agent vérificateur n'a pas le droit d'écrire sur un chemin protégé pour le constater."
  - test: "Relire dans GitHub (Settings) l'environnement `gate-verdict` (restreint à `main`, secret `GATE_APP_PRIVATE_KEY` et variable `GATE_APP_ID` au niveau de l'environnement seulement), l'auto-fusion désactivée et les durcissements Actions."
    expected: "Conforme à la déclaration du SUMMARY 01-14 (V3) : application `prosperity-gate` (ID 5887661, `statuses: write` seule), clé non lisible depuis une PR."
    why_human: "Le verrou interdit à l'agent de lire ces réglages (`gh api …/environments`, `…/actions/permissions`, `gh variable`, `gh secret`). Les effets observables (statut `quality` publié par `prosperity-gate[bot]`, fusion bloquée sur #306) sont, eux, vérifiés ci-dessous."
  - test: "Constater que le timer SonarQube utilisateur de kfzcore est actif (`systemctl --user list-timers`) et qu'une analyse nightly a été traitée."
    expected: "Timer `prosperity-sonar` actif ; dernière analyse `SUCCESS`."
    why_human: "Le timer vit hors du dépôt, sur le poste de l'humain. Advisory (D-16) : aucun effet sur le verdict ni sur le but de la phase ; à accepter ou ignorer sans bloquer."
---

# Phase 1 : Socle et quality gate, rapport de vérification

**Objectif de phase :** As a développeur du projet, I want to voir chaque PR jugée par une seule gate déterministe (`pnpm quality`), identique en local et en CI, qui bloque typage laxiste, violations d'architecture, failles de sécurité, tests faibles et contournements, so that aucune ligne de domaine écrite par un agent n'entre dans le dépôt sans avoir passé cette gate.
**Vérifié le :** 2026-11-25 sur `sebc-dev/jiaolong` @ `22635a2` (contient `origin/main`, PR #300, #301, #307)
**Statut :** human_needed (aucun écart bloquant ; trois constats de réglages hors dépôt que l'agent ne peut pas relire)
**Re-vérification :** Non, vérification initiale

## Atteinte de l'objectif

### Vérités observables (critères de succès de la feuille de route)

| # | Vérité | Statut | Preuve |
|---|--------|--------|--------|
| 1 | `pnpm quality` rend le même verdict en pré-push et en CI, écrit `reports/gate.json`, et la protection de branche n'exige que `quality` | ✓ VERIFIED | `package.json` : `"quality": "node quality/run.ts"` ; `lefthook.yml` pré-push = `pnpm quality --profile push`, `quality.yml` = `pnpm quality` (profil `full`) ; mêmes checks découverts dans `quality/checks/`, les checks lourds déclarés `skipped: ci-only` dans `gate.json` (lecture D-12 : même verdict pour chaque check joué, mêmes versions via `mise.toml`). Rejoué : `mise exec -- pnpm quality` sort 0, `verdict : pass`, `reports/gate.json` (profil `full`, 22 checks). `gh ruleset view 17645569` : actif, « You can bypass: never », unique `required_status_checks` = `context: quality`, `integration_id: 5887661` (application `prosperity-gate`), `strict` vrai |
| 2 | Des PR de démonstration, une violation chacune, sont toutes rejetées (`as`, `any`, complexité, outil MCP important `adapters/db`, cycle, export mort, bloc dupliqué, secret, SQL concaténé, handler sans `Principal`, action CI non épinglée) | ✓ VERIFIED | Les 11 violations ont un cas de l'auto-test (`quality/selftest/cases/` : `lint-type-assertion`, `lint-explicit-any`, `lint-cognitive-complexity`, `arch-mcp-imports-db`, `arch-cycle`, `deadcode-unused-export`, `dup-new-clone`, `sec-generated-secret`, `sast-sql-concatenation`, `sast-handler-without-principal`, `wf-unpinned-action`), 27 cas au total, joués sur worktrees jetables par le check `selftest` (nightly forcé : run 45621020711 `success` sur `main`). Rejoué par le vérificateur : `node quality/selftest/run.ts --case tests-weak-assertion,tests-coverage-drop,wf-unpinned-action,arch-mcp-imports-db` : 4 cas `passed / detected`, exit 0. Sur de vraies PR : #302 (check bloquant), #305, #306 `quality` en échec ; #306 `gate` SUCCESS mais `quality` FAILURE (jugement hors PR). Lecture : les violations sont jouées en cas d'auto-test plutôt qu'en 11 PR GitHub séparées ; équivalent fonctionnel, rejeté par la même gate, voir note ci-dessous |
| 3 | Module canari : un test faible échoue par le score Stryker et par la couverture du domaine pur < 100 % ; test d'intégration sur PostgreSQL 18 réel (Testcontainers), ordre aléatoire, seed loguée | ✓ VERIFIED | Canari `src/shared/money/{allocate,money}.ts` + tests d'exemples et de propriétés (fast-check). Cas `tests-weak-assertion` (`mutation` / `mutation-score-below-break`) et `tests-coverage-drop` (`unit` / `coverage-threshold`) détectés (rejoués). `vitest.config.ts` : `sequence.shuffle {files, tests}`, seuils purs 100 % lus dans `quality/thresholds.json`. `test/global-setup.ts` : `postgres:18.7-trixie@sha256:eb63…` par `PostgreSqlContainer`. Run local du check `integration` : `passed`, note `seed 1795619541853 (rejouable : --sequence.seed=…)` ; `unit` et `coverage` loguent aussi leur seed. Mutation : `stryker.config.mjs` `thresholds.break` = 80 |
| 4 | Sans label humain (posé par `sebc-dev` après le dernier push, D-15), la CI bloque baisse de seuil, retrait d'assertion, échappatoire, chemin protégé ; les permissions de l'agent refusent l'édition de ces chemins | ✓ VERIFIED (réserve Write, voir Vérification humaine) | Cas d'auto-test `integrity-threshold-lowered`, `integrity-assertion-removed`, `integrity-protected-path-changed`, `escape-hatch-added`, `escape-hatch-coverage-ignore`. PR réelles : #303 `human-label` (rouge sans label, vert avec, rouge après push), #304 `bot-label` (label posé par `github-actions[bot]` rejeté, `approval-actor-not-allowed`), #306 `workflow-rewrite` (`gate` vert, `quality` rouge `integrity-failed`). PR #307 (modifie `quality/protected-paths.ts`) fusionnée seulement avec `gate-change-approved` et `quality` SUCCESS. `.claude/settings.json` : 66 règles `Edit(...)`, `Bash(git commit*--no-verify*)`, `Bash(git push*--force*)`, hook `bash-guard.ts` ; `.github/CODEOWNERS` 74 lignes ; `quality/protected-paths.json` 66 globs |
| 5 | Une dépendance ajoutée sans `deps-approved`, ou plus récente que l'âge minimal, fait échouer l'installation ou la CI | ✓ VERIFIED | `pnpm-workspace.yaml` : `minimumReleaseAge: 10080`, `minimumReleaseAgeStrict`, `blockExoticSubdeps`, `trustPolicy: no-downgrade`, `strictDepBuilds`, `allowBuilds` explicite ; `pnpm install --frozen-lockfile` rejoué : exit 0, « Lockfile passes supply-chain policies ». Check `deps` (`quality/deps-guard.ts`, 30 jours) et cas `deps-added-unapproved`, `deps-policy-weakened`. PR #305 : `dependency-added ms (2.1.3) exige le label deps-approved`, `quality` rouge. Local : `vitest@5.1.2` refusé par `minimumReleaseAge` (déclaré au SUMMARY 01-14) |

**Score :** 5/5 vérités vérifiées (0 présentes mais non vérifiées en comportement)

Note sur le critère 2 : la feuille de route parle de « PR de démonstration ». La phase a livré l'équivalent sous deux formes : (a) l'auto-test (`selftest`, 27 cas, patchs appliqués dans des worktrees jetables, détection exigée par règle précise, un échec d'infrastructure ne comptant jamais comme détection), joué à chaque diff qui touche un chemin protégé et au nightly ; (b) cinq PR GitHub réelles pour les scénarios de jugement (D-07b : #302 à #306). Le résultat est le même : chaque violation listée est rejetée par la gate. Je ne demande pas 11 PR distinctes.

### Gate rejouée en local

`mise exec -- pnpm install --frozen-lockfile` : exit 0. `mise exec -- pnpm quality` : exit 0, `verdict : pass`.

| Check | Statut | Remarque |
|---|---|---|
| arch, container, coverage, cve, deadcode, duplication, escape-hatches, format, integration, lint, mutation, sast, secrets, selftest, typecheck, unit, workflow-audit, workflow-lint | passed | `mutation` : « aucun fichier mutable modifié » ; `selftest` : « non déclenché (D-08) » ; `container` : « non applicable, aucun Containerfile » ; `workflow-audit` : audits hors ligne (GH_TOKEN absent) |
| approvals, deps, integrity | skipped (ci-only) | jugés en CI sur le diff de PR, vérifiés par les runs de PR |
| lint-security | failed, **advisory** | 205 issues `eslint-plugin-security`, par conception sans effet sur le verdict (CLAUDE.md §10.2 : advisory) |

### Artefacts requis

| Artefact | Rôle | Statut | Détail |
|---|---|---|---|
| `quality/run.ts`, `quality/gate-report.ts`, `quality/check-kit.ts` | Runner unique, `reports/gate.json` | ✓ VERIFIED | Substantiel, relié à `package.json` `quality`, lefthook et `quality.yml` ; échec fermé quand aucun check n'est joué (corrigé par #307) |
| `quality/checks/*.ts` (22 checks) | typage, lint, arch, deadcode, duplication, secrets, sast, cve, workflow, unit, coverage, mutation, integration, escape-hatches, integrity, approvals, deps, selftest, container, format, lint-security | ✓ VERIFIED | Tous découverts et exécutés par le run local |
| `quality/protected-paths.{ts,json}` | Liste unique des 66 chemins protégés | ✓ VERIFIED | Correction CR-01 vérifiée empiriquement : `isProtected('quality/checks/.evil.ts')`, `.github/workflows/.evil.yml`, `deploy/.x.service`, `mise/.x`, `quality/.a/b.ts` renvoient `true` ; `src/foo.ts` `false`. `discoverChecks` refuse tout fichier caché de `quality/checks/`. Tests dédiés `quality/protected-paths.test.ts` |
| `quality/integrity*.ts`, `approvals.ts`, `approval-evidence.ts`, `deps-guard.ts`, `verdict*.ts` | Juges d'intégrité, approbation par label D-15, juge hors PR | ✓ VERIFIED | Rejoués depuis la copie de base `gate-base` ; verdict publié par `prosperity-gate[bot]` (voir PR #306, #307) |
| `.github/workflows/{quality,quality-verdict,nightly}.yml` | CI, juge hors PR, nightly | ✓ VERIFIED | Actions épinglées par SHA ; `permissions: {}` par défaut ; `pull_request` seulement (jamais `pull_request_target`) |
| `.dependency-cruiser.cjs`, `knip.json`, `.jscpd.json`, `.gitleaks.toml`, `semgrep/prosperity.yml`, `eslint.config.mjs`, `tsconfig.json`, `biome.json` | Outils de la gate et leurs règles | ✓ VERIFIED | `tsconfig` : `strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `erasableSyntaxOnly`… ; ESLint : `strictTypeChecked`, `consistent-type-assertions: never`, `no-explicit-any`, `no-non-null-assertion`, `ban-ts-comment`, `sonarjs/cognitive-complexity` 10, `reportUnusedDisableDirectives: error` ; depcruise : 7 règles (`no-circular`, `domain-is-pure`, `mcp-tools-no-db`, `cross-module-public-only`, `db-access-restricted`, `no-dev-deps-in-src`, `not-to-unresolvable`) ; Semgrep : handler sans `Principal`, SQL concaténé, `Math.random`, comparaison non constante, `registerTool` direct |
| `src/shared/money/*`, `test/*.int.test.ts`, `db/migrations/0001_foundation.sql`, `src/db/*` | Canari, tests d'intégration et socle base | ✓ VERIFIED | Tests d'exemples et de propriétés ; test méta RLS ; Testcontainers sur PostgreSQL 18.7 |
| `.claude/settings.json`, `.github/CODEOWNERS`, `quality/agent-guard/*`, `lefthook.yml` | Verrou de l'agent | ✓ VERIFIED (réserve Write) | 23 tests `quality/lock.test.ts` |
| `docs/quality-gate.md`, `deploy/sonar/*`, `quality/sonar/*` | Documentation et analyse advisory D-16 | ✓ VERIFIED | Sonar : advisory, hors verdict |

### Liens clés

| De | Vers | Via | Statut |
|---|---|---|---|
| `package.json` `quality` | `quality/run.ts` | `node quality/run.ts` | ✓ WIRED |
| `lefthook.yml` pré-push | `pnpm quality --profile push` | `mise exec` | ✓ WIRED |
| `quality.yml` job `gate` | `pnpm quality` + juges de confiance depuis `gate-base` | `--base-dir "$RUNNER_TEMP/gate-base"` | ✓ WIRED |
| `quality.yml` | `quality-verdict.yml` | `workflow_run`, jugement rejoué depuis `main` | ✓ WIRED (runs 45641751593, 45642106285 `success`) |
| `quality-verdict` | statut requis `quality` du ruleset | application `prosperity-gate`, `integration_id` 5887661 | ✓ WIRED (#307 : `quality` SUCCESS ; #306 : FAILURE) |
| `quality/protected-paths.json` | `integrity`, `selftest`, pré-commit, `write-rules.ts`, `settings.json`, CODEOWNERS | `isProtected` / 66 règles / 66 lignes | ✓ WIRED |
| `quality/thresholds.json`, `layout.json` | `vitest.config.ts`, `stryker.config.mjs`, `eslint.config.mjs`, `.dependency-cruiser.cjs` | import JSON, aucune valeur recopiée | ✓ WIRED |

### Trace de données (niveau 4)

Non applicable : la phase ne produit aucune donnée rendue à un utilisateur. Le canari monétaire est une bibliothèque pure, couverte par exemples, propriétés et mutation.

### Contrôles comportementaux

| Comportement | Commande | Résultat | Statut |
|---|---|---|---|
| Gate complète | `mise exec -- pnpm quality` | `verdict : pass`, exit 0 | ✓ PASS |
| Installation sous politique supply-chain | `mise exec -- pnpm install --frozen-lockfile` | exit 0 | ✓ PASS |
| Détection : test faible, couverture, action non épinglée, outil MCP important la base | `node quality/selftest/run.ts --case …` (4 cas) | 4 `detected`, exit 0 | ✓ PASS |
| Correction CR-01 | `isProtected` sur 5 chemins cachés | tous `true` | ✓ PASS |
| Ruleset et PR réelles | `gh ruleset view 17645569`, `gh pr view 300,302-307` | unique check `quality` ; #300 et #307 `MERGED`, #302 à #306 `CLOSED` | ✓ PASS |

### Sondes (probes)

Aucune sonde `probe-*.sh` déclarée ni présente (phase de gate, pas de migration). Étape ignorée.

### Couverture des exigences

Identifiants déclarés dans les `requirements:` des 15 plans : QUAL-01 (01-01, 03, 13, 14, 15), QUAL-02 (02, 10, 11), QUAL-03 (09, 11), QUAL-04 (04, 10, 12), QUAL-05 (03, 05, 12, 13), QUAL-06 (06, 07, 10, 12, 14), QUAL-07 (06, 07, 08, 13, 14, 15), QUAL-08 (05, 12), QUAL-09 (02, 07, 08, 12, 14). Les 9 identifiants de la phase sont tous revendiqués, aucun orphelin : `REQUIREMENTS.md` ne mappe que QUAL-01 à QUAL-09 à la phase 1.

| Exigence | Plans | Description | Statut | Preuve |
|---|---|---|---|---|
| QUAL-01 | 01, 03, 13, 14, 15 | `pnpm quality` unique, identique pré-push et CI, CI seul juge, un seul check requis | ✓ SATISFIED | Vérité 1 ; ruleset à un seul check |
| QUAL-02 | 02, 10, 11 | typage strict, lint type-aware sans avertissement, assertions interdites, complexité plafonnée | ✓ SATISFIED | `tsconfig.json`, `eslint.config.mjs`, `--max-warnings 0` (thresholds), cas `lint-*`, `types-unchecked-index` détectés |
| QUAL-03 | 09, 11 | dependency-cruiser, knip, jscpd | ✓ SATISFIED | `.dependency-cruiser.cjs` 7 règles ; checks `arch`, `deadcode`, `duplication` verts ; cas `arch-*`, `deadcode-unused-export`, `dup-new-clone` |
| QUAL-04 | 04, 10, 12 | gitleaks, règles Semgrep du projet, CVE high/critical, workflows non épinglés | ✓ SATISFIED | checks `secrets`, `sast`, `cve`, `workflow-audit`, `workflow-lint` ; cas `sec-generated-secret`, `sast-*`, `cve-high-severity`, `wf-unpinned-action`. Réserve : un avis OSV sans score CVSS ne bloque pas (IN-04, advisory) |
| QUAL-05 | 03, 05, 12, 13 | fast-check, Stryker bloquant, couverture 100 % pur, plancher global à cliquet | ✓ SATISFIED | tests `*.properties.test.ts`, `stryker.config.mjs` `break` 80, seuils 100/85/80 ; cliquet porté par le juge d'intégrité (un seuil ne baisse pas sans label) |
| QUAL-06 | 06, 07, 10, 12, 14 | compteur d'échappatoires à cliquet, job d'intégrité | ✓ SATISFIED | `quality/baseline.json` (22 motifs à 0), check `escape-hatches`, `integrity` ; PR #303, #304, #306 |
| QUAL-07 | 06, 07, 08, 13, 14, 15 | chemins de gate, CI, déploiement protégés (CODEOWNERS, permissions agent, intégrité) | ✓ SATISFIED (réserve Write) | 66 chemins, 66 règles `Edit`, 74 lignes CODEOWNERS, hook Bash, pré-commit, CR-01 corrigé (#307) |
| QUAL-08 | 05, 12 | tests d'intégration sur PostgreSQL 18 réel (Testcontainers), sans mock de repository, ordre aléatoire | ✓ SATISFIED | `test/global-setup.ts` (`postgres:18.7-trixie@sha256`), `sequence.shuffle`, seed loguée ; `vi.mock(` plafonné à 0 par le cliquet |
| QUAL-09 | 02, 07, 08, 12, 14 | nouvelle dépendance : approbation humaine et âge minimal | ✓ SATISFIED | `pnpm-workspace.yaml`, `deps-guard`, label `deps-approved` vérifié (D-15) ; PR #305 |

Les cases de `REQUIREMENTS.md` (« Pending ») sont tenues par l'orchestrateur, hors du périmètre de ce rapport.

### Anti-patterns trouvés

| Fichier | Constat | Gravité | Impact |
|---|---|---|---|
| (périmètre de phase) | Aucun `TBD`, `FIXME` ni `XXX` dans `quality/`, `src/`, `test/`, `db/`, `semgrep/`, `deploy/`, `.github/` | ℹ️ Info | Aucun marqueur de dette non référencé |
| `quality/approvals.ts:62-78` (WR-01) | Ancre « dernier push » = plus ancien run du SHA ; un fast-forward vers un SHA déjà vu garde une ancre ancienne. Exige un force-push de l'auteur (refusé par la garde agent) ; le job `reset-approval` retire déjà les labels | ⚠️ Warning (consigné, non corrigé) | Fenêtre étroite d'approbation périmée ; non bloquant |
| `quality/tools.ts:84-109` (WR-02) | Délai de `runTool` : un petit-enfant qui garde les tubes peut empêcher la résolution | ⚠️ Warning (non corrigé) | Échoue fermé (timeout du job, 20 min), jamais un faux vert |
| `deploy/sonar/prosperity-sonar.service` (WR-05) | `EnvironmentFile` expose `SONAR_TOKEN` à `mise install` et aux scripts d'installation | ⚠️ Warning (non corrigé) | Hors CI, outil advisory (D-16) |
| `quality/checks/sast.ts:60-66` (WR-06) | Erreurs d'analyse Semgrep de niveau `warn` ignorées (à confirmer) | ⚠️ Warning (non corrigé) | Un fichier non analysable pourrait passer ; périmètre actuel : une poignée de fichiers `src/` |
| `quality/escape-hatches.ts`, `cve.ts`, `bash-guard.ts`, `quality.yml` (IN-01 à IN-07) | Périmètre du cliquet limité à `src/`, `test/`, racine ; avis sans CVSS ignorés ; enveloppes à options valuées ; `pnpm install` avant les étapes de confiance ; `parseAmount` tolère « 12 50 » | ℹ️ Info | Dette consignée, aucune ne contredit un critère de succès |
| `.claude/CLAUDE.md`, `01-VALIDATION.md` | CLAUDE.md écrit encore pnpm 12.21.0 (outillage en 12.18.0) ; `01-VALIDATION.md` reste `status: draft`, `nyquist_compliant: false` | ℹ️ Info | Documentation à aligner ; épinglage daté consigné |

WR-03, WR-04, WR-07 et CR-01 de la revue `01-REVIEW.md` sont corrigés par la PR #307 (commit `7d6aece`, vérifié dans l'arbre et par exécution). Les constats WR-01, WR-02, WR-05, WR-06 et les infos restent des suivis consultatifs.

### Écarts acceptés connus

- pnpm 12.18.0 au lieu de 12.21.0 (règle d'âge de 30 jours sur `@pnpm/exe.netbsd-x64`) ; à relever après le 2026-12-10.
- Surcharge pnpm temporaire `'minimatch@>=11': 10.2.6` dans `pnpm-workspace.yaml` ; à retirer **le 2026-11-26 (demain)**, par PR avec `deps-approved`.
- SonarQube nightly hébergé sur kfzcore (et non kfzserver), advisory (D-16) ; `lint-security` advisory (205 issues).

### Vérification humaine requise

#### 1. Refus de l'outil Write sur un chemin protégé

**Test :** dans une session agent neuve, tenter Write (pas Edit) sur `quality/thresholds.json`.
**Attendu :** refus par les permissions ; aucune règle `Write(...)` n'existe, seules 66 règles `Edit(...)`.
**Pourquoi humain :** refus déclaré sans message exact (01-14-SUMMARY). L'agent vérificateur ne peut pas écrire sur un chemin protégé pour le constater.

#### 2. Réglages GitHub hors portée de l'agent

**Test :** relire l'environnement `gate-verdict` (restreint à `main`, secret et variable au niveau de l'environnement), l'auto-fusion désactivée, les durcissements Actions.
**Attendu :** conforme à la déclaration du SUMMARY 01-14 (V3).
**Pourquoi humain :** lecture refusée à l'agent par le verrou. Les effets observables sont vérifiés (statut `quality` publié par `prosperity-gate[bot]`, fusion bloquée sur #306, ruleset à un seul check de source `prosperity-gate`).

#### 3. Timer SonarQube (advisory)

**Test :** `systemctl --user list-timers` sur kfzcore.
**Attendu :** timer actif, dernière analyse `SUCCESS`.
**Pourquoi humain :** vit hors du dépôt. Sans effet sur le verdict ni sur l'objectif de la phase.

### Résumé des écarts

Aucun écart bloquant. Les cinq critères de succès et les neuf exigences QUAL-01 à QUAL-09 sont atteints dans l'arbre : la gate unique tourne verte localement, son verdict de CI est rendu hors de portée de la PR par une application GitHub dont le statut `quality` est le seul check requis du ruleset, chaque classe de violation du critère 2 est détectée (auto-test de 27 cas et PR réelles #302 à #306), le canari est tenu par la mutation, la couverture pure à 100 % et un PostgreSQL 18 réel en ordre aléatoire avec seed loguée, et les chemins protégés ne se contournent plus par un fichier caché (CR-01 corrigé et prouvé). Le statut `human_needed` ne tient qu'aux trois réglages hors dépôt que le verrou interdit à l'agent de relire ; ils sont déjà attestés par l'humain et n'invalident aucune vérité vérifiée. Aucun marqueur de dette, aucun test ou seuil affaibli.

Recommandation : accepter les trois éléments humains (le premier se vérifie en une minute), lever la surcharge `minimatch` le 2026-11-26 et traiter WR-01, WR-02, WR-05, WR-06 en suivis avant ou pendant la phase 2.

---

_Vérifié le : 2026-11-25_
_Vérificateur : Claude (gsd-verifier)_
