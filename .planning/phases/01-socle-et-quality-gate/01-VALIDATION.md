---
phase: "1"
slug: "socle-et-quality-gate"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-11-21"
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Vitest 5.1.x (projets `unit` + `integration`), fast-check 4.10.x, StrykerJS 10.1.1 |
| **Config file** | `vitest.config.ts`, `stryker.config.mjs` (none — Wave 0 installs) |
| **Quick run command** | `pnpm quality --profile push` |
| **Full suite command** | `pnpm quality` (+ `pnpm quality --only selftest`) |
| **Estimated runtime** | ~60 seconds (profil push) ; CI complète ≤ 8-10 min |

---

## Sampling Rate

- **After every task commit:** Run `pnpm quality --profile push` (dès qu'il existe ; avant, la commande de vérification propre à la tâche)
- **After every plan wave:** Run `pnpm quality` + `pnpm quality --only selftest`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-T1 | 01-01 | 1 | QUAL-01 | T-01-01, T-01-03, T-01-04 | Gate de bout en bout ; aucun contexte d'événement dans `run:`, outils épinglés et vérifiés, installés en CI en mode verrouillé (`install_args: "--locked"`) | integration (tracer) | `mise exec -- pnpm quality` ; workflow invalide → code 1 ; `mise exec -- lefthook run pre-push` ; `grep -c 'install_args: "--locked"' .github/workflows/quality.yml` = 1 | ❌ W0 | ⬜ pending |
| 01-01-T2 | 01-01 | 1 | QUAL-01 | T-01-06 | Rattachement d'historique décidé par l'humain (one-way) | checkpoint:decision | manuel (réponse consignée) | n/a | ⬜ pending |
| 01-01-T3 | 01-01 | 1 | QUAL-01 | T-01-04 | PR brouillon de bootstrap, check `quality` vert sur runner hébergé | e2e CI | `gh pr checks <n> --json name,bucket` ; `git merge-base --is-ancestor origin/main HEAD` | n/a | ⬜ pending |
| 01-02-T1 | 01-02 | 2 | QUAL-09 | T-01-07, T-01-SC | Aucun paquet `[SUS]` installé sans validation humaine | checkpoint:human-verify | manuel (légitimité npm) | n/a | ⬜ pending |
| 01-02-T2 | 01-02 | 2 | QUAL-02, QUAL-09 | T-01-08 | Typage strict et format ; installation gelée sous `minimumReleaseAge` | unit + négatif | `pnpm install --frozen-lockfile && pnpm quality --only typecheck,format` ; accès indexé → `TS…` | ❌ W0 | ⬜ pending |
| 01-02-T3 | 01-02 | 2 | QUAL-02 | T-01-09 | Lint type-aware sans avertissement, `as`/`any`/`!` interdits | négatif | `mise exec -- pnpm quality` ; `as` → `consistent-type-assertions` | ❌ W0 | ⬜ pending |
| 01-03-T1 | 01-03 | 3 | QUAL-01, QUAL-05 | T-01-58 | Règles de verdict du runner ; ordre aléatoire avec seed ; périmètre de couverture `GATE_COVERAGE_SCOPE` (`all` par défaut, `pure` pour `unit`, valeur inconnue refusée), aucun dossier de `src/` exclu | unit + négatif | `pnpm vitest run --project unit quality/run.test.ts` ; sonde `src/zz-scope-probe.ts` présente en `all`, absente en `pure` | ❌ W0 | ⬜ pending |
| 01-03-T2 | 01-03 | 3 | QUAL-05 | T-01-12 | Canari `Money` exact, sans flottant, couverture 100 % (périmètre pur) | tdd + propriétés | `pnpm quality --only unit,lint,typecheck` + `reports/coverage/coverage-summary.json` à 100 % | ❌ W0 | ⬜ pending |
| 01-03-T3 | 01-03 | 3 | QUAL-05 | T-01-10, T-01-11 | Mutation bloquante à 80 sur le diff, stabilité #6335 mesurée | mutation | `pnpm quality --only mutation` ; fichiers Stryker ignorés | ❌ W0 | ⬜ pending |
| 01-04-T1 | 01-04 | 3 | QUAL-04 | T-01-16 | Statut des packs Semgrep décidé (Q4) | checkpoint:decision | manuel (réponse consignée) | n/a | ⬜ pending |
| 01-04-T2 | 01-04 | 3 | QUAL-04 | T-01-13, T-01-14 | Secrets refusés au pré-commit et en CI, workflows audités | négatif | `pnpm quality --only secrets,workflow-audit,container` ; `ghp_` indexé refusé par gitleaks | ❌ W0 | ⬜ pending |
| 01-04-T3 | 01-04 | 3 | QUAL-04 | T-01-15, T-01-16 | Règles SAST du projet testées, CVE ≥ 7 bloquantes, lint sécurité advisory | unit (semgrep --test) | `semgrep --test …` ; `pnpm quality --only sast,cve` ; `lint-security` advisory | ❌ W0 | ⬜ pending |
| 01-05-T1 | 01-05 | 4 | QUAL-08 | T-01-20, T-01-42 | Rôles séparés migrations / app, migration forward-only | statique | `pnpm quality --only typecheck,lint,format` ; imports `kysely/migration` | ❌ W0 | ⬜ pending |
| 01-05-T2 | 01-05 | 4 | QUAL-08 | T-01-17, T-01-19, T-01-42, T-01-59 | Migrations jouées sous `prosperity_migrator`, app sans DDL, PG 18.7 réel ; code de `src/db/` exercé dans les workers (base vide migrée, migration en échec nommée) | integration | `pnpm vitest run --project integration test/foundation.int.test.ts` | ❌ W0 | ⬜ pending |
| 01-05-T3 | 01-05 | 4 | QUAL-08, QUAL-05 | T-01-18, T-01-42, T-01-59 | Méta-tests RLS et rôles, check `integration` ; check `coverage` : run fusionné `unit` + `integration`, plancher global 85/80 sur tout `src/**` (`src/db/**` compris) | integration + négatif | `pnpm quality --only integration` ; `pnpm quality --only coverage` + `reports/coverage-all/coverage-summary.json` (src/db présent, total ≥ 85/80) ; fichier non testé sous `src/db/` → `coverage-threshold` ; `--profile push` → `ci-only` | ❌ W0 | ⬜ pending |
| 01-06-T1 | 01-06 | 4 | QUAL-06 | T-01-57 | Compteur d'échappatoires à cliquet (22 motifs, budget 0), directives d'exclusion de mutation, de couverture, Semgrep, gitleaks, jscpd et knip comprises, casse et espaces ignorés | tdd + négatif | `vitest … escape-hatches.test.ts` ; `@ts-expect-error` ajouté → code 1 ; `v8 ignore` + `Stryker disable` ajoutés → code 1 | ❌ W0 | ⬜ pending |
| 01-06-T2 | 01-06 | 4 | QUAL-06, QUAL-07 | T-01-21, T-01-22, T-01-56 | Intégrité jugée depuis la base (seuils, assertions, politique pnpm) ; liste protégée couvrant les fichiers de config, d'exclusion, de version d'outil et de réglage pnpm lus d'eux-mêmes par les outils | tdd + négatif | `vitest … integrity.test.ts` ; `mutation.break` 70 → `threshold-lowered` ; table `isProtected` d'exemples ; `.gitleaksignore` ajouté → `protected-path-changed` | ❌ W0 | ⬜ pending |
| 01-06-T3 | 01-06 | 4 | QUAL-07 | T-01-23, T-01-24 | Garde Bash : écritures protégées, signature et clés (D-14), labels (hygiène), fusion refusés | tdd + e2e processus | `vitest … bash-guard.test.ts` ; stdin PreToolUse `sed -i` et `gh pr merge` → deny | ❌ W0 | ⬜ pending |
| 01-07-T1 | 01-07 | 4 | QUAL-06, QUAL-07 | T-01-27 | Type de clé matérielle et politique de présence décidés par l'humain (D-14, costly) | checkpoint:decision | manuel (réponse consignée) | n/a | ⬜ pending |
| 01-07-T2 | 01-07 | 4 | QUAL-06, QUAL-09 | T-01-25, T-01-26, T-01-27, T-01-43, T-01-51, T-01-52 | Commit d'approbation signé en tête, vérifié contre `allowed_signers` de la base, drapeaux de présence contrôlés par la CI | tdd (vrais `git` et `ssh-keygen`) | `vitest … sshsig.test.ts approvals.test.ts` ; `pnpm quality --only approvals` → `ci-only` | ❌ W0 | ⬜ pending |
| 01-08-T1 | 01-08 | 4 | QUAL-09 | T-01-28, T-01-55 | Dépendance ajoutée sans `deps-approved` refusée ; registre et âge ; rapport d'approbations illisible → échec fermé | tdd + négatif | `vitest … deps-guard.test.ts` ; `ms` ajouté → `dependency-added` | ❌ W0 | ⬜ pending |
| 01-08-T2 | 01-08 | 4 | QUAL-07 | T-01-44, T-01-45, T-01-55 | Juge hors PR : statut `quality` publié par l'application, aucun code de PR exécuté, `quality/approvals.ts` lancé comme processus et jamais importé | tdd + statique | `vitest … verdict.test.ts` ; `pnpm quality --only workflow-lint,workflow-audit,typecheck,lint` | ❌ W0 | ⬜ pending |
| 01-09-T1 | 01-09 | 5 | QUAL-03 | T-01-29 | Frontières d'architecture (outil MCP → base interdit) | négatif | `pnpm quality --only arch` ; `src/mcp/tools` → `adapters/db` refusé | ❌ W0 | ⬜ pending |
| 01-09-T2 | 01-09 | 5 | QUAL-03 | T-01-30 | Code mort et duplication bloquants | négatif | `pnpm quality` ; export inutilisé → `exports` | ❌ W0 | ⬜ pending |
| 01-10-T1 | 01-10 | 6 | QUAL-02, QUAL-04, QUAL-06 | T-01-32, T-01-33 | Runner d'auto-test : règle attendue exigée, worktrees nettoyés ; `--case` = liste de globs séparés par des virgules, élément vide ou sans cas → code 2 | tdd + négatif | `vitest … selftest/run.test.ts` ; `--profile push --only selftest` → `ci-only` ; `--case 'zz-nomatch-*'` → code 2 | ❌ W0 | ⬜ pending |
| 01-10-T2 | 01-10 | 6 | QUAL-02, QUAL-04, QUAL-06 | T-01-31 | Trois cas témoins verts, aucun secret littéral | selftest | `node quality/selftest/run.ts --case <3 témoins>` | ❌ W0 | ⬜ pending |
| 01-11-T1 | 01-11 | 7 | QUAL-02 | T-01-46 | Cas `any`, `!`, complexité, `parseFloat`, directive inutile, index | selftest | `node quality/selftest/run.ts --case <6 cas> --report reports/selftest-01-11-qual02.json` | ❌ W0 | ⬜ pending |
| 01-11-T2 | 01-11 | 7 | QUAL-03 | T-01-46 | Cas outil MCP → base, cycle, export mort, bloc dupliqué | selftest | `node quality/selftest/run.ts --case 'arch-*,deadcode-*,dup-*' …` | ❌ W0 | ⬜ pending |
| 01-12-T1 | 01-12 | 7 | QUAL-04 | T-01-48 | Cas SQL concaténé, handler sans `Principal`, aléa, action non épinglée, CVE | selftest | `node quality/selftest/run.ts --case 'sast-*,wf-*,cve-*' …` | ❌ W0 | ⬜ pending |
| 01-12-T2 | 01-12 | 7 | QUAL-05, QUAL-06 | T-01-47 | Test faible déterministe (mutation), couverture, échappatoire, assertion, chemin protégé | selftest | `node quality/selftest/run.ts --case <5 cas> --report reports/selftest-01-12-qual0506.json` | ❌ W0 | ⬜ pending |
| 01-12-T3 | 01-12 | 7 | QUAL-06, QUAL-08, QUAL-09 | T-01-48, T-01-57 | Table sans RLS, dépendance non approuvée, politique pnpm affaiblie, `v8 ignore` ajouté au canari | selftest | `node quality/selftest/run.ts --case 'db-*,deps-*,escape-hatch-coverage-ignore' …` → 4 cas | ❌ W0 | ⬜ pending |
| 01-13-T1 | 01-13 | 8 | QUAL-01, QUAL-05 | T-01-34 | Nightly lecture seule, outils en mode verrouillé, pré-commit ≤ 10 s | statique + hook | `actionlint nightly.yml && pnpm quality --only workflow-lint,workflow-audit` ; `lefthook run pre-commit --all-files` ; `install_args: "--locked"` dans `nightly.yml` | ❌ W0 | ⬜ pending |
| 01-13-T2 | 01-13 | 8 | QUAL-01 | T-01-35, T-01-36 | Limites documentées ; outil D-07b refusé sans variable humaine | statique + négatif | `pnpm quality --only typecheck,lint,format,deadcode` ; `demo-prs.ts` sans variable → code ≠ 0 | ❌ W0 | ⬜ pending |
| 01-13-T3 | 01-13 | 8 | QUAL-01, QUAL-05 | — | Profil complet en CI (dont `coverage` fusionné), 27 cas verts, budgets mesurés | e2e CI + selftest | artefact `gate` du run (`gh run download`) ; `node quality/selftest/run.ts` → 27 cas | n/a | ⬜ pending |
| 01-14-T1 | 01-14 | 9 | QUAL-07 | — | Relecture humaine D-01 avant le verrou | checkpoint:decision | manuel (réponse consignée) | n/a | ⬜ pending |
| 01-14-T2 | 01-14 | 9 | QUAL-07, QUAL-06, QUAL-01 | T-01-37, T-01-39, T-01-41, T-01-49, T-01-54 | Verrou : deny Edit (couvre Write) dérivé de la liste protégée complète, deny signature et clés (D-14), garde, `--base-dir`, job `gate` seul, `install_args: "--locked"` conservé, verdict `--dry-run` | unit + e2e processus | `pnpm vitest run --project unit quality/lock.test.ts` ; `pnpm quality --only workflow-lint,workflow-audit,lint,format,typecheck` | ❌ W0 | ⬜ pending |
| 01-14-T3 | 01-14 | 9 | QUAL-07, QUAL-09, QUAL-01 | T-01-38, T-01-40, T-01-49, T-01-50, T-01-53, T-01-54 | Clé matérielle enrôlée et `allowed_signers` humain, ruleset `quality` (source = application), sept refus de l'agent, D-07b signés dont `workflow-rewrite` | checkpoint:human-action + lecture API | manuel ; puis `gh api repos/sebc-dev/prosperity/rules/branches/main` (lecture) | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky* — commandes abrégées ; la commande exacte et son `<fails_when>` sont dans la tâche du PLAN. Toutes les commandes s'exécutent avec `mise exec --`.

Sampling : chaque tâche `auto` a au moins une commande `<automated>` ; les seules tâches sans commande sont des checkpoints humains (01-01-T2, 01-02-T1, 01-04-T1, 01-07-T1, 01-14-T1, 01-14-T3). Aucune fenêtre de trois tâches d'implémentation consécutives sans vérification automatique.

Correspondance exigences → tests (depuis 01-RESEARCH.md § Validation Architecture) :

| Req ID | Test Type | Automated Command |
|--------|-----------|-------------------|
| QUAL-01 | unit + e2e | `pnpm vitest run quality/run.test.ts` ; PR réelle (D-07b) |
| QUAL-02 | selftest | `node quality/selftest/run.ts --case 'lint-*,types-*'` (ou `GATE_SELFTEST_CASES='lint-*,types-*' pnpm quality --only selftest`) |
| QUAL-03 | selftest | `node quality/selftest/run.ts --case 'arch-*,deadcode-*,dup-*'` |
| QUAL-04 | selftest | `node quality/selftest/run.ts --case 'sec-*,sast-*,wf-*,cve-*'` |
| QUAL-05 | unit + integration + selftest | `pnpm quality --only unit` (globs purs à 100 %) ; `pnpm quality --only coverage` (plancher global sur tout `src/**`, run fusionné `unit` + `integration`) ; `pnpm quality --only mutation` |
| QUAL-06 | selftest | `node quality/selftest/run.ts --case 'integrity-*,escape-hatch-*'` |
| QUAL-07 | manuel guidé + e2e | tentative d'édition en session agent ; `gh api …/rulesets` |
| QUAL-08 | integration + selftest | `pnpm vitest run --project integration` |
| QUAL-09 | selftest + PR réelle | `node quality/selftest/run.ts --case 'deps-*'` |

---

## Wave 0 Requirements

Couverture par les plans (case cochée = créé par une tâche planifiée, non encore exécutée ; `wave_0_complete` passera à `true` à l'exécution) :

- [x] `quality/` : runner, rapport, outils (01-01-T1), registre de checks (un fichier par check, 01-01 à 01-09), intégrité et compteur (01-06-T1/T2), approbation signée (01-07-T2, après la décision de clé 01-07-T1), deps-guard et verdict hors PR (01-08-T1/T2) ; `quality/selftest/` : runner (01-10-T1) et 27 cas (01-10-T2, 01-11, 01-12)
- [x] `vitest.config.ts` (01-03-T1, périmètre `GATE_COVERAGE_SCOPE` ; projet `integration` 01-05-T2 ; check `coverage` fusionné 01-05-T3), `stryker.config.mjs` (01-03-T3), `eslint.config.mjs` et `tsconfig.json` (01-02), `eslint.security.config.mjs` (01-04-T3), `.dependency-cruiser.cjs`, `knip.json`, `.jscpd.json` (01-09), `.gitleaks.toml` (01-04-T2), `biome.json` (01-02-T2), `lefthook.yml` (01-01-T1, complété 01-04, 01-13, 01-14)
- [x] `test/` : `globalSetup` Testcontainers et `test/db.ts` (01-05-T2), méta-tests RLS `owner_member_id`, rôle app sans DDL et rôle de migration (01-05-T3)
- [x] `src/shared/money/` + tests par exemples et propriétés (01-03-T2), `src/db/` (fournisseur SQL, `migrateToLatest`, `provisionMigrator`, 01-05-T1), `db/migrations/0001_foundation.sql` (01-05-T1)
- [x] `mise install` puis `pnpm install --frozen-lockfile` (01-01-T1, 01-02-T2)
- [x] Mesure de stabilité Stryker (Q2) : 20 exécutions du canari (01-03-T3)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Le check requis `quality` (statut publié par l'application `prosperity-gate`) bloque le merge sur `main` | QUAL-01, QUAL-07 | Seul GitHub le prouve (ruleset, source du statut) | PR réelle rouge → merge refusé (01-14-T3, étape 8) |
| Une PR qui réécrit `.github/workflows/quality.yml` obtient `gate` vert mais `quality` rouge | QUAL-07 (critère 4) | Le juge `workflow_run` ne tourne que sur GitHub, depuis `main` | Scénario `workflow-rewrite` de `demo-prs.ts` (01-14-T3, étape 9) ; preuve locale par `quality/verdict.ts --dry-run` dans `quality/lock.test.ts` |
| Approbation signée par la clé matérielle acceptée, invalidée par le push suivant (`approval-stale`), non signée refusée (`approval-unsigned`), signée par une clé hors `allowed_signers` refusée (`approval-signer-not-allowlisted`) | QUAL-06 | Seul l'humain peut actionner la clé ; le juge hors PR ne tourne que sur GitHub | Scénarios `signed-approval`, `unsigned-approval`, `foreign-key-approval` de `demo-prs.ts` (01-14-T3, étape 9) ; première preuve par la PR de bootstrap (étape 5) |
| Dépendance ajoutée sans `deps-approved` bloquée | QUAL-09 | PR réelle | Passage manuel guidé D-07b |
| Édition ou écriture d'un fichier de la gate, pose de label, fusion, commit signé et ajout de clé par l'agent refusés | QUAL-07 | Session agent réelle | Tentatives Edit, Write, `sed -i`, `gh pr edit --add-label`, `gh pr merge`, `git commit -S` d'approbation, `gh ssh-key add` en session Claude Code neuve (01-14-T3, étape 3) |
| Clé d'approbation enrôlée avec présence physique, `quality/allowed_signers` écrit et committé par l'humain | QUAL-06, QUAL-07 | Geste physique sur l'authentificateur | 01-14-T3, étapes 1 et 2 ; empreintes consignées |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (les checkpoints humains exceptés)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (aucune commande `MISSING`)
- [x] No watch-mode flags (aucun `--watch` dans une commande `<automated>`)
- [ ] Feedback latency < 60s : tenu par `pnpm quality --profile push` après chaque commit ; les commandes de tâche lourdes (mutation, intégration PG, auto-test, attente d'un run CI) dépassent 60 s et ne servent qu'à la fin de leur tâche
- [ ] `nyquist_compliant: true` set in frontmatter (posé par `/gsd-validate-phase` après exécution)

**Approval:** pending
