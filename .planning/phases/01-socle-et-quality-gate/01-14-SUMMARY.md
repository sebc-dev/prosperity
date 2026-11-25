---
phase: 01-socle-et-quality-gate
plan: 14
subsystem: infra
tags: [quality-gate, lock, claude-code-permissions, codeowners, github-app, out-of-pr-judge, ruleset, sonarqube, demo-prs]

requires:
  - phase: 01-socle-et-quality-gate
    provides: "gate `pnpm quality` et ses profils (01-01 à 01-13), garde de l'agent (01-06), approbation par label et juge hors PR (01-07, 01-08), SonarQube nightly (01-15)"
provides:
  - "Verrou de l'agent : 66 règles `Edit(...)` (une par chemin protégé), règles Bash (labels, fusion, API en écriture, réglages, `--no-verify`, push forcé, signature et clés en hygiène), hook PreToolUse `bash-guard.ts`, pré-commit `protected-paths`, CODEOWNERS (66 lignes `@sebc-dev`)"
  - "Workflow `quality` : job `gate` (étapes de confiance `approval-evidence`, `approvals`, `integrity`, `deps` jouées depuis la copie de base `gate-base`, `--base-dir` explicite) et job `reset-approval`"
  - "Juge hors PR en service : application GitHub `prosperity-gate` (ID 5887661), environnement `gate-verdict` restreint à `main`, statut `quality` publié par `prosperity-gate[bot]`"
  - "Ruleset `Main` (17645569) final : unique check requis `quality` de source `prosperity-gate`, PR obligatoire, aucun contournement, `strict` activé"
  - "PR de bootstrap #300 fusionnée (064e1c6) ; nightly vert sur `main` ; analyse SonarQube nightly en service (D-16)"
  - "Preuve D-07b sur de vraies PR (#302 à #306) et refus de l'agent consignés"
affects: [phase-02, toute-modification-de-la-gate]

actuals:
  tokens: 7080    # chars/4 sur le diff 2e70009..e241321 hors pnpm-lock.yaml (28 319 caractères)
  tasks: 3
  commits: 4      # MESURÉ : git rev-list --count 2e70009..e241321 (hors #301 et hors commit de ce SUMMARY)
plan_head_before: 2e70009
plan_head_after: e241321a804bc58cfe764cca6153e5ed851eaeaf

tech-stack:
  added: []
  patterns:
    - "Deny de fichier écrit `Edit(...)` seulement : il couvre Edit, Write et NotebookEdit ; aucune règle `Write(...)` à chemin (acceptée mais jamais appliquée), testé"
    - "Statut requis rendu hors de portée de la PR : source = GitHub App, clé dans un environnement restreint à `main`, jugement rejoué depuis la branche par défaut"
    - "Étapes de confiance lues depuis une copie de base (`git worktree add --detach $RUNNER_TEMP/gate-base`), jeton réservé à la seule étape de collecte des preuves"

key-files:
  created:
    - .claude/settings.json
    - .github/CODEOWNERS
    - quality/lock.test.ts
  modified:
    - .github/workflows/quality.yml
    - lefthook.yml
    - mise.toml
    - mise.lock
    - package.json
    - pnpm-lock.yaml
    - pnpm-workspace.yaml
    - quality/selftest/cycle.test.ts

key-decisions:
  - "D-01 relu et approuvé (réponse `approve`) : D-05 tel que planifié, `.claude/CLAUDE.md` entièrement protégé, `agentExempt` vide, disposition `src/` de Q5 = A, seuils, 66 chemins protégés, allowlist `sebc-dev`, workflows et Sonar approuvés, limites 1, 2, 5, 9 et 12 acceptées"
  - "pnpm ramené de 12.21.0 à 12.18.0 : `@pnpm/exe.netbsd-x64` (créé le 2026-11-10, livré avec pnpm >= 12.19) échoue à la règle d'âge de 30 jours ; à relever après le 2026-12-10"
  - "Surcharge pnpm TEMPORAIRE `'minimatch@>=11': 10.2.6` : `@isaacs/nonrecursive-glob-match` (créé le 2026-10-26, tiré par minimatch 11 via eslint 10.15.0) échoue à la même règle ; à retirer le 2026-11-26"
  - "Test de parallélisme de l'auto-test rendu déterministe (barrière avec plafond de 20 s) au lieu d'une fenêtre fixe de 250 ms qui flanchait sous charge ; aucune assertion retirée"
  - "L'analyse Sonar nightly tourne en timer systemd UTILISATEUR sur le poste kfzcore (et non kfzserver comme le plan l'écrivait), clone `~/prosperity-sonar`"

patterns-established:
  - "Tout changement d'un chemin protégé passe par un commit humain, une PR et le label `gate-change-approved` posé par `sebc-dev` après le dernier push"
  - "Une dépendance trop récente se résout par un épinglage daté et consigné, jamais par un assouplissement de `minimumReleaseAge`"

requirements-completed: [QUAL-07, QUAL-06, QUAL-09, QUAL-01]

coverage:
  - id: D1
    description: "Le verrou préparé est cohérent et prouvé de bout en bout : deny `Edit` par chemin protégé, aucune règle `Write(...)` morte, hook Bash déclaré, CODEOWNERS complet, invariants des deux workflows, refus du garde (sed -i, gh pr merge, gh pr edit --add-label, gh api -X POST labels), juge hors PR en `--dry-run`"
    requirement: QUAL-07
    verification:
      - kind: unit
        ref: "mise exec -- pnpm vitest run --project unit quality/lock.test.ts : 23 tests passés (rejoué par l'agent le 2026-11-25 sur e241321)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Workflows et fichiers modifiés conformes à la gate (actionlint, zizmor, lint, format, types)"
    requirement: QUAL-01
    verification:
      - kind: other
        ref: "mise exec -- pnpm quality --only workflow-lint,workflow-audit,lint,format,typecheck : verdict pass (rejoué par l'agent)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Ruleset final : unique check requis `quality` publié par l'application `prosperity-gate`, PR obligatoire, aucun contournement"
    requirement: QUAL-01
    verification:
      - kind: other
        ref: "gh ruleset view 17645569 et gh api repos/sebc-dev/prosperity/rules/branches/main : context quality, integration_id 5887661, strict true, bypass never (rejoués par l'agent)"
        status: pass
    human_judgment: false
  - id: D4
    description: "PR de bootstrap #300 fusionnée avec ses deux approbations par label reconnues sur le runner ; nightly vert sur `main`"
    requirement: QUAL-07
    verification:
      - kind: other
        ref: "gh pr view 300 (MERGED, 064e1c6, labels présents) ; run quality 45354011369, artefact gate : approvals.json approved [gate-change-approved, deps-approved], principal sebc-dev, github-label-events@1 ; nightly 45390446428 success"
        status: pass
    human_judgment: false
  - id: D5
    description: "Refus de l'agent en session neuve (Edit, Write, sed -i, label par pr edit, label par gh api, fusion, gh label create) ; réglages d'environnement, auto-fusion et durcissements Actions"
    requirement: QUAL-07
    verification:
      - kind: manual_procedural
        ref: "Refus (a) et garde `gh label` / `gh variable` / `gh api environments|actions/permissions|rulesets` observés par l'orchestrateur ; (b) à (g), environnement `gate-verdict`, auto-fusion et durcissements Actions déclarés par l'humain"
        status: unknown
    human_judgment: true
    rationale: "L'agent ne peut pas relire ces réglages (le verrou le lui interdit) : la preuve repose sur la déclaration de l'humain"
  - id: D6
    description: "Comportements D-07b sur de vraies PR (#302 à #306) et refus de version trop récente"
    requirement: QUAL-07
    verification:
      - kind: e2e
        ref: "PR #302 blocked-check, #303 human-label, #304 bot-label, #305 deps-unapproved, #306 workflow-rewrite : relevés par l'orchestrateur depuis les rapports de run et les statuts de commit ; deps-too-recent joué en local"
        status: pass
    human_judgment: false
  - id: D7
    description: "Analyse SonarQube nightly en service, sans effet sur le verdict (D-16)"
    requirement: QUAL-09
    verification: []
    human_judgment: true
    rationale: "Le timer vit hors du dépôt (poste de l'humain) : l'état est déclaré par l'humain, l'agent ne peut pas le lire"

duration: ~3 jours calendaires (2026-11-22 au 2026-11-25), dont la quasi-totalité en gestes humains
completed: 2026-11-25
status: complete
---

# Phase 01 Plan 14: Verrou de la quality gate, juge hors PR et preuve D-07b Summary

**Verrou actif : 66 règles `Edit(...)` et garde Bash pour l'agent, job `gate` à étapes de confiance depuis la base, statut `quality` publié par l'application `prosperity-gate` comme seul check requis de `main`, PR de bootstrap #300 fusionnée, nightly et analyse Sonar en service, et les cinq scénarios D-07b rejoués sur de vraies PR (#302 à #306) avec les résultats attendus.**

## Performance

- **Durée :** ~3 jours calendaires (2026-11-22 à 2026-11-25) ; le travail de l'agent tient en la préparation du verrou (tâche 2) et en la vérification finale en lecture seule, le reste est humain
- **Tâches :** 3 (point de relecture, préparation du verrou, gestes humains)
- **Fichiers :** 3 créés, 8 modifiés dans les commits du plan (`2e70009..e241321`, 11 fichiers, 609 insertions, 98 suppressions)

## Accomplissements

- **Tâche 1, point de relecture D-01 : `approve`.** D-05 appliqué tel que planifié (`.claude/CLAUDE.md` protégé en entier, `agentExempt` vide), disposition de `src/` de Q5 = A, seuils, 66 chemins protégés, allowlist `sebc-dev`, workflows, configuration Sonar et limites 1, 2, 5, 9 et 12 de `docs/quality-gate.md` acceptés.
- **Tâche 2, verrou préparé (`739f6a6`, commit humain).** 5 fichiers (`.claude/settings.json`, `.github/CODEOWNERS`, `.github/workflows/quality.yml`, `lefthook.yml`, `quality/lock.test.ts`) écrits par l'agent précédent, recopiés tels quels, relus et committés par l'humain avec `PROSPERITY_HUMAN_GATE_EDIT=1`. `quality/lock.test.ts` : 23 tests.
- **Tâche 3, gestes humains.** Labels, application `prosperity-gate`, environnement `gate-verdict`, ruleset transitoire puis final, fusion de #300, nightly, analyse Sonar, scénarios D-07b : tous faits (détail dans les contrôles V1 à V7).

## Task Commits

1. **Tâche 1 : point de relecture D-01** - aucun commit (réponse `approve` de l'humain)
2. **Tâche 2 : verrou préparé** - `739f6a6` (feat, commit humain `feat(01-14): active le verrou de la quality gate`)
3. **Tâche 3 : gestes humains** - commits issus des écarts rencontrés : `467a4a1` (chore, pnpm 12.18.0), `fa41456` (chore, surcharge minimatch temporaire), `e241321` (test, barrière déterministe) ; puis hors de la branche du plan, PR #301 `84064fe` (fix, Sonar sous systemd)

La tâche 3 elle-même est faite sur GitHub et sur le poste de l'humain. **Plan metadata :** commit de ce SUMMARY (`docs(01-14)`).

## Contrôles en lecture seule (V1 à V7)

Légende : **PASS** = relu par l'agent ; **PASS (orchestrateur)** = relevé en lecture seule par l'orchestrateur ; **PASS (déclaré)** = déclaré par l'humain ; **NON VÉRIFIABLE PAR L'AGENT (verrou)** = lecture refusée à l'agent par construction (un refus est une preuve que le verrou tient) ; **ÉCART** = conforme au plan à une variante près, décrite.

| Contrôle | Résultat | Preuve |
|---|---|---|
| **V1** labels et première approbation (vérité 3) | **PASS** pour l'approbation ; labels **PASS (déclaré)** et présents sur #300 | `gh label list` refusé à l'agent (« gh label réservé à l'humain ») ; `gh pr view 300` : `MERGED`, labels `gate-change-approved` et `deps-approved` présents. Artefact `gate` du dernier run `quality` de #300 (45354011369, tête `e241321`) : `reports/approvals.json` approuve `gate-change-approved` et `deps-approved`, `bootstrap: true`, `verifier: github-label-events@1`, `keyType: github-label`, `approval.principal: sebc-dev`, `approval.commit: e241321…` ; `integrity` « 209 écart(s) approuvé(s), listés », `deps` passé, `gate.json` : profil `full`, verdict `pass` |
| **V2** sept refus de l'agent (vérité 2) | **PASS (orchestrateur)** pour (a) et pour les gardes `gh` ; **PASS (déclaré)** pour (b) à (g) | (a) Edit `eslint.config.mjs` : « File is in a directory that is denied by your permission settings. » (orchestrateur). Garde Bash : « gh label réservé à l'humain », « gh variable réservé à l'humain », refus de `gh api …/environments`, `…/actions/permissions`, `…/rulesets` (orchestrateur) ; l'agent a lui-même reçu « PreToolUse:Bash hook error: gh label réservé à l'humain » pour `gh label list` ce jour. (b) Write, (c) `sed -i`, (d) `gh pr edit --add-label`, (e) `gh api -X POST …/labels`, (f) `gh pr merge`, (g) `gh label create` : refus déclarés par l'humain, messages exacts non consignés. **Point à vérifier** : le dépôt a 66 règles `Edit(...)` et aucune règle `Write(...)` ; l'humain déclare le refus (b) de Write. Conforme à la doctrine du plan (`Edit` couvre Write et NotebookEdit) mais à reconfirmer en relecture, voir « Points ouverts » |
| **V3** juge hors PR en service (vérité 6) | **NON VÉRIFIABLE PAR L'AGENT (verrou)** ; **PASS (déclaré)** | `gh api repos/sebc-dev/prosperity --jq .allow_auto_merge` refusé à l'agent (règle `gh api*merge*`, lecture comprise) ; `…/environments` refusé par le garde. Déclaré par l'humain : application `prosperity-gate`, ID 5887661, permission `statuses: write` seule, installée sur `sebc-dev/prosperity` seul ; environnement `gate-verdict` restreint à `main` avec variable `GATE_APP_ID` et secret `GATE_APP_PRIVATE_KEY` au niveau de l'environnement seulement ; auto-fusion désactivée |
| **V4** fusion de #300 et nightly (vérité 3) | **PASS** | `gh pr view 300` : `MERGED`, fusion `064e1c64…` à 2026-11-24T12:06:58Z (commit de fusion) ; `gh run list --workflow nightly.yml` : run `workflow_dispatch` 45390446428 sur `main` le 2026-11-24T12:07Z, conclusion `success`. Les deux runs `schedule` antérieurs (2026-11-22 et 2026-11-23) sont en échec : antérieurs à la fusion, non analysés |
| **V5** ruleset final (vérité 6) | **PASS** | `gh ruleset view 17645569` : actif, « You can bypass: never », `deletion`, `non_fast_forward`, `pull_request` (0 approbation requise) et `required_status_checks` ; `gh api repos/sebc-dev/prosperity/rules/branches/main` : unique check `context: quality`, `integration_id: 5887661` (= `prosperity-gate`), `strict_required_status_checks_policy: true`. #302 : `mergeStateStatus: BLOCKED` ; statut `quality` rouge publié par `prosperity-gate[bot]` (orchestrateur) |
| **V6** analyse SonarQube nightly (vérité 8, D-16) | **PASS (déclaré)**, **ÉCART** d'hôte | « analyse traitée (SUCCESS) » le 2026-11-24 à 15:04, serveur 26.10.0.133078 ; timer activé, prochaine échéance nightly vers 04:30 UTC plus gigue. Voir l'écart 2 : le timer est un timer systemd utilisateur sur le poste kfzcore, pas sur kfzserver |
| **V7** scénarios D-07b | **PASS (orchestrateur)**, voir tableau suivant | rapports de run et statuts de commit |

### V7, détail par PR de démonstration (toutes fermées sans fusion)

| PR | Scénario | Résultat observé (relevé par l'orchestrateur) |
|---|---|---|
| #302 | `blocked-check` | `quality` rouge publié par `prosperity-gate[bot]` (violation de lint) ; `mergeStateStatus: BLOCKED` (relu par l'agent) |
| #303 | `human-label` | rouge sans label (`gate-not-success`) ; vert après le label humain (`success`, « gate, intégrité, dépendances et approbations conformes », par `prosperity-gate[bot]`) ; rouge de nouveau après un push vide : label retiré (`unlabeled` par `github-actions[bot]` via `reset-approval` à 2026-11-24T22:48:28Z), `gate-not-success (+1)` |
| #304 | `bot-label` | label posé par `github-actions[bot]` ; `approvals.json` : `gate-change-approved: approval-actor-not-allowed` ; `quality` rouge |
| #305 | `deps-unapproved` | `deps` : `dependency-added ms (2.1.3) exige le label deps-approved` ; `quality` rouge, `gate-not-success (+2)` |
| #306 | `workflow-rewrite` | `gate` VERT (le workflow réécrit exécute `true`) mais `quality` ROUGE `integrity-failed` rendu par le juge hors PR (`quality-verdict`, déclencheur `workflow_run`, jugement depuis `main`) ; fusion BLOQUÉE |
| (local) | `deps-too-recent` | `vitest@5.1.2` refusé par `minimumReleaseAge` de pnpm, « Erreur minimumReleaseAge attendue : OK » |

Nettoyage : aucune branche `demo/gate-*` ni `gate-*` (locale ou distante ; `git fetch origin` a élagué les 5 branches distantes) ; PR #302 à #306 `CLOSED` (relu par l'agent).

**Contrôles de l'agent hors liste V** (read-only, le 2026-11-25) : `mise exec -- pnpm vitest run --project unit quality/lock.test.ts` 23 tests passés ; `pnpm quality --only workflow-lint,workflow-audit,lint,format,typecheck` verdict `pass` ; `grep -cE '"Write\(' .claude/settings.json` = 0 ; `bash-guard.ts` 1 occurrence dans `.claude/settings.json` ; `@sebc-dev` 66 lignes dans CODEOWNERS ; `name: gate` 1 ; `--base-dir "$RUNNER_TEMP/gate-base"` 6 occurrences dans `quality.yml` ; `.claude/settings.local.json` non versionné. `origin/main` porte `quality-verdict.yml`, `quality/approvers.json` et `deploy/sonar` (relu par `git ls-tree`).

## Deviations from Plan

### Écarts décidés par l'humain (étape 4 du passage, PR de bootstrap #300)

**1. [Rule 3 - Blocage] Règle d'âge des dépendances sur la PR de bootstrap**
- **Constat :** le check `deps` échouait sur la règle des 30 jours pour `@pnpm/exe.netbsd-x64` (créé le 2026-11-10, livré avec pnpm >= 12.19) et `@isaacs/nonrecursive-glob-match` (créé le 2026-10-26, tiré par minimatch 11 via eslint 10.15.0).
- **Décision de l'humain (1) :** pnpm 12.21.0 ramené à 12.18.0 (`467a4a1` : `mise.toml`, `mise.lock`, `package.json`, `pnpm-lock.yaml`) ; les 14 binaires de plateforme restants sont antérieurs au 2026-09-08. **À relever après le 2026-12-10.**
- **Décision de l'humain (2) :** surcharge pnpm TEMPORAIRE `'minimatch@>=11': 10.2.6` dans `pnpm-workspace.yaml` (`fa41456`), validée parce que `lint` et `selftest` sont restés verts. **À retirer le 2026-11-26** (PR avec `deps-approved`).
- **Écart de documentation :** `CLAUDE.md` et la section stack écrivent encore pnpm 12.21.0.
- **Aucun assouplissement** de la règle d'âge, de `minimumReleaseAge` ni de seuil.

**2. [Rule 1 - Bug] Test de parallélisme flottant de l'auto-test**
- **Constat :** `quality/selftest/cycle.test.ts`, « exécute des cas en parallèle sans interférence », s'appuyait sur une fenêtre fixe de 250 ms (pic de 1 sous charge).
- **Correction (commit humain `e241321`) :** barrière déterministe avec plafond de 20 s ; aucune assertion retirée.
- Après quoi `gate` est vert et les deux approbations sont reconnues.

**3. [Rule 1 - Bug] Premier passage Sonar en échec, `mise` absent du PATH de systemd**
- **Constat :** le timer Sonar est une unité systemd utilisateur sur le poste kfzcore (le plan visait kfzserver, qui n'est pas l'hôte retenu), clone `~/prosperity-sonar`. Premier run en échec : `mise` hors du PATH de l'unité, donc `quality/run.test.ts` (contrôle d'épinglage de mise) rouge et aucun LCOV écrit par Vitest.
- **Correction (PR #301 `fix/sonar-nightly`, commit `84064fe`, humain) :** `Environment=PATH=%h/.local/bin:…` dans `deploy/sonar/prosperity-sonar.service` et `--coverage.reportOnFailure` dans `quality/sonar/reports.ts`.
- **Résultat :** « analyse traitée (SUCCESS) » le 2026-11-24 à 15:04.
- Cette correction est sur `origin/main` mais pas dans la branche de ce plan.

### Autres écarts d'exécution

**4. [Écart de rédaction] Hôte de l'analyse Sonar** : voir l'écart 3, `user_setup` nommait kfzserver ; c'est kfzcore qui porte le timer.

**5. [Écart de rédaction] Forme du refus Write** : le plan demande de constater le refus de l'outil Write (b) ; l'humain le déclare refusé sans message exact, et le dépôt n'a aucune règle `Write(...)` (voir « Points ouverts »).

**Total des écarts :** 3 corrections (Rule 1 : 2, Rule 3 : 1) et 2 écarts de rédaction, tous décidés ou exécutés par l'humain pour les chemins protégés. **Impact sur le plan :** aucun seuil, ignore, test ou échappatoire affaibli ; la surcharge minimatch et le pnpm abaissé sont des épinglages datés, pas des assouplissements.

## Issues Encountered

- **Lecture refusée par construction.** L'agent ne peut pas lire `gh label list`, les environnements, `allow_auto_merge`, les secrets ni les réglages Actions (garde Bash et règles deny). Ces refus confirment que le verrou tient ; les faits correspondants sont consignés « déclarés par l'humain ».
- **Règle `gh api*merge*` large.** Elle refuse aussi une lecture comme `gh api repos/sebc-dev/prosperity --jq .allow_auto_merge`. Sans conséquence de sécurité ; cela rend certaines vérifications de réglages impossibles pour l'agent.
- **Échecs de nightly antérieurs à la fusion** (2026-11-22 et 2026-11-23, événement `schedule`) : non analysés, à ignorer si ce sont les anciens runs du projet précédent.
- **Faux positif connu :** les commits intitulés `(01-14)` datés du 2026-03-29 appartiennent à l'ancien projet Java archivé.

## Points ouverts (à suivre)

| Échéance | Action |
|---|---|
| **2026-11-26** | Retirer la surcharge pnpm `'minimatch@>=11': 10.2.6` de `pnpm-workspace.yaml` (PR avec `deps-approved`) |
| **après 2026-12-10** | Relever pnpm à >= 12.21 et aligner `CLAUDE.md` et la section stack (aujourd'hui 12.21.0 alors que l'outillage est en 12.18.0) |
| Revue | Confirmer la couverture de l'outil Write par les règles `Edit(...)` : 66 règles `Edit`, aucune `Write(...)`, refus (b) déclaré sans message exact |
| Optionnel | Restreindre les méthodes de fusion autorisées du ruleset à « merge commit » (aujourd'hui `merge squash rebase`) |
| Ménage | PR de l'ancien projet encore ouvertes : Dependabot #289, #291, #292, #293 et #288 ; réglage par défaut de CodeQL (langages) à nettoyer |
| Constat | `lint-security` : ~198 issues, advisory, sans effet sur le verdict |
| Constat | Un volet utilisateur GSD `sonar-review` (étape ship:pre) existe hors du dépôt |
| Constat | Risque accepté de D-15 : le jeton partagé permettrait à un agent qui contournerait deny et garde de poser un label (voir `docs/quality-gate.md`, « Limites connues ») |

## Known Stubs

Aucun.

## Threat Flags

Aucun nouvel élément de surface hors du `<threat_model>`. Mitigations jouées : T-01-37 (`lock.test.ts`, refus Edit), T-01-38 (garde `gh`), T-01-39 (`workflow-rewrite` : `gate` vert, `quality` rouge, #306), T-01-40 (statut publié par `prosperity-gate[bot]`, source du ruleset = l'application), T-01-49 (fusion bloquée sans statut vert), T-01-50 (réglages et secrets non lisibles par l'agent), T-01-53 (amorçage de #300 sous ruleset transitoire et relecture D-01), T-01-63 (allowlist lue dans la base, #304), T-01-SC (aucun paquet ajouté ; `deps-too-recent` refusé).

## User Setup Required

Fait par l'humain : labels, application `prosperity-gate`, environnement `gate-verdict`, auto-fusion, durcissements Actions, timer Sonar. Aucun reste, hors les suivis datés ci-dessus.

## Next Phase Readiness

- La gate est verrouillée et son verdict est rendu hors de portée de la PR : la phase 1 peut se clore et la phase 2 démarrer sous `pnpm quality`.
- Deux épinglages temporaires à lever (minimatch le 2026-11-26, pnpm après le 2026-12-10).
- L'orchestrateur tient `STATE.md`, `ROADMAP.md` et la case des exigences QUAL-01, QUAL-06, QUAL-07 et QUAL-09 de `REQUIREMENTS.md` ; ce plan n'y touche pas.

## Self-Check: PASSED

- Fichiers présents dans l'arbre : `.claude/settings.json`, `.github/CODEOWNERS`, `.github/workflows/quality.yml`, `lefthook.yml`, `quality/lock.test.ts`.
- Commits ancêtres de HEAD : `739f6a6`, `467a4a1`, `fa41456`, `e241321` ; `git rev-list --count 2e70009..HEAD` = 4. Le commit `84064fe` (PR #301) est sur `origin/main`, hors de cette branche.
- Contrôles rejoués par l'agent : `quality/lock.test.ts` 23 tests passés ; `pnpm quality --only workflow-lint,workflow-audit,lint,format,typecheck` verdict `pass` ; ruleset 17645569 et règles de `main` conformes ; #300 `MERGED` ; #302 à #306 `CLOSED`.
- Non vérifiable par l'agent (verrou) et donc déclaré : labels du dépôt, environnement `gate-verdict`, auto-fusion, durcissements Actions, état du timer Sonar, refus (b) à (g).
