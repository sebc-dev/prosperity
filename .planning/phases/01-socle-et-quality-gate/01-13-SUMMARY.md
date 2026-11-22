---
phase: 01-socle-et-quality-gate
plan: 13
subsystem: infra
tags: [quality-gate, nightly, lefthook, agent-guard, documentation, demo-prs, stryker, ci-budget]

requires:
  - phase: 01-socle-et-quality-gate
    provides: "gate `pnpm quality` et ses profils (01-01 à 01-09), garde de l'agent `quality/agent-guard/` (01-06), juge hors PR et workflow `quality` (01-07, 01-08), 27 cas d'auto-test (01-10 à 01-12)"
provides:
  - "Workflow `nightly` (planifié + manuel, lecture seule) : gate complète forcée, mutation complète, fast-check 1000, packs Semgrep complets, trufflehog advisory"
  - "Pré-commit de confort (format, lint-staged, workflow-lint-staged, escape-hatches, gitleaks-staged), 1,3 à 4,1 s par commit"
  - "Messages et commentaires du garde de l'agent alignés sur D-15 (label = approbation ; signature et clés = hygiène), refus et tests inchangés"
  - "`docs/quality-gate.md` : commandes, checks, verdict, procédure d'approbation par label, juge hors PR, décisions réversibles, 15 limites connues"
  - "`quality/selftest/demo-prs.ts` : outil humain du passage manuel D-07b (6 scénarios)"
  - "Budgets mesurés : pré-push 13 s (60 s), job CI 3 min 28 s (10 min), auto-test 27 cas en 1 min 45 s"
affects: [01-14, 01-15]

actuals:
  tokens: 11564   # chars/4 sur le diff complet 70f8a15..24864d6 (46 255 caractères)
  tasks: 3
  commits: 5      # MESURÉ : git rev-list --count 70f8a15..24864d6 (hors commit de ce SUMMARY)
plan_head_before: 70f8a1519ab7a9edc92bcc7b174160e8d6ff029d
plan_head_after: 24864d6505d0b9b0ccb1ccc416e4f74128efdecb

tech-stack:
  added: []
  patterns:
    - "La gate retire de son environnement les variables git qui désignent le dépôt de l'appelant avant de lancer un check (`clearRepoGitVariables`)"
    - "Outil de démonstration : worktree jetable depuis `origin/main`, cas d'auto-test appliqué depuis le dépôt courant, hooks locaux coupés (`LEFTHOOK=0`) pour que la violation atteigne GitHub"

key-files:
  created:
    - .github/workflows/nightly.yml
    - docs/quality-gate.md
    - quality/selftest/demo-prs.ts
    - quality/tools.test.ts
  modified:
    - lefthook.yml
    - knip.json
    - quality/agent-guard/gh-rules.ts
    - quality/agent-guard/git-rules.ts
    - quality/agent-guard/misc-rules.ts
    - quality/run.ts
    - quality/tools.ts
    - stryker.config.mjs

key-decisions:
  - "Le job de la PR s'appelle encore `quality` (renommé `gate` au plan 01-14) : `docs/quality-gate.md` le dit ainsi ; le scénario `workflow-rewrite` écrit un job `gate`, nom final"
  - "`GIT_INDEX_FILE` reste dans l'environnement de la gate : le pré-commit lit l'index du commit en cours ; seules les variables qui désignent le dépôt sont retirées"
  - "Stryker ignore `reports/` et `coverage/` (sorties d'autres checks, réécrites en parallèle) ; aucun seuil, aucun périmètre de mutation touché"

patterns-established:
  - "Un test qui crée un dépôt git jetable ne doit jamais hériter de `GIT_DIR` : la gate nettoie son environnement à l'entrée de `run.ts`"

requirements-completed: [QUAL-01, QUAL-05, QUAL-07]

coverage:
  - id: D1
    description: "Le workflow `nightly` est valide (actionlint, zizmor hors ligne) et joue le profil complet forcé ; le profil nightly joué en local passe (`verdict : pass`, 3 min 41 s)"
    requirement: QUAL-05
    verification:
      - kind: other
        ref: "mise exec -- actionlint .github/workflows/nightly.yml ; zizmor --offline : aucun finding ; GATE_FORCE_SELFTEST=1 GATE_MUTATION_SCOPE=all FAST_CHECK_NUM_RUNS=1000 pnpm quality : verdict pass"
        status: pass
    human_judgment: false
  - id: D2
    description: "Le pré-commit tient le budget de 10 s et passe sur l'arbre entier"
    requirement: QUAL-01
    verification:
      - kind: other
        ref: "lefthook run pre-commit --all-files : 2,4 s (10,8 s à froid) ; commits réels : 1,3 à 4,1 s"
        status: pass
    human_judgment: false
  - id: D3
    description: "Messages du garde alignés sur D-15, aucun refus ni test modifié"
    requirement: QUAL-07
    verification:
      - kind: other
        ref: "pnpm vitest run --project unit quality/agent-guard/ : 242 tests passés ; grep D-14 = 0, D-15 >= 3 par fichier ; autres fichiers du garde inchangés depuis 27e0692"
        status: pass
    human_judgment: false
  - id: D4
    description: "Profil `full` prouvé sur le runner hébergé : seuls integrity, approvals et deps échouent fermés (`missing-trusted-report`), auto-test déclenché et vert (27 cas), mutation et intégration passées"
    requirement: QUAL-01
    verification:
      - kind: other
        ref: "run GitHub 45020111124 sur la PR #300 (tête 7d63798), artefact `gate` : commande de vérification du plan, sortie VERIFY1_OK"
        status: pass
    human_judgment: false
  - id: D5
    description: "La documentation décrit la gate sans la présenter comme infranchissable : le jeton partagé de D-15, les hooks désactivables, les règles deny non étanches, la PR qui réécrit son workflow"
    requirement: QUAL-01
    verification: []
    human_judgment: true
    rationale: "Le contenu de `docs/quality-gate.md` (limites et contrôles compensatoires) se juge à la lecture ; les mots-clés exigés sont vérifiés par grep"
  - id: D6
    description: "L'outil `demo-prs.ts` refuse de tourner sans `PROSPERITY_HUMAN_GATE_EDIT=1` et sa chaîne (types, lint, code mort, workflows générés) est valide ; les scénarios n'ont pas été joués sur GitHub"
    requirement: QUAL-01
    verification:
      - kind: other
        ref: "env -u PROSPERITY_HUMAN_GATE_EDIT node quality/selftest/demo-prs.ts blocked-check : code 2 ; pnpm quality --only typecheck,lint,format,deadcode : pass ; actionlint sur les deux workflows générés : OK"
        status: pass
    human_judgment: true
    rationale: "Les scénarios ouvrent de vraies PR et supposent des gestes humains sur GitHub : jouées au plan 01-14 (passage D-07b)"

duration: 28min
completed: 2026-11-22
status: complete
---

# Phase 01 Plan 13: Nightly, pré-commit, documentation de la gate et mesure des budgets Summary

**Nightly planifié, pré-commit de confort, messages du garde alignés sur D-15, `docs/quality-gate.md` avec ses 15 limites connues et outil humain `demo-prs.ts` ; le profil complet est prouvé sur le runner hébergé (PR #300, job de 3 min 28 s, auto-test de 27 cas vert, seuls les trois juges de confiance échouent fermés) et le pré-push tient en 13 s. Trois défauts de la gate découverts en route ont été corrigés, dont un qui faisait écrire des commits « fixture » dans la branche de l'appelant depuis un hook pré-push.**

## Performance

- **Durée :** ~28 min (11:40 à 12:08 UTC)
- **Tâches :** 3, plus 2 corrections (hors plan) et 1 complément de documentation
- **Fichiers :** 4 créés, 8 modifiés (12 au total, 756 insertions)

## Accomplissements

- **Tâche 1** : `nightly.yml` (`schedule` 03:23 UTC + `workflow_dispatch`, `permissions: {}`, job en lecture seule, actions épinglées par SHA comme `quality.yml`, `install_args: "--locked"`, trufflehog advisory, artefact `gate-nightly`) ; `lefthook.yml` complété ; neuf chaînes du garde de l'agent réécrites au mot près (aucune expression régulière, règle ni test modifié).
- **Tâche 2** : `docs/quality-gate.md` (commandes, 22 checks, schéma de `gate.json`, procédure d'approbation D-15, juge hors PR, décisions réversibles, nightly, limites) ; `demo-prs.ts` avec les scénarios `blocked-check`, `human-label`, `bot-label`, `deps-unapproved`, `workflow-rewrite`, `deps-too-recent`, ajouté aux entrées de `knip.json`.
- **Tâche 3** : budgets mesurés, profil nightly joué en local, profil complet prouvé sur GitHub après poussée de `sebc-dev/jiaolong`.

## Mesures (QUAL-01 lu selon D-12)

| Mesure | Résultat | Cible |
|---|---|---|
| Pré-push `pnpm quality --profile push` | **13,1 s** en local, 13,5 s via le hook | 60 s |
| Pré-commit, commits réels (1 à 3 fichiers) | 1,3 à 4,1 s | 10 s |
| Pré-commit `--all-files` | 2,4 s (10,8 s au premier passage, cache ESLint froid) | 10 s |
| Job CI `quality` (run 45020111124) | **3 min 28 s** (12:01:01 à 12:04:29) | 10 min |
| Auto-test complet, local (`--jobs` par défaut) | 1 min 44 s à 1 min 46 s | |
| Auto-test dans le job CI | 158,9 s | |
| Profil nightly local | 3 min 41 s, `verdict : pass` | |
| `pnpm quality` complet, local | 1 min 04 s, `verdict : pass` | |

Checks `skipped: ci-only` au pré-push (11) : `approvals`, `container`, `coverage`, `cve`, `deps`, `integration`, `integrity`, `lint-security`, `mutation`, `selftest`, `workflow-audit` ; liste identique à D-12, aucun check déplacé.

Durées du job CI par check : selftest 158,9 s (27 cas joués), mutation 124,4 s (score 98,94 %, 93 tués, 1 survivant), sast 23,0 s, coverage 22,6 s, integration 21,3 s, unit 17,9 s, lint 15,3 s, typecheck 5,0 s, secrets 2,4 s ; le reste sous 2 s.

Durée par cas de l'auto-test (local, en parallèle, secondes) : `tests-weak-assertion` 32,2 ; `lint-*` (six cas) 13,6 à 15,1 ; `sast-*` (trois cas) 11,5 à 13,3 ; `tests-coverage-drop` 8,6 ; `types-unchecked-index` 5,8 ; `db-table-without-rls` 4,9 ; `cve-high-severity` 2,6 ; `sec-generated-secret` 2,4 ; `deadcode-unused-export` 2,1 ; `arch-*` 1,3 et 1,4 ; `wf-unpinned-action` 1,2 ; `integrity-*` 1,0 à 1,1 ; `deps-policy-weakened` 1,0 ; `dup-new-clone`, `escape-hatch-*`, `deps-added-unapproved` 0,6 à 0,8. Somme des durées de cas : 193 s.

Artefact `gate` du run CI : profil `full`, 27 cas d'auto-test verts, `integration` et `coverage` passés sur le Docker du runner, `mutation` passée ; `integrity`, `approvals` et `deps` en `failed` avec `missing-trusted-report` (voulu jusqu'au verrou du plan 01-14) ; `lint-security` advisory en échec (177 issues, sans effet sur le verdict).

## Task Commits

1. **Tâche 1 : nightly, pré-commit, messages du garde** - `b7271a9` (feat)
2. **Tâche 2 : documentation et outil de démonstration** - `1ee51b3` (feat)
3. **Correction : bac à sable Stryker** - `fbb8393` (fix)
4. **Correction : variables git du hook pré-push** - `7d63798` (fix)
5. **Compléments de limites connues** - `24864d6` (docs)

La tâche 3 ne modifie aucun fichier du dépôt (poussée et lectures de runs).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `lint-staged` échouait sur `semgrep/prosperity.ts`**
- **Found during :** Tâche 1 (`lefthook run pre-commit --all-files`)
- **Issue :** ESLint ignore volontairement `semgrep/**` ; passé en argument explicite il émet un avertissement « File ignored » que `--max-warnings 0` transforme en échec.
- **Fix :** `--no-warn-ignored` ajouté à la commande du job (aucune règle ni ignore touché).
- **Files modified :** `lefthook.yml` | **Commit :** `b7271a9`

**2. [Rule 1 - Bug] Le nightly local échouait en `tool-error` sur la mutation**
- **Found during :** Tâche 3 (profil nightly local)
- **Issue :** avec `GATE_MUTATION_SCOPE=all`, Stryker copiait dans son bac à sable `reports/coverage/coverage-final.json` pendant que le check `coverage` le réécrivait : `ENOENT`. Le profil de PR n'y était pas exposé tant que le diff ne contenait pas de fichiers à muter.
- **Fix :** `ignorePatterns: ['reports', 'coverage']` dans `stryker.config.mjs` (sorties de la gate, jamais du code ni des tests ; aucun seuil touché). Nightly local rejoué : pass.
- **Files modified :** `stryker.config.mjs` | **Commit :** `fbb8393`

**3. [Rule 1 - Bug] Un hook pré-push dans un worktree lié faisait commiter les tests dans la branche de l'appelant**
- **Found during :** Tâche 3 (première poussée refusée : `unit` en échec, 17 issues)
- **Issue :** git exporte `GIT_DIR` (chemin absolu) à ses hooks ; les tests qui créent un dépôt jetable (`git init`, `git commit`) en héritaient et écrivaient dans la branche de l'appelant. Constat : dix commits « fixture », « un », « deux » ajoutés à `worktree-agent-a728d0220b5224dc5`, et une branche `pr` créée dans le dépôt partagé ; ni la poussée (refusée par le hook) ni `main` n'ont été touchés.
- **Récupération (branche d'agent uniquement) :** `git reset --mixed fbb8393` (arbre de travail intact, état propre), `git branch -f worktree-agent-… fbb8393`, retour sur la branche, `git branch -D pr`. Aucun `reset --hard`, `clean`, `update-ref` ni `stash`.
- **Fix :** `clearRepoGitVariables` (`quality/tools.ts`) appelée en tête de `main()` dans `quality/run.ts` ; `GIT_INDEX_FILE` conservé. Test unitaire `quality/tools.test.ts`. Vérifié : avec `GIT_DIR` factice, `vitest` direct échoue, `pnpm quality --only unit` passe ; seconde poussée réelle propre (aucun commit parasite).
- **Files modified :** `quality/tools.ts`, `quality/run.ts`, `quality/tools.test.ts` | **Commit :** `7d63798`

**4. [Écart de rédaction] Nom du job de la PR**
- Le plan parle du « job `gate` » de `quality.yml` ; ce job s'appelle encore `quality` jusqu'au plan 01-14 (SUMMARY 01-01). `docs/quality-gate.md` décrit l'état réel et le renommage ; le scénario `workflow-rewrite` écrit un job `gate`, nom final.

**Total deviations :** 3 auto-fixed (3 Rule 1) et 1 écart de rédaction. **Impact :** aucun seuil, ignore, test ou échappatoire ajouté ni affaibli ; le garde de l'agent n'a changé que dans ses chaînes.

## Authentication Gates

Aucun. `gh` était authentifié ; la poussée `git push origin HEAD:sebc-dev/jiaolong` a utilisé les identifiants existants.

## Issues Encountered

- **Poussée de la branche faite depuis le worktree de l'agent.** `sebc-dev/jiaolong` distant était resté à `80e3ab6` (plan 01-01) : la poussée a publié d'un coup les 77 commits des plans 01-02 à 01-12 et les miens (`80e3ab6..7d63798`), en avance rapide. La branche locale `sebc-dev/jiaolong` de l'orchestrateur est donc un ancêtre du distant : fusionner la branche de l'agent la fera rattraper. Le distant est à `7d63798`, sans le commit de ce SUMMARY.
- **Hooks installés dans le dépôt partagé.** Le premier `lefthook run` a exécuté « sync hooks » : `pre-commit` et `pre-push` existent maintenant dans les hooks communs, donc aussi pour le worktree de l'orchestrateur.
- **`reset-approval` échoue sur la PR #300** (`'gate-change-approved' not found`) : les labels n'existent pas encore dans le dépôt. Sans conséquence (`continue-on-error`) ; à créer par l'humain avant le passage D-07b. Noté dans les limites connues.
- **Limites des plans 01-08 et 01-12 consignées dans la documentation :** `workflow-audit` rend `passed` si zizmor ne peut pas valider un workflow ; un `tool-error` passager de `sast` (registre Semgrep) a été signalé au plan 01-12. Il ne s'est pas reproduit : trois auto-tests complets locaux (27 cas en parallèle) et le run CI.
- `lint-security` (advisory) : 177 issues (173 avant ce plan), sans effet sur le verdict.
- Les commandes mêlant `git` à d'autres commandes, ou pointant git vers un autre dossier, sont refusées par l'environnement du worktree : vérifications jouées en commandes séparées.

## Known Stubs

Aucun.

## Threat Flags

Aucun nouvel élément de surface hors du `<threat_model>`. Mitigations jouées : T-01-34 (`nightly.yml` en lecture seule, SHA, aucun contexte dans `run:`, zizmor sans finding), T-01-35 (limites documentées), T-01-36 (`demo-prs.ts` refuse sans `PROSPERITY_HUMAN_GATE_EDIT=1`, ne la pose jamais, ne pose ni ne retire de label), T-01-69 (grep : aucun `D-14` dans les trois fichiers du garde), T-01-SC (aucun paquet ajouté).

## User Setup Required

Avant le passage manuel D-07b (plan 01-14) : créer dans le dépôt les labels `gate-change-approved` et `deps-approved` (geste humain, l'agent n'en crée aucun).

## Next Phase Readiness

- Le plan 01-14 fige la configuration : la gate est documentée, mesurée et prouvée sur le runner (PR #300). `integrity`, `approvals` et `deps` attendent leurs étapes de confiance et le verrou.
- Le nightly ne s'exécutera qu'après la fusion de la PR de bootstrap (vérification au plan 01-14).
- `demo-prs.ts` n'a pas été joué sur GitHub ; le passage D-07b l'utilise (`origin/main` doit alors porter la gate).
- Les budgets laissent de la marge : pré-push 13 s sur 60 s, job CI 3 min 28 s sur 10 min.

## Self-Check: PASSED

- Fichiers présents : `.github/workflows/nightly.yml`, `docs/quality-gate.md`, `quality/selftest/demo-prs.ts`, `quality/tools.test.ts`, `lefthook.yml`.
- Commits ancêtres de HEAD : `b7271a9`, `1ee51b3`, `fbb8393`, `7d63798`, `24864d6`.
- Critères d'acceptation : tâche 1 (3 SHA, `FAST_CHECK_NUM_RUNS` 1, `--locked` 1, 5 jobs lefthook, `D-14` 0, `hygiène D-03` 0, `D-15` 3/4/3, `hygiène` 4/2) ; tâche 2 (`## Limites connues` 1, `sebc-dev` 3, scénarios 24, `approvers.json` 4, `D-15` 3, `quality-verdict` 2) ; tâche 3 (27 cas, commande de vérification CI : `VERIFY1_OK`, auto-test local 27 verts, aucun worktree `selftest-`).
- `pnpm quality` : `verdict : pass`.
