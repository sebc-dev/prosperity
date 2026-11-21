---
phase: 01-socle-et-quality-gate
plan: 01
subsystem: infra
tags: [quality-gate, mise, pnpm, lefthook, github-actions, actionlint]

requires:
  - phase: none
    provides: premier plan de la phase 1
provides:
  - "`pnpm quality` : point d'entrée unique de la gate (profils `push`/`full`, `--only`, `--report`, `--base`)"
  - "Contrat `CheckDefinition`/`CheckResult`/`GateReport` et rapport atomique `reports/gate.json`"
  - "Premier check réel `workflow-lint` (actionlint 1.7.12), modèle des checks suivants"
  - "Outillage épinglé et verrouillé : `mise.toml`, `mise.lock`, `.mise/locks/pipx-semgrep/1.186.0`"
  - "Politique supply-chain pnpm (`pnpm-workspace.yaml`)"
  - "Pré-push lefthook `quality-push` et workflow CI `quality` (job `quality`, artefact `gate`)"
  - "PR brouillon de bootstrap #300 (`sebc-dev/jiaolong` vers `main`), historique de l'ancien `main` rattaché"
affects: [01-02, 01-03, 01-04, 01-05, 01-06, 01-07, 01-08, 01-09, 01-10, 01-11, 01-12, 01-13, 01-14]

actuals:
  tokens: 5300   # chars/4 sur le diff de la tâche 1 hors lockfiles (21 087 caractères) ; tâches 2 et 3 sans fichier
  tasks: 3
  commits: 2     # MESURÉ : git rev-list --first-parent --count c0a74f4..80e3ab6 (voir note sous Performance)
plan_head_before: c0a74f4d9b684b81d1a2b2977a29c3a9a60bc822
plan_head_after: 80e3ab61d76b2579b851c13b309763bd9bd5d698

tech-stack:
  added: [mise 2026.11.12, pnpm 12.21.0, typescript 6.0.3, lefthook 2.2.2, actionlint 1.7.12]
  patterns:
    - "Un fichier par check dans `quality/checks/*.ts`, export `check`, aucun registre central"
    - "Verdict tiré de la sortie structurée de l'outil, jamais du seul code de sortie"
    - "spawn sans shell ; versions d'outils lues dans `mise.toml` et vérifiées à l'exécution"

key-files:
  created:
    - mise.toml
    - mise.lock
    - .mise/locks/pipx-semgrep/1.186.0/pyproject.toml
    - .mise/locks/pipx-semgrep/1.186.0/uv.lock
    - package.json
    - pnpm-workspace.yaml
    - pnpm-lock.yaml
    - quality/gate-report.ts
    - quality/tools.ts
    - quality/run.ts
    - quality/checks/workflow-lint.ts
    - lefthook.yml
    - .github/workflows/quality.yml
  modified:
    - .gitignore

key-decisions:
  - "Rattachement d'historique : `merge-ours` (décision humaine de la tâche 2). `git merge -s ours --allow-unrelated-histories origin/main` ; arbre inchangé vérifié par `git diff --quiet HEAD^1 HEAD`"
  - "Aucun contournement du ruleset : poussée en fast-forward, sans force-push, `main` non modifié"
  - "Le job de la PR garde le nom `quality` jusqu'au plan 01-14, où il devient `gate` et où `quality` devient le statut du verdict de confiance"

requirements-completed: [QUAL-01]

coverage:
  - id: D1
    description: "`mise exec -- pnpm quality` exécute `workflow-lint` (actionlint 1.7.12) et écrit `reports/gate.json` avec `verdict: pass`"
    requirement: QUAL-01
    verification:
      - kind: other
        ref: "mise exec -- pnpm quality && lecture de reports/gate.json (verdict pass, profil full, workflow-lint passed, version 1.7.12)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Un workflow invalide fait sortir la gate en code 1 avec le check `failed`"
    requirement: QUAL-01
    verification:
      - kind: other
        ref: "pnpm quality --only workflow-lint sur un workflow à `uses: actions/checkout` sans ref (code 1, status failed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Le pré-push lefthook joue `pnpm quality --profile push` et écrit un rapport `profile: push`"
    requirement: QUAL-01
    verification:
      - kind: other
        ref: "mise exec -- lefthook run pre-push ; git push réel : `quality-push` exécuté et réussi"
        status: pass
    human_judgment: false
  - id: D4
    description: "Sur la PR brouillon #300, le runner `ubuntu-24.04` rapporte un check nommé exactement `quality` en succès, seul workflow exécuté"
    requirement: QUAL-01
    verification:
      - kind: other
        ref: "gh pr checks 300 --json name,bucket (quality = pass) ; gh run list --branch sebc-dev/jiaolong (workflowName = quality uniquement)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Installation des outils en mode verrouillé sur le runner (`install_args: \"--locked\"`) depuis `mise.lock`"
    requirement: QUAL-01
    verification:
      - kind: other
        ref: "journal du run 44940662378 : `Running mise install --locked`, semgrep installé depuis les dépendances Python gelées"
        status: pass
    human_judgment: false

duration: 10min (continuation : tâche 3 ; tâche 1 exécutée dans un worktree précédent)
completed: 2026-11-21
status: complete
---

# Phase 1 Plan 01 : Squelette de la gate (tracer) Summary

**`pnpm quality` de bout en bout : outils mise verrouillés, check `workflow-lint` (actionlint 1.7.12), rapport atomique `reports/gate.json`, pré-push lefthook et job CI `quality` vert sur `ubuntu-24.04`, prouvé sur la PR brouillon de bootstrap #300 après rattachement de l'ancien historique de `main` par `merge -s ours`.**

## Performance

- **Duration :** 10 min pour cette continuation (tâche 3) ; la tâche 1 a été exécutée par l'agent précédent
- **Tasks :** 3 (1 tracer, 1 décision humaine, 1 preuve CI)
- **Files :** 14 fichiers touchés par la tâche 1 (13 créés, `.gitignore` modifié) ; tâches 2 et 3 sans fichier du dépôt
- **Commits (mesurés) :** `git rev-list --first-parent --count c0a74f4..80e3ab6` donne 2 (la fusion de l'orchestrateur `69d5645` et la fusion de rattachement `80e3ab6`) ; le commit de code de la tâche 1 `94e3249` y entre par le second parent. Un `rev-list` sans `--first-parent` est gonflé par l'historique de l'ancien `main` désormais ancêtre.

## Accomplishments

- Gate de bout en bout : `mise.toml` (11 outils épinglés) et `mise.lock` ; `pnpm quality` (profils, découverte des checks, pool borné, rapport trié) ; contrat `CheckDefinition`/`CheckResult`/`GateReport` et `computeVerdict` pur (aucun saut silencieux en CI) ; `reports/gate.json` écrit par fichier temporaire puis renommage.
- Check `workflow-lint` : version vérifiée contre `mise.toml` (`tool-version-mismatch`), verdict tiré du JSON d'actionlint, `tool-error` pour tout code hors 0 et 1.
- Pré-push lefthook `quality-push` ; workflow `quality.yml` épinglé par SHA, `permissions: {}`, déclencheur `pull_request`, sans filtre de chemins.
- Tâche 2 (décision humaine) : `merge-ours`. Tâche 3 : fusion `-s ours` de `origin/main` (3c1c955), arbre inchangé, poussée en fast-forward `b8c59bb..80e3ab6` (pré-push joué), PR brouillon #300 ouverte, `quality` en `pass`.

## Task Commits

1. **Tâche 1 (tracer) : gate de bout en bout** - `94e3249` (feat)
2. **Tâche 2 : décision de rattachement** - aucune modification de dépôt ; réponse `merge-ours`
3. **Tâche 3 : rattachement de l'historique de `main`** - `80e3ab6` (chore, commit de fusion à arbre inchangé)

Le commit `69d5645` est la fusion du worktree de la tâche 1 faite par l'orchestrateur.

## Constats sur les hypothèses

- **A5 (pnpm de mise contre `packageManager`) : confirmée.** pnpm 12.21.0 fourni par mise et `packageManager: "pnpm@12.21.0"` ne se heurtent pas. En local comme sur le runner, `pnpm install --frozen-lockfile` n'émet aucun avertissement (`Lockfile passes supply-chain policies`, `Done in 614ms using pnpm v12.21.0`).
- **A6 (nom du check) : confirmée.** Le job `name: quality` rapporte un check nommé exactement `quality`, `bucket: pass`, 21 s (run 44940662378).
- **Un seul workflow exécuté :** `gh run list --branch sebc-dev/jiaolong` ne renvoie que `quality` ; aucun workflow de l'ancien `main` ne tourne. Voir plus bas les contrôles GitHub hors workflow.
- **Mode verrouillé en CI :** le journal montre `Detected a mise lock file, running mise install --locked`, et semgrep installé par `installing frozen Python dependencies` avec CPython 3.12.3 système.
- **mise 2026.11.12** installé depuis la release GitHub, SHA-256 vérifié, sans script distant.
- **`lefthook install`** écrit le hook dans le dossier git commun, partagé par tous les worktrees. Sans `lefthook.yml`, `lefthook run pre-push` affiche « No config files… » et sort en 0 : aucun isolement par `core.hooksPath` n'a été nécessaire.
- **`mise lock --platform linux-x64`** a produit `.mise/locks/pipx-semgrep/1.186.0/{pyproject.toml,uv.lock}`.

## Deviations from Plan

None - plan executed exactly as written.

Adaptations d'environnement, sans écart de contenu : la tâche 3 a été jouée dans un worktree d'agent (`worktree-agent-*`) et non sur `sebc-dev/jiaolong` ; la poussée s'est faite par `git push origin HEAD:refs/heads/sebc-dev/jiaolong` (fast-forward vérifié par `git merge-base --is-ancestor b8c59bb HEAD`), puis l'orchestrateur rapatrie la branche localement. `pnpm install --frozen-lockfile` a été relancé dans le worktree faute de `node_modules`.

## Auth Gates

Aucune.

## Issues Encountered

Aucun blocage. Observations à traiter par les plans suivants, hors périmètre de celui-ci :

1. **`mise install --locked` en local échoue pour `pipx:semgrep`** dans un worktree neuf (« Python graph installs require an installed interpreter ; add python to your config »), alors que la même commande réussit sur le runner (CPython 3.12.3 système) et que `mise install` sans `--locked` constate l'outil déjà installé. À reconfirmer lors du premier poste neuf ou d'un cache vide ; si cela se reproduit, envisager un pin `python` dans `mise.toml`.
2. **`actionlint is deprecated`** : mise 2026.11.12 avertit que `jactionlint` est le fork maintenu d'actionlint. Avertissement non bloquant ; le pin `actionlint = "1.7.12"` est celui du CLAUDE.md. Décision de migration à prendre dans un plan ultérieur.
3. **Contrôles GitHub hors workflow sur la PR #300** : CodeQL (installation par défaut du dépôt) et Socket Security s'exécutent sur la PR ; `Analyze (java-kotlin)` et `Analyze (python)` sont en échec (langages de l'ancien projet) et ne proviennent d'aucun fichier de workflow de la branche. Le check `ci-required` de l'ancien ruleset n'apparaît pas et laisse la PR `BLOCKED` : attendu jusqu'au plan 01-14 (Q3).
4. **`minimum_release_age` ignoré par `jdx/mise-action`** quand une version explicite de mise est fournie (message du journal) : sans effet ici, `version: 2026.11.12` étant épinglée.

## Known Stubs

None.

## Threat Flags

Aucun nouveau point de surface hors du `threat_model` du plan.

## Next Phase Readiness

Le squelette est prouvé du poste à la CI. Les plans 01-13 et 01-14 réutilisent le numéro de PR **#300** (https://github.com/sebc-dev/prosperity/pull/300, brouillon, base `main`, tête `sebc-dev/jiaolong`). La PR est `BLOCKED` par l'ancien ruleset, ce qui est attendu. Les plans suivants branchent leurs checks sous `quality/checks/`.

## Self-Check: PASSED

- Fichiers : `quality/run.ts`, `quality/tools.ts`, `quality/gate-report.ts`, `quality/checks/workflow-lint.ts`, `mise.toml`, `mise.lock`, `lefthook.yml`, `.github/workflows/quality.yml` présents sur disque.
- Commits : `94e3249` et `80e3ab6` sont ancêtres de HEAD ; `git merge-base HEAD origin/main` renvoie `3c1c95519e5b21bb8575e45ac12859110249004c` ; `git diff --quiet HEAD^1 HEAD` sur la fusion réussit.
- CI : `gh pr checks 300` liste `quality` avec `bucket: pass` ; `gh run list --branch sebc-dev/jiaolong` ne renvoie que `quality`.
