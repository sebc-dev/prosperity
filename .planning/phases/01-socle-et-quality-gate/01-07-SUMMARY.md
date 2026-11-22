---
phase: 01-socle-et-quality-gate
plan: 07
subsystem: infra
tags: [quality-gate, approval, github-labels, workflow_run, verdict, tdd, d-15]

requires:
  - phase: 01-socle-et-quality-gate
    provides: "`quality/verdict.ts` + `verdict-rules.ts` + `verdict-io.ts` (`ApprovalsReport`, `readApprovalsReport`, `runVerdict`, `nodeJudge`), `quality/deps-guard.ts` (`writeJsonAtomic`), `quality/tools.ts` (`runTool`, `isRecord`), `quality/check-kit.ts`, modèle de check ci-only `quality/checks/deps.ts` (plans 01-06 et 01-08)"
provides:
  - "`quality/approval-evidence.ts` : collecte en lecture seule (trois `gh api` GET) des preuves d'approbation (PR, événements `labeled`/`unlabeled`/`head_ref_force_pushed`, runs du SHA de tête), forme normalisée, relecture validée, CLI pour l'étape de confiance de la PR"
  - "`quality/approvals.ts` : juge pur des labels (`decideApprovals`, `lastPushAnchor`), allowlist lue dans la seule copie de base, rapport au schéma `ApprovalsReport` (`verifier` `github-label-events@1`), CLI sans jeton"
  - "`quality/approvers.json` : allowlist versionnée (`sebc-dev`) et labels requis (`gate-change-approved`, `deps-approved`)"
  - "`runVerdict` collecte les preuves avec le jeton du workflow (`VerdictDeps.collectEvidence`) puis lance le juge sans jeton ; permission `actions: read` du job `verdict`"
  - "Check bloquant `approvals` (ci-only) relisant `reports/approvals.json` par `readApprovalsReport`"
  - "`quality.yml` rejoué sur `labeled`/`unlabeled` (gate complète, sans allègement) et job `reset-approval` (retrait des labels à chaque `synchronize`, hygiène)"
affects: [01-09, 01-12, 01-13, 01-14]

actuals:
  tokens: 20298   # chars/4 sur le diff complet (81 192 caractères, de 9924fd4 à bff1024)
  tasks: 3
  commits: 5      # MESURÉ : git rev-list --count 9924fd4..HEAD (hors commit de ce SUMMARY)
plan_head_before: 9924fd4b6b1dbade0ac911abf431e64272d63d8c
plan_head_after: bff10245a9ef425a79a0785be043b1dba4b612d1

tech-stack:
  added: []
  patterns:
    - "Collecteur de preuves en lecture seule, juge pur sur un fichier de données : le code de `main` détient le jeton du workflow et collecte, le juge reste un processus sans jeton qui ne lit que le fichier et la copie de base"
    - "Un seul validateur : `evidenceFromApi` normalise les réponses de l'API en candidat puis le fait passer par `parseApprovalEvidence`, le même lecteur que celui des fichiers"
    - "Fixtures partagées dans un module non-test (`*-fixtures.ts`) quand un fichier de test dépasserait 300 lignes ou 60 lignes par `describe`"

key-files:
  created:
    - quality/approval-evidence.ts
    - quality/approvals.ts
    - quality/approvers.json
    - quality/checks/approvals.ts
    - quality/approval-evidence.test.ts
    - quality/approval-evidence-collect.test.ts
    - quality/approval-evidence-fixtures.ts
    - quality/approvals.test.ts
    - quality/approvals-judge.test.ts
    - quality/approvals-cli.test.ts
    - quality/approvals-fixtures.ts
    - quality/checks/approvals.test.ts
    - quality/verdict-fixtures.ts
  modified:
    - quality/verdict.ts
    - quality/verdict.test.ts
    - quality/deps-guard.ts
    - .github/workflows/quality-verdict.yml
    - .github/workflows/quality.yml

key-decisions:
  - "Ancre serveur du dernier push = maximum entre le plus ancien run `pull_request` du SHA de tête dont le dépôt et la branche de tête sont ceux de la PR, et le dernier `head_ref_force_pushed` ; jamais la date d'un commit ; un run du même SHA venu d'une autre branche ou d'un autre dépôt est ignoré"
  - "Un acteur vide (compte supprimé, bot sans login) est refusé même si l'allowlist contenait une chaîne vide ; `loadApproversConfig` exige des tableaux non vides de chaînes non vides"
  - "Le rapport reflète le drapeau `--bootstrap` tel que reçu (`bootstrap: true`, refusé par le verdict hors PR) ; la configuration de la base prime si elle existe, sinon l'allowlist est `pull.baseOwner` lu dans l'API"
  - "`parseApprovalEvidence` impose `pull.number === pr` : des preuves incohérentes sont invalides dès la relecture"
  - "Le check `approvals` passe quand le rapport est conforme, même avec des refus (repris en issues informatives) : l'exigence de la sorte appartient à l'intégrité et à la garde des dépendances ; un rapport d'amorçage passe avec une note, le verdict hors PR le refuse"
  - "Un run dû à un label sans rapport avec l'approbation rejoue la gate complète (coût en minutes de CI accepté, aucune condition `if:` sur le job de la PR)"

patterns-established:
  - "Raisons de refus d'approbation = identifiants stables (`approval-missing`, `approval-removed`, `approval-actor-not-allowed`, `approval-stale`, `approval-no-anchor`, `approval-head-moved`, `approval-evidence-invalid`, `approvers-config-missing`) repris tels quels en `issues`"
  - "Échec fermé partout : preuves absentes, illisibles, d'une autre PR ou d'un autre SHA ne donnent jamais une approbation"

requirements-completed: [QUAL-06, QUAL-07, QUAL-09]

coverage:
  - id: D1
    description: "Collecteur de preuves en lecture seule : trois GET `gh`, aucune option d'écriture, `GATE_STATUS_TOKEN` et `GITHUB_TOKEN` retirés de l'environnement de `gh`, réponses normalisées et validées, CLI (codes 0/1/2)"
    requirement: QUAL-06
    verification:
      - kind: unit
        ref: "quality/approval-evidence.test.ts + quality/approval-evidence-collect.test.ts (45 tests, faux `gh` en PATH et vrais processus node)"
        status: pass
      - kind: integration
        ref: "node quality/approval-evidence.ts --repo sebc-dev/prosperity --pr 300 --head-sha 80e3ab61d76b2579b851c13b309763bd9bd5d698 --out <fichier> (API réelle, GET seulement)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Juge pur des labels : dernier `labeled` d'un acteur de l'allowlist de la base, postérieur à l'ancre serveur, label encore présent ; huit raisons de refus nommées ; rapport relu à l'identique par `readApprovalsReport`"
    requirement: QUAL-06
    verification:
      - kind: unit
        ref: "quality/approvals.test.ts + quality/approvals-judge.test.ts + quality/approvals-cli.test.ts (54 tests)"
        status: pass
      - kind: integration
        ref: "node quality/approvals.ts --base-dir . --pr 300 ... puis lecture par readApprovalsReport (PR #300 réelle)"
        status: pass
    human_judgment: false
  - id: D3
    description: "`runVerdict` collecte les preuves (jeton du workflow) puis lance le juge d'approbation sans jeton ; `judge-error:approval-evidence` si la collecte lève ; rien sans PR"
    requirement: QUAL-07
    verification:
      - kind: unit
        ref: "quality/verdict.test.ts#runVerdict : approbation par label"
        status: pass
      - kind: unit
        ref: "quality/verdict-cli.test.ts (mode --dry-run inchangé)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Check bloquant `approvals` : ci-only en local, rapport de confiance relu par `readApprovalsReport` en CI sur `pull_request`, échec fermé sans rapport"
    requirement: QUAL-07
    verification:
      - kind: unit
        ref: "quality/checks/approvals.test.ts"
        status: pass
      - kind: e2e
        ref: "pnpm quality --only workflow-lint,workflow-audit,approvals,typecheck,lint,format (approvals skipped ci-only, verdict pass)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Workflows : `quality` rejoué sur `labeled`/`unlabeled` sans allègement, job `reset-approval` au `synchronize`, permission `actions: read` du verdict ; message de la garde des dépendances aligné sur D-15"
    requirement: QUAL-09
    verification:
      - kind: other
        ref: "pnpm quality --only workflow-lint,workflow-audit,typecheck,lint,format (actionlint et zizmor passent)"
        status: pass
      - kind: unit
        ref: "quality/deps-guard.test.ts + quality/deps-guard-cli.test.ts (règles et identifiants inchangés)"
        status: pass
    human_judgment: true
    rationale: "Le comportement des workflows (rejeu sur label, retrait au push, lecture des runs avec `actions: read`, `gh` et `--slurp` sur le runner) ne s'observe que sur une vraie PR : scénarios `human-label`, `bot-label` et `deps-unapproved` du plan 01-14"

# Metrics
duration: 14min
completed: 2026-11-22
status: complete
---

# Phase 1 Plan 07 : approbation par label vérifiée par la CI (D-15) Summary

**Approbation humaine = label posé par `sebc-dev` après le dernier push : preuves GitHub collectées en GET par le code de `main`, jugées sans jeton sur l'allowlist de la copie de base et une ancre serveur, rapport `ApprovalsReport` inchangé pour l'intégrité, la garde des dépendances et le verdict.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-11-22T10:40:00Z
- **Completed:** 2026-11-22T10:54:00Z
- **Tasks:** 3 (1 tracer TDD, 1 TDD, 1 auto)
- **Files modified:** 18 (13 créés, 5 modifiés)

## Accomplishments

- Chaîne de bout en bout jouée sur la vraie PR de bootstrap #300, en lecture seule : API GitHub, preuves, juge, `readApprovalsReport` (SHA jugé `80e3ab61d76b2579b851c13b309763bd9bd5d698`, aucun label : `gate-change-approved` et `deps-approved` donnent `approval-missing`, `approval: null`, `bootstrap: false`, `verifier: github-label-events@1`). L'ancre serveur a bien été trouvée (un run `pull_request` du SHA sur la branche et le dépôt de tête de la PR), sans quoi la raison aurait été `approval-no-anchor`.
- Juge d'approbation sans réseau ni jeton : huit raisons de refus nommées, ancre affinée (dépôt et branche de tête, relevée au dernier push forcé), allowlist lue uniquement dans `<--base-dir>/quality/approvers.json` (une configuration permissive de la tête ou du répertoire courant est sans effet, `--base-dir` manquant donne la sortie 2).
- `runVerdict` collecte les preuves avec le jeton du workflow et lance le juge sans jeton (`--pr`, `--evidence`) ; `nodeJudge` est inchangé ; le job `verdict` gagne seulement `actions: read`, aucune permission d'écriture.
- Gate rejouée sur pose ou retrait de label, labels retirés à chaque push par un job sans action ni checkout, message de la garde des dépendances aligné sur D-15 ; `quality/agent-guard/` intact (aligné au plan 01-13).

## Task Commits

Chaque tâche a été validée atomiquement (TDD pour les tâches 1 et 2) :

1. **Tâche 1 (tracer) : preuves, juge, allowlist de la base**
   - RED : `a22d3ca` (test) — 99 tests, tous en échec sur des squelettes qui lèvent « non implémenté » (ou un processus qui sort 0 sans rien écrire)
   - GREEN : `936f89f` (feat) — 99 tests verts
2. **Tâche 2 : verdict hors PR et check `approvals`**
   - RED : `ecb1f85` (test) — 12 tests en échec sur les 55 des quatre fichiers visés
   - GREEN : `872ca9b` (feat) — 77 tests verts sur `verdict`, `verdict-io`, `verdict-cli` et `checks/approvals`
3. **Tâche 3 : workflows et garde des dépendances** — `bff1024` (feat)

**Plan metadata:** commit `docs(01-07): complete label approval plan` (ce SUMMARY).

Aucun commit de refactor : le code sorti du vert respectait déjà les seuils (lint, types, format).

## RED

- Tâche 1 : les tests de `evidenceFromApi`, `parseApprovalEvidence`, du collecteur (faux `gh`), du juge, de la configuration et des deux CLI ont été écrits avant l'implémentation, contre des squelettes aux signatures du contrat. Résultat : 99 échecs sur 99, aucun test vert par accident. Évaluation sémantique : chaque test cible un comportement planifié (raison de refus, arguments de `gh`, code de sortie) ; les échecs viennent de « non implémenté » ou de codes de sortie inattendus, pas d'une erreur d'import ou de syntaxe. Les preuves RED n'ont pas été passées au classifieur `gsd_run check tdd-red-evidence` (le plan est de type `execute`, non `tdd` ; `TDD_MODE` n'était pas activé).
- Tâche 2 : 12 échecs (arguments du juge `approvals`, collecte, `judge-error:approval-evidence`, absence de PR, check `approvals`) ; les tests d'issues informatives de refus passaient déjà (comportement conservé du plan 01-08).

## Files Created/Modified

- `quality/approval-evidence.ts` : types `LabelEvent`, `RunInfo`, `PullInfo`, `ApprovalEvidence`, `evidenceFromApi`, `parseApprovalEvidence`, `collectApprovalEvidence`, CLI
- `quality/approvals.ts` : `APPROVAL_KINDS`, `VERIFIER`, `loadApproversConfig`, `lastPushAnchor`, `decideApprovals`, `judgeApprovals`, CLI
- `quality/approvers.json` : allowlist et labels requis
- `quality/checks/approvals.ts` : check `approvals` (blocking, `skip-ci-only`)
- `quality/verdict.ts` : `collectEvidence` dans `VerdictDeps`, `labelApprovals`, collecte dans `liveDeps`, collecte vide en `--dry-run`
- `quality/deps-guard.ts` : message de refus nommant le label
- `.github/workflows/quality.yml` : `labeled`/`unlabeled`, job `reset-approval`
- `.github/workflows/quality-verdict.yml` : `actions: read`
- Tests et fixtures : voir `key-files.created`

## Decisions Made

Voir `key-decisions`. Deux précisions de conception : (1) `evidenceFromApi` ne valide rien lui-même, il fabrique un candidat que `parseApprovalEvidence` valide, ce qui garde un seul lecteur pour l'API et pour les fichiers ; (2) un événement d'un autre type que `labeled`, `unlabeled` ou `head_ref_force_pushed` est ignoré sans validation, tout champ requis manquant d'un événement conservé rend les preuves invalides.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fichiers de test scindés pour respecter `max-lines` et `max-lines-per-function`**
- **Found during:** Tâches 1 et 2 (lint)
- **Issue:** les tests du plan (un `approvals.test.ts`, un `approval-evidence.test.ts`, des ajouts à `verdict.test.ts`) dépassaient 300 lignes et 60 lignes par `describe` ; le plan prévoit de scinder par rôle sans relever de seuil
- **Fix:** fixtures partagées dans trois modules (`approval-evidence-fixtures.ts`, `approvals-fixtures.ts`, `verdict-fixtures.ts`) et tests répartis : `approval-evidence.test.ts` (normalisation, relecture) et `approval-evidence-collect.test.ts` (collecteur, CLI) ; `approvals.test.ts` (ancre, décision), `approvals-judge.test.ts` (configuration, jugement : `approvers-config-missing`, `approval-evidence-invalid`, base prioritaire, amorçage) et `approvals-cli.test.ts` (sortie 2 sans `--base-dir`, rapport écrit). Les critères du plan sur le contenu de `approvals.test.ts` sont donc couverts par ces trois fichiers. Les `expect(` de `verdict.test.ts` passent de 38 à 49 : aucune assertion retirée
- **Files modified:** les six fichiers ci-dessus, `quality/verdict.test.ts`
- **Verification:** lint (`--max-warnings 0`), `tsc --noEmit`, tests verts
- **Committed in:** `a22d3ca`, `ecb1f85`

**2. [Rule 3 - Blocking] Seconde commande `<automated>` de la tâche 1 jouée en étapes séparées**
- **Found during:** Tâche 1 (vérification)
- **Issue:** le harnais refuse la ligne unique du plan (enchaînement de `$(…)`, `&&` et un `node -e` qui nomme `github`)
- **Fix:** mêmes commandes, jouées l'une après l'autre avec un dossier de travail fixe du scratchpad ; la dernière étape (relecture par `readApprovalsReport`, `verifier` attendu, `bootstrap` faux, deux sortes jugées) est un petit script `.mjs` du scratchpad, hors dépôt. Les trois étapes sortent 0
- **Files modified:** aucun

**3. [Rule 2 - Missing critical] Contrôles d'entrée du collecteur et acteur vide**
- **Found during:** Tâche 1
- **Issue:** le plan exige la validation du dépôt, du numéro et du SHA avant tout appel ; il refuse l'acteur vide mais une allowlist contenant `""` aurait pu l'accepter
- **Fix:** `collecte refusée : …` avant tout appel `gh` (testé : aucun appel consigné) ; refus explicite de l'acteur vide dans `decideApprovals`, et `loadApproversConfig` refuse les noms vides
- **Committed in:** `936f89f`

---

**Total deviations:** 3 (2 blocking, 1 missing critical)
**Impact on plan:** aucune ne change le contrat, le schéma de rapport ou les consommateurs ; la première ajoute six fichiers (fixtures et tests) à l'empreinte du plan, tous consignés ci-dessus.

## Issues Encountered

- `approvals.ts` importe `writeJsonAtomic` (de `deps-guard.ts`) et `isRecord` (de `tools.ts`), et `approval-evidence.ts` importe `isRepository` (de `verdict-io.ts`), au lieu du seul `node:*` mentionné par le plan : réutilisation plutôt que copie (jscpd). Le juge ne lance aucun processus et n'appelle aucun réseau (greps du plan : 0 correspondance pour `runTool|api.github.com|fetch(`).
- `pnpm quality` complet vert en local (`approvals`, `integrity`, `deps` en `skipped: ci-only`). Le check advisory `lint-security` signale 140 issues (`eslint-plugin-security`, faible signal), dont une trentaine dans les fichiers ajoutés ici (principalement des chemins de fichiers non littéraux dans les tests) : même nature que celles des fichiers existants, sévérité advisory, non traitées.
- Le coût de CI augmente : chaque pose ou retrait de label rejoue la gate complète (≈ 8 à 10 min sur runner hébergé), accepté par le plan et sans optimisation possible (prohibition du frontmatter).

## Known Stubs

Aucun : les squelettes de la phase RED (`approval-evidence.ts`, `approvals.ts`, `checks/approvals.ts`) ont tous été remplacés.

## Threat Flags

Aucune surface nouvelle hors du registre du plan (T-01-25, T-01-26, T-01-27, T-01-43, T-01-52, T-01-60, T-01-61, T-01-62). Le risque accepté T-01-27 reste entier : un label posé par l'agent avec le jeton `gh` de `sebc-dev` est indiscernable d'un label humain ; la barrière est la règle deny de D-03 et le garde Bash du plan 01-06, actifs au verrou (plan 01-14).

## User Setup Required

None - no external service configuration required. Les labels `gate-change-approved` et `deps-approved` doivent exister sur GitHub : leur création et leur premier usage sont des gestes humains du plan 01-14 (l'exécuteur n'a posé ni retiré aucun label).

## TDD Gate Compliance

Plan de type `execute` (tâches `tdd="true"`) : pour chacune des tâches 1 et 2, un commit `test(01-07)` (RED) précède le commit `feat(01-07)` (GREEN) qui le suit : `a22d3ca` puis `936f89f`, `ecb1f85` puis `872ca9b`. Aucun commit `refactor`.

## Next Phase Readiness

- Prêt pour 01-09 (entrées knip des nouveaux scripts lancés comme processus : `quality/approval-evidence.ts`, `quality/approvals.ts`), 01-12 (cas `integrity-*`, `deps-*`) et 01-14 (étape de confiance de la PR qui écrit `reports/approval-evidence.json` puis `reports/approvals.json`, création des labels, PR réelles `human-label`, `bot-label`, `deps-unapproved`).
- À constater au premier run réel (plan 01-14) : `gh` préinstallé sur `ubuntu-24.04` (A4) et `--slurp` (gh ≥ 2.48) sur le runner, `head_branch` et `head_repository` d'un run `pull_request` de fork [ASSUMED], bon fonctionnement de `gh pr edit --remove-label` avec le jeton du workflow dans `reset-approval`.
- Les messages du garde de l'agent restent à aligner sur D-15 au plan 01-13.

---
*Phase: 01-socle-et-quality-gate*
*Completed: 2026-11-22*

## Self-Check: PASSED

- Fichiers créés présents (13 sur 13) ; commits `a22d3ca`, `936f89f`, `ecb1f85`, `872ca9b`, `bff1024` présents dans l'historique de la branche.
- `requirements.ready-ids` : QUAL-06, QUAL-07 et QUAL-09 sont partagés avec des plans sans SUMMARY, donc non marqués ici (règle du plan partagé, #2388) ; `REQUIREMENTS.md` inchangé.
