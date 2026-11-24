---
phase: 01-socle-et-quality-gate
plan: 08
subsystem: infra
tags: [quality-gate, supply-chain, deps-guard, workflow_run, github-app, zizmor, verdict]

requires:
  - phase: 01-socle-et-quality-gate
    provides: "contrat `CheckDefinition`/`CheckResult`, `quality/check-kit.ts`, `quality/tools.ts` (`runTool`, `isRecord`), `quality/thresholds.json` (`supplyChain.packageMinAgeDays`), `quality/run.ts` (plans 01-01 à 01-04)"
provides:
  - "`quality/deps-guard.ts` : `diffDependencies`, `evaluateDependencies`, CLI à échec fermé (sorte `deps-approved` lue dans `reports/approvals.json`, existence et âge de création sur npm)"
  - "Check bloquant `deps` (`quality/checks/deps.ts`) : ci-only, lit `reports/deps.json` en CI sur `pull_request`, auto-test local avec `GATE_BASE_DIR`"
  - "`quality/verdict.ts` + `verdict-rules.ts` + `verdict-io.ts` : `parseTarget`, `decideVerdict`, `statusPayload`, `runVerdict`, lecteur validé d'`ApprovalsReport`, CLI avec `--dry-run`"
  - "`.github/workflows/quality-verdict.yml` : juge hors PR (`workflow_run` sur `quality`, environnement `gate-verdict`, statut `quality` publié par une application GitHub dédiée)"
  - "`.github/zizmor.yml` : exception `dangerous-triggers` limitée à `quality-verdict.yml`, justifiée"
affects: [01-09, 01-12, 01-14]

actuals:
  tokens: 22470   # chars/4 sur le diff complet (89 878 caractères, hors pnpm-lock.yaml inchangé)
  tasks: 2
  commits: 5      # MESURÉ : git rev-list --count cf0b1eb~1..HEAD (hors commit de ce SUMMARY)
plan_head_before: 6bfea7a387f6adf1585504c88250c80e4616c2ed
plan_head_after: 5130c1d8467eaf219e30142c88b43fb8ee87b460

tech-stack:
  added: []
  patterns:
    - "Un juge de confiance est un script lancé depuis la copie de la branche par défaut, sans shell, `cwd` hors de la tête, sans jeton dans l'environnement ; son rapport est relu comme donnée validée, un rapport illisible ou hors schéma valant rapport absent"
    - "`import.meta.main` garde le CLI d'un module qui exporte aussi des fonctions pures : le test importe sans lancer, le workflow lance sans importer"
    - "Tests sans mock de module : juges, publication, recherche registre injectés ; git, node et un faux `gh` (script `sh` dans un PATH de test) joués en vrais processus"

key-files:
  created:
    - quality/deps-guard.ts
    - quality/deps-diff.ts
    - quality/checks/deps.ts
    - quality/verdict.ts
    - quality/verdict-rules.ts
    - quality/verdict-io.ts
    - .github/workflows/quality-verdict.yml
    - .github/zizmor.yml
    - quality/deps-guard.test.ts
    - quality/deps-guard-cli.test.ts
    - quality/checks/deps.test.ts
    - quality/verdict.test.ts
    - quality/verdict-io.test.ts
    - quality/verdict-cli.test.ts
  modified: []

key-decisions:
  - "Une seule logique de diff : `package.json` (4 sections + `pnpm.overrides`, une surcharge visant le paquet après `>` et avant `@sélecteur`) puis lockfile lu ligne à ligne ; un paquet déjà signalé en direct n'est pas redoublé par le lockfile ; un nouveau nom donne `transitive-added`, une nouvelle version d'un nom existant donne `dependency-changed`"
  - "Les deux règles du registre (`dependency-not-on-registry`, `dependency-too-young`) valent même avec `deps-approved` ; l'âge exact de 30 jours est accepté, 29 refusé ; une recherche qui lève ou une date illisible échoue fermé (`registry-lookup-failed`)"
  - "Le chemin du run déclencheur est comparé sans le suffixe `@<référence>` que GitHub peut ajouter à `workflow_run.path` : seul le fichier compte, le suffixe est posé par GitHub et non par la PR"
  - "`runVerdict` publie exactement une fois, y compris quand l'extraction de la tête ou un juge échoue (`judge-error:extract-head|approvals|integrity|deps`) ; la tête absente rend les rapports d'intégrité et de dépendances absents"
  - "Les juges lancés par le verdict reçoivent un environnement sans `GATE_STATUS_TOKEN`, `GH_TOKEN` ni `GITHUB_TOKEN` ; le jeton du workflow ne sert qu'au `git fetch` (par `GIT_CONFIG_*`, jamais en argument) et le jeton de l'application qu'à la publication"

patterns-established:
  - "Raison de refus = identifiant stable `<nom>-failed` | `missing-trusted-report:<nom>` | `judge-error:<nom>` | règle de l'outil repris dans `issues`"
  - "Un fichier de code dépassant 300 lignes se scinde par rôle (diff pur / évaluation / entrées-sorties) en gardant l'API publique par réexport"

requirements-completed: [QUAL-09, QUAL-07]

coverage:
  - id: D1
    description: "Garde des dépendances : diff package.json/lockfile, `deps-approved` exigée pour tout ajout ou changement, existence et âge ≥ 30 jours sur npm, échec fermé sur rapport d'approbations illisible"
    requirement: "QUAL-09"
    verification:
      - kind: unit
        ref: "quality/deps-guard.test.ts, quality/deps-guard-cli.test.ts"
        status: pass
      - kind: integration
        ref: "GATE_BASE_DIR=<worktree de base> pnpm quality --only deps avec ms@2.1.3 ajouté : sortie 1, règle dependency-added dans reports/gate.json"
        status: pass
    human_judgment: false
  - id: D2
    description: "Check `deps` ci-only : rapport de confiance lu en CI sur pull_request (échec fermé sans lui, sévérité et identité imposées), skipped ci-only en local"
    requirement: "QUAL-09"
    verification:
      - kind: unit
        ref: "quality/checks/deps.test.ts"
        status: pass
      - kind: integration
        ref: "pnpm quality : deps skipped (ci-only), verdict pass"
        status: pass
    human_judgment: false
  - id: D3
    description: "Verdict de confiance : cible workflow_run validée, décision `failure` sur tout défaut, statut `quality` publié une seule fois par juges et publication injectés ; extraction de la tête comme données, juges sans jeton"
    requirement: "QUAL-07"
    verification:
      - kind: unit
        ref: "quality/verdict.test.ts, quality/verdict-io.test.ts, quality/verdict-cli.test.ts"
        status: pass
    human_judgment: false
  - id: D4
    description: "Workflow `quality-verdict` (workflow_run, environnement gate-verdict, application dédiée) et exception zizmor unique"
    requirement: "QUAL-07"
    verification:
      - kind: other
        ref: "pnpm quality --only workflow-lint,workflow-audit,typecheck,lint : verdict pass ; sans .github/zizmor.yml, zizmor signale dangerous-triggers sur quality-verdict.yml"
        status: pass
    human_judgment: true
    rationale: "Le workflow ne peut s'exécuter qu'une fois présent sur main avec l'application, l'environnement et le ruleset du plan 01-14 ; la preuve sur GitHub (scénario workflow-rewrite) et la relecture humaine de l'exception zizmor (D-01) y sont prévues"

duration: ~25min
completed: 2026-11-21
status: complete
---

# Phase 1 Plan 08 : Garde des dépendances et verdict de confiance hors PR Summary

**Garde des dépendances (diff `package.json` et lockfile, `deps-approved` signée exigée, existence et âge de création sur npm) et juge `quality-verdict` (`workflow_run` lu sur la branche par défaut, tête de PR extraite comme données, juges lancés depuis la base sans jeton, statut requis `quality` publié par une application dédiée), testés avec de vrais processus git, node et `gh` sans mock de module.**

## Performance

- **Duration :** ~25 min (estimée : l'heure de départ n'a pas été relevée avant la première commande)
- **Tasks :** 2 (toutes deux en TDD : RED puis GREEN)
- **Files :** 14 créés, 0 modifié
- **Commits (mesurés) :** `git rev-list --count cf0b1eb~1..HEAD` donne 5 (hors le commit de ce SUMMARY)

## Accomplishments

- `diffDependencies` (pur) lit les sections `dependencies`, `devDependencies`, `optionalDependencies`, `peerDependencies` et `pnpm.overrides`, puis les clés de premier niveau de chaque section `packages:` du lockfile (le lockfile pnpm compte deux documents YAML) : aucun paquet YAML ajouté. Un retrait donne une note, jamais une exigence d'approbation.
- `evaluateDependencies` exige `deps-approved` pour `dependency-added`, `dependency-changed` et `transitive-added`, puis interroge le registre pour les seuls noms nouveaux (une fois chacun, par paquets de 8) : `dependency-not-on-registry` et `dependency-too-young` échouent même approuvés. La recherche est un paramètre ; `registryLookup` (CLI) valide le nom npm avant de construire l'URL.
- CLI `quality/deps-guard.ts` : sortie 0 conforme, 1 refus (rapport écrit atomiquement), 2 usage ou lecture impossible sans rapport (rapport d'approbations absent, JSON illisible, `approved` qui n'est pas un tableau de chaînes, `--approved` et `--approvals-report` ensemble, dossier sans `package.json`, `package.json` de la tête symbolique). `--bootstrap` fait de chaque paquet un ajout.
- Check `deps` : en CI sur `pull_request`, lit `reports/deps.json` (absent ou hors schéma : `missing-trusted-report`), impose `blocking` et l'identité `deps`/`deps-guard` au rapport relu ; en CI hors `pull_request` : `passed` avec note ; en local avec `GATE_BASE_DIR` : garde réel (`GATE_APPROVED_KINDS`) ; sinon `skipped` `ci-only`.
- `decideVerdict` rend `failure` dès qu'une raison existe : `gate-not-success`, `untrusted-gate-path`, `untrusted-gate-event`, `pr-not-found`, `integrity-failed`, `deps-failed`, `missing-trusted-report:<nom>`, `bootstrap-not-allowed` ; les refus du rapport d'approbations (`approval-stale`, `approval-unsigned`…) sont repris comme issues informatives. `parseTarget` exige un SHA de 40 hexadécimaux et un numéro de PR entier.
- `runVerdict` : extraction de la tête, juge d'approbation, puis intégrité et dépendances avec `--approvals-report` ; un juge qui lève devient `judge-error:<nom>` et le statut est tout de même publié une fois. Le CLI lit la charge dans `GITHUB_EVENT_PATH`, cherche la PR par `gh api …/commits/<sha>/pulls` si `pull_requests` est vide, écrit `verdict.json` et sort 0 si la publication a réussi. `--dry-run` joue intégrité et dépendances pour de vrai sur une tête et un rapport d'approbations fournis, sans publier.
- `quality-verdict.yml` : `workflow_run` sur `quality`, `permissions: {}`, concurrence par SHA de tête, un job `verdict` dans l'environnement `gate-verdict`, `contents: read` et `pull-requests: read`, quatre actions épinglées par SHA complet, aucune installation, aucun checkout d'une autre référence, jeton d'application limité à `statuses: write`. `.github/zizmor.yml` ne lève que `dangerous-triggers` pour ce fichier, avec la justification en commentaire (vérifié : sans lui, zizmor signale la règle).

## Task Commits

1. **Tâche 1 : garde des dépendances, RED** - `cf0b1eb` (test)
2. **Tâche 1 : garde des dépendances et check `deps`, GREEN** - `e6de841` (feat)
3. **Tâche 1 : refus d'un lien symbolique dans la tête** - `7b41389` (fix)
4. **Tâche 2 : verdict, RED** - `addd27a` (test)
5. **Tâche 2 : verdict, workflow et exception zizmor, GREEN** - `5130c1d` (feat)

Aucun commit `refactor` : le code vert n'appelait pas de nettoyage supplémentaire.

## TDD

- **Tâche 1, RED :** `deps-guard.test.ts` (36 tests) contre un squelette aux signatures finales au comportement faux. Test cible : `diffDependencies > signale une devDependency ajoutée avec sa version`. Run Vitest avec le reporter `junit` : 34 échecs sur 36 (les 2 réussites le sont par construction). `gsd-tools check tdd-red-evidence` rend `RED_EVIDENCE_OK` (`target_test_failed`). Évaluation sémantique : le test cible s'exécute et échoue sur son assertion `toEqual` (`[{ name: '?', kind: 'dependency-removed' }]` reçu pour `[{ name: 'c', to: '3.0.0', kind: 'dependency-added' }]` attendu), sans échec d'import, de syntaxe ni de fixture.
- **Tâche 1, GREEN :** implémentation, 35 tests puis 55 avec les fichiers voisins, typage, lint et format propres. Les tests du CLI ont été déplacés dans `deps-guard-cli.test.ts` pour tenir la limite de 300 lignes.
- **Tâche 2, RED :** `verdict.test.ts` (42 tests) contre un squelette. Test cible : `parseTarget > lit une charge workflow_run complète`. 36 échecs sur 42, `RED_EVIDENCE_OK`. Évaluation sémantique : le test cible reçoit `{ error: '?' }` au lieu de la cible complète, échec d'assertion `toEqual`.
- **Tâche 2, GREEN :** 42 tests de `verdict.test.ts` verts ; les tests de l'entrée-sortie (`verdict-io.test.ts`, 15) et du CLI (`verdict-cli.test.ts`, 7) ont été écrits avec le code vert, ils couvrent la plomberie hors du contrat testé en RED.
- Les preuves RED vivent sous `.gsd/tdd-evidence/01-08/` (ignoré).

## Files Created/Modified

- `quality/deps-guard.ts` - évaluation (`deps-approved`, registre), CLI à échec fermé, `parseCheckResult`, `writeJsonAtomic`
- `quality/deps-diff.ts` - `diffDependencies` pur (manifeste et lockfile), réexporté par `deps-guard.ts`
- `quality/checks/deps.ts` - check `deps`
- `quality/verdict.ts` - `runVerdict`, CLI, réexport de l'API pure
- `quality/verdict-rules.ts` - types, `parseTarget`, `readApprovalsReport`, `decideVerdict`, `statusPayload`
- `quality/verdict-io.ts` - `extractHeadFromGit`, `nodeJudge`, `githubPublisher`, `findPullRequest`
- `.github/workflows/quality-verdict.yml`, `.github/zizmor.yml`
- six fichiers de test (`deps-guard`, `deps-guard-cli`, `checks/deps`, `verdict`, `verdict-io`, `verdict-cli`)

## Decisions Made

Voir `key-decisions`. En résumé : un seul diff pour le manifeste et le lockfile sans double signalement ; registre toujours exigé, même approuvé ; chemin du run comparé sans le suffixe de référence ; un statut publié quoi qu'il arrive ; aucun jeton dans l'environnement des juges.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fichiers ajoutés hors de la liste `files_modified`**
- **Found during :** Tâches 1 et 2 (`eslint` : `max-lines` 300 et `max-lines-per-function` 60, blocants dans la gate)
- **Issue :** `deps-guard.ts` (336 lignes), `verdict.ts` (≈ 380) et `deps-guard.test.ts` (305, un `describe` de 72 lignes) dépassaient les seuils.
- **Fix :** scission par rôle en gardant l'API publique du plan : `quality/deps-diff.ts` (diff pur, réexporté par `deps-guard.ts`), `quality/verdict-rules.ts` (parseur, décision, statut ; réexportés par `verdict.ts`), `quality/verdict-io.ts` (git, juges, `gh`), et des fichiers de test supplémentaires (`deps-guard-cli.test.ts`, `checks/deps.test.ts`, `verdict-io.test.ts`, `verdict-cli.test.ts`). Les tests du plan (`deps-guard.test.ts`, `verdict.test.ts`) restent les points d'entrée.
- **Files modified :** voir ci-dessus
- **Verification :** `pnpm exec eslint quality --max-warnings 0` sans erreur
- **Committed in :** `e6de841`, `5130c1d`

**2. [Rule 2 - Missing critical] Durcissements de la frontière tête de PR / base**
- **Found during :** Tâche 2 (modèle de menace T-01-45, T-01-55)
- **Issue :** le plan n'écartait pas explicitement la lecture d'un fichier symbolique dans la tête, ni la présence des jetons dans l'environnement du `git` qui extrait la tête.
- **Fix :** `readPlain` refuse un lien symbolique (`lstat`) pour `package.json` et le lockfile ; `extractHeadFromGit` retire `GATE_STATUS_TOKEN`, `GH_TOKEN` et `GITHUB_TOKEN` de son environnement et n'ajoute le jeton du workflow qu'au `git fetch`, par `GIT_CONFIG_*` (nécessaire pour un dépôt privé puisque `persist-credentials: false`). Règle `registry-lookup-failed` ajoutée pour l'échec fermé d'une recherche ou d'une date illisible, et raison `judge-error:extract-head` pour l'échec de l'extraction.
- **Files modified :** `quality/deps-guard.ts`, `quality/verdict-io.ts`, tests associés
- **Verification :** test `sort 2 quand package.json de la tête est un lien symbolique`, tests `nodeJudge` (aucun jeton dans le rapport du juge)
- **Committed in :** `7b41389`, `5130c1d`

**3. [Rule 1 - Bug] La vérification automatique du plan laisse `pnpm-lock.yaml` modifié**
- **Found during :** Tâche 1 (deuxième commande `<automated>`)
- **Issue :** `pnpm quality` après ajout de `ms` dans `package.json` déclenche l'installation automatique de pnpm : `pnpm-lock.yaml` est modifié et `node_modules/ms` installé ; la commande du plan ne restaure que `package.json`.
- **Fix :** lockfile restauré par `git checkout -- pnpm-lock.yaml`, `pnpm install --frozen-lockfile` rejoué pour retirer `ms`. À corriger si cette commande est reprise (plans 01-12 et 01-14) : restaurer aussi `pnpm-lock.yaml`, ou lancer `node quality/run.ts --only deps` plutôt que `pnpm quality`.
- **Files modified :** aucun fichier suivi

---

**Total deviations :** 3 (1 bloquant, 1 critique manquant, 1 bug de la commande de vérification)
**Impact on plan :** aucune dérive de périmètre ; les fichiers ajoutés sont des scissions imposées par les seuils de la gate, l'API et les noms du plan sont inchangés.

## Issues Encountered

- Le test de RED de la tâche 1 a d'abord été refusé par le classifieur (`no_target_test_failure`) : le nom du test cible doit être qualifié (`fichier#suite > test`). Corrigé dans l'enregistrement, pas dans le test.
- `import.meta.main` (Node 26) est reconnu par le typage et par Vitest (faux à l'import) : le même fichier sert de module testé et de commande.
- `eslint-plugin-sonarjs` refuse les expressions régulières à retour arrière super-linéaire : les clés du lockfile et les noms npm sont lus par des fonctions sur chaînes.

## Known Stubs

Aucun.

## Hypothèses signalées et reports

- **Dépendance du check `deps` en CI :** tant que le plan 01-14 n'a pas câblé l'étape de confiance qui écrit `reports/deps.json`, un run `pnpm quality` sur `pull_request` échoue fermé avec `missing-trusted-report` (même comportement voulu que `integrity`).
- **`app-id` :** `actions/create-github-app-token` v3.3.0 marque `app-id` obsolète au profit de `client-id` ; le workflow garde `app-id` / `vars.GATE_APP_ID` comme le demande le plan (simple avertissement). Au plan 01-14, soit créer la variable avec l'identifiant de l'application, soit passer à `client-id`. Le SHA épinglé `64ab729a…` est celui de la v3.3.0 (publiée le 2026-10-12, plus de 7 jours) ; la v3.4.0 (2026-11-18) a été écartée pour son âge.
- **`workflow_run.path` :** la forme exacte (avec ou sans suffixe `@<référence>`) n'est pas vérifiée sur GitHub ; les deux sont acceptées. À constater au premier run réel (plan 01-14).
- **`mise-action` avec `install_args: node` :** seul Node est installé ; que les étapes suivantes trouvent `node` dans le PATH alors que les autres outils de `mise.toml` manquent n'est constaté qu'au premier run sur `main` (plan 01-14).
- **A4 (`gh` préinstallé) :** non vérifié localement ; le faux `gh` des tests ne prouve que les arguments et le jeton.
- **Audits zizmor en ligne :** non joués localement (hors ligne, pas de `GH_TOKEN`) ; les SHA des quatre actions sont ceux de `quality.yml` ou vérifiés par `gh api` (`create-github-app-token`).
- **Registre en amorçage :** `--bootstrap` fait une recherche par paquet du lockfile ; le plan 01-14 le joue une fois, par paquets de 8, avec un délai de 20 s par requête.

## User Setup Required

None - no external service configuration required (l'application GitHub, l'environnement `gate-verdict`, sa variable `GATE_APP_ID` et son secret `GATE_APP_PRIVATE_KEY` sont créés par l'humain au plan 01-14).

## Next Phase Readiness

- Prêt pour le plan 01-14 (verrou) : `quality-verdict.yml` attend l'application, l'environnement restreint à `main` et le ruleset exigeant cette application comme source de `quality` ; le `--dry-run` de `quality/verdict.ts` est la preuve locale prévue (avec le vrai `quality/integrity.ts` du plan 01-06).
- Prêt pour le plan 01-12 (auto-test) : cas `deps-*` jouables avec `GATE_BASE_DIR` et `GATE_APPROVED_KINDS`.

## Threat Flags

Aucun nouveau : les surfaces ajoutées (workflow `workflow_run` privilégié, jeton d'application, lecture de la tête) sont celles du `<threat_model>` du plan (T-01-28, T-01-44, T-01-45, T-01-55).

## Self-Check: PASSED

Fichiers présents (14), commits `cf0b1eb`, `e6de841`, `7b41389`, `addd27a`, `5130c1d` ancêtres de HEAD, `eslint`, `tsc` et `biome` propres, 209 tests Vitest verts, `pnpm quality` au verdict `pass` (`deps` : `skipped` `ci-only`).

---
*Phase: 01-socle-et-quality-gate*
*Completed: 2026-11-21*
