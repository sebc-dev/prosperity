---
phase: "01"
slug: "socle-et-quality-gate"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-11-25"
---

# Phase 01 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Arbre de la PR → juges de confiance | Fichiers contrôlés par l'auteur de la PR (workflows, `package.json`, lockfile, scripts, config d'outils) jugés par le code de la base | Code et configuration non fiables |
| Workflow privilégié (`quality-verdict`, `workflow_run`) → tête de PR | Droits sur le dépôt de base et jeton de l'application `prosperity-gate` ; la tête n'est lue que comme données | Jeton `statuses: write`, preuves d'approbation |
| Agent IA → gate | Édition de chemins protégés, commandes shell, gestes GitHub (labels, fusion, réglages) | Seuils, tests, workflows, permissions |
| Registre npm / binaires d'outils → poste et CI | Paquets, scripts d'installation, binaires gitleaks/semgrep/… | Supply chain |
| Dépôt public → secrets | gitleaks, rapports de gate, jeton Sonar | Secrets, jetons |
| Rôle applicatif → PostgreSQL | `prosperity_app` / `prosperity_migrator`, RLS par membre | Données financières du foyer |
| GitHub `main` → homelab (kfzcore) | Analyse SonarQube nightly de `origin main` uniquement | Code fusionné, jeton Sonar |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-01-01 | Tampering | `.github/workflows/quality.yml` (injection via contexte d'événement dans `run:`) | high | mitigate | Aucune expression de contexte d'événement dans un `run:` ; la base vient de `GITHUB_BASE_REF` ; zizmor `template-injection` bloquant dès le plan 01-04 | closed |
| T-01-02 | Information disclosure | artefact `gate` (`reports/gate.json`) d'un dépôt public | medium | mitigate | Le rapport ne contient que `rule`/`message`/`file`/`line` ; les checks de secrets (plan 01-04) tournent en mode rédigé et ne recopient jamais les champs de correspondance | closed |
| T-01-03 | Tampering | binaires d'outils (gitleaks, semgrep, actionlint…) | high | mitigate | `mise.lock` (checksums + provenance) ; en CI, `jdx/mise-action` avec `install_args: "--locked"` explicite (critère `grep` de la tâche 1, invariant repris par `quality/lock.test.ts` au plan 01-14 et par le nightly au plan 01-13) ; versions vérifiées par chaque check (`tool-version-mismatch`) | closed |
| T-01-04 | Elevation of privilege | job `quality` exécutant du code de PR | high | mitigate | Déclencheur `pull_request` uniquement, `permissions: {}` + lecture seule au job, `persist-credentials: false`, runner hébergé (D-13) | closed |
| T-01-05 | Tampering | installation de mise sur le poste | medium | mitigate | Binaire de release téléchargé par `gh release download`, contrôlé par `SHASUMS256.txt` ; jamais d'exécution d'un script distant | closed |
| T-01-06 | Repudiation | rattachement d'historique (`merge -s ours`) | low | accept | Décision one-way prise par l'humain (tâche 2) ; l'arbre inchangé est vérifié (`git diff --quiet HEAD^1 HEAD`) et la PR reste brouillon | closed (accepted) |
| T-01-SC | Tampering | installs npm/pnpm | high | mitigate | Seul `typescript@6.0.3` (verdict OK) est installé ici ; politique `minimumReleaseAge`/`allowBuilds` active dès ce plan ; checkpoint de légitimité bloquant avant tout paquet `[SUS]` (plan 01-02) | closed |
| T-01-07 | Tampering | dépendances npm (typosquat, version trop fraîche) | high | mitigate | Checkpoint `blocking-human` de légitimité (tâche 1), versions exactes, `minimumReleaseAge: 10080` strict, aucune exclusion d'âge | closed |
| T-01-08 | Elevation of privilege | scripts `postinstall` | high | mitigate | `strictDepBuilds: true` + `allowBuilds` explicite à false (plan 01-01) ; toute nouvelle construction échoue l'installation | closed |
| T-01-09 | Tampering | `eslint.config.mjs` / directives de désactivation | medium | mitigate | `require-description`, `no-unused-disable`, `reportUnusedDisableDirectives: 'error'`, `--max-warnings 0` ; seuils dans `quality/thresholds.json` comparés par l'intégrité (plan 01-06) | closed |
| T-01-10 | Tampering | tests faibles du noyau financier | high | mitigate | Stryker bloquant à 80 sur le diff (source des tests modifiés inclus), couverture 100 % sur `layout.pure`, règles `@vitest/eslint-plugin` contre les assertions creuses | closed |
| T-01-11 | Tampering | faux survivants Stryker (#6335) qui poussent à baisser le seuil | medium | mitigate | Mesure de 20 exécutions, `disableBail` ou relance des survivants ; seuil fixé dans `quality/thresholds.json`, comparé par l'intégrité (plan 01-06) | closed |
| T-01-12 | Tampering | montants convertis par flottant | high | mitigate | Parseur `bigint` maison, règles ESLint `parseFloat`/`Number(`/`Math.round` sur les globs purs, propriétés fast-check | closed |
| T-01-58 | Tampering | périmètre de couverture (`GATE_COVERAGE_SCOPE`) détourné pour sortir du code du plancher global | medium | mitigate | Défaut `all` (tout `src/**`, aucun dossier exclu) ; seul le check `unit` pose `pure`, dans l'environnement de son processus fils ; valeur inconnue = erreur de configuration ; plancher global jugé par le check `coverage` (plan 01-05) ; `vitest.config.ts` et `quality/**` protégés | closed |
| T-01-13 | Information disclosure | secret committé dans le dépôt public | critical | mitigate | gitleaks au pré-commit (`--staged`) et sur l'historique en CI, mode rédigé ; signalement à l'humain des résultats de l'historique hérité | closed |
| T-01-14 | Tampering | action non épinglée, injection de template, permissions larges | high | mitigate | zizmor bloquant (`unpinned-uses`, `template-injection`, `excessive-permissions`) + actionlint (plan 01-01) | closed |
| T-01-15 | Tampering | dépendance vulnérable | high | mitigate | osv-scanner (≥ 7.0 bloquant, calculé par le runner) + `pnpm audit --prod` ; exceptions seulement dans `osv-scanner.toml` protégé | closed |
| T-01-16 | Tampering | dérive des packs Semgrep du registre | medium | mitigate | Décision humaine Q4 ; règles du projet versionnées et testées par `semgrep --test` | closed |
| T-01-17 | Elevation of privilege | rôle `prosperity_app` | high | mitigate | `NOLOGIN NOINHERIT NOCREATEDB NOCREATEROLE NOBYPASSRLS`, `REVOKE CREATE ON SCHEMA public`, tests `42501` et méta-test des attributs du rôle | closed |
| T-01-18 | Information disclosure | future table à `owner_member_id` sans RLS | high | mitigate | Méta-test `[meta:rls-owner-member-id]` posé avant toute table, prouvé mordant par l'auto-test | closed |
| T-01-19 | Tampering | image `postgres` | medium | mitigate | Image épinglée par digest `sha256:eb63372c…` | closed |
| T-01-20 | Tampering | injection SQL par exécution de texte brut | high | mitigate | `sql.raw` autorisé dans le seul fournisseur par la configuration ESLint ; règle Semgrep `prosperity.sql-concatenation` | closed |
| T-01-59 | Tampering | code de `src/db/` hors du plancher global (couverture mesurée sur les seuls tests unitaires, ou code exécuté seulement dans `globalSetup`, non instrumenté) | medium | mitigate | Check `coverage` sur un run fusionné `unit` + `integration` en périmètre `all` ; tests de `src/db/` exécutés dans les workers ; `coverage-scope-incomplete` si un fichier de `src/db/` manque au rapport ou si l'intégration n'a pas tourné ; contrôle négatif (fichier non testé ajouté → `coverage-threshold`) | closed |
| T-01-42 | Elevation of privilege | migrations exécutées en superutilisateur, ou rôle app confondu avec le rôle de migration (D-10) | high | mitigate | `prosperity_migrator` provisionné hors migration sans SUPERUSER ni BYPASSRLS, propriétaire de la base et du schéma ; migrations jouées sous ce rôle (`current_user` vérifié) ; tests `[foundation:migrations-run-as-migrator]` et `[meta:migrator-role]` | closed |
| T-01-21 | Tampering | seuils, assertions, politique pnpm, cliquet, migrations | high | mitigate | `evaluateIntegrity` avec table `DIRECTIONS` codée côté script ; approbation signée `gate-change-approved` (D-14) requise pour chaque écart | closed |
| T-01-22 | Tampering | PR qui réécrit `quality/integrity.ts` ou `protected-paths.json` pour se juger | high | mitigate | Liste et script lus dans la copie de base en CI (câblage au plan 01-14) et rejoués par le verdict de confiance défini sur la branche par défaut (plan 01-08) ; mode amorçage exigeant l'approbation quand la base ne les contient pas | closed |
| T-01-23 | Elevation of privilege | écritures shell de l'agent vers la gate, fusion de PR par l'agent, demande de signature sur la clé matérielle ou ajout de clé au compte | high | mitigate | `evaluateCommand` (sed -i, redirections, mv/cp/rm, git restore, `sh -c` imbriqué, `gh pr merge`, `gh pr review`, `gh repo edit`, secrets et variables, push vers `main`, `-S`/`--gpg-sign`/configuration de signature, sujet `gate-approval:`, `ssh-keygen`, `ssh-add`, `gh ssh-key`, `gh gpg-key`, API des clés) + pré-commit `precommit-protected.ts` ; activation au plan 01-14 | closed |
| T-01-24 | Denial of service | garde qui plante et bloque tout Bash | low | accept | Erreur d'analyse = aucune décision (code 0) ; la CI reste le juge (D-04) | closed (accepted) |
| T-01-56 | Tampering | fichiers que les outils lisent d'eux-mêmes (`.gitleaksignore`, `.semgrepignore`, `.npmrc`, `.pnpmfile.*`, `mise.local.toml`, `.tool-versions`, `lefthook-local.yml`, variantes de config, `.gitignore`, `.gitattributes`, harnais de test) | high | mitigate | Tous dans `quality/protected-paths.json` : ajout ou modification = `protected-path-changed`, approbation signée exigée (D-14), auto-test déclenché (D-08), deny agent et CODEOWNERS dérivés au plan 01-14 ; table `isProtected` testée et contrôle `<automated>` sur une liste d'exemples | closed |
| T-01-57 | Tampering | directives qui retirent du code d'un juge (`Stryker disable`/`restore`, `v8`/`istanbul`/`c8 ignore`, `nosem`, `gitleaks:allow`, `jscpd:ignore`, `@public`/`@beta`/`@alias`) | high | mitigate | Comptées par le cliquet d'échappatoires, budget 0, sans égard à la casse ni aux espaces ; cas d'auto-test `escape-hatch-coverage-ignore` (plan 01-12) | closed |
| T-01-25 | Spoofing | label posé par un acteur hors allowlist (bot, autre compte, acteur supprimé) | high | mitigate | Dernier `labeled` du label exigé d'un acteur de `quality/approvers.json` lu dans la base ; acteur vide refusé ; `approval-actor-not-allowed` ; scénario réel `bot-label` (plan 01-14) | closed |
| T-01-26 | Tampering | label posé avant le dernier push, ou approbation rejouée sur un autre contenu | high | mitigate | Ancre serveur (plus ancien run `pull_request` du SHA sur la branche de tête de la PR, relevé au dernier `head_ref_force_pushed`), jamais la date du commit ; comparaison stricte ; `approval-stale` ; tête déplacée → `approval-head-moved` ; retrait des labels au push par `reset-approval` en hygiène ; `strict_required_status_checks_policy` du ruleset (plan 01-14) | closed |
| T-01-27 | Spoofing | label posé par l'agent avec le jeton `gh` de `sebc-dev`, indiscernable d'un label humain | high | accept | Risque accepté par décision humaine (D-15). Barrière : règles deny de D-03 (labels, API en écriture, fusion) et garde Bash du plan 01-06, activés au verrou (plan 01-14) ; fusion humaine seule ; résiduel documenté dans `docs/quality-gate.md` (plan 01-13) ; durcissement disponible sans changer le schéma du rapport : commit d'approbation signé (D-14) | closed (accepted) |
| T-01-43 | Tampering | allowlist ou labels requis lus dans l'arbre de la PR (répertoire courant, dossier du script) | high | mitigate | `--base-dir` obligatoire, `loadApproversConfig(baseDir)` seule source ; tests : configuration permissive de la tête sans effet, sortie 2 sans `--base-dir`, garde `grep` contre toute lecture relative ; amorçage : allowlist = propriétaire du dépôt lu dans l'API, rapport `bootstrap: true` refusé par le verdict (plan 01-08) | closed |
| T-01-52 | Denial of service | preuves forgées ou tronquées pour faire planter le juge | low | mitigate | Lecture validée champ par champ ; toute forme inattendue → `approval-evidence-invalid`, jamais une approbation ni une exception non gérée | closed |
| T-01-60 | Information disclosure | jeton de l'application ou du workflow exposé au juge ou au collecteur (affecte T-01-45 du plan 01-08) | high | mitigate | Collecte faite par le code de `main` (`runVerdict`) avec le seul jeton du workflow, `GATE_STATUS_TOKEN` et `GITHUB_TOKEN` retirés de l'environnement de `gh` (test du faux `gh`) ; GET seulement (garde `grep` et test) ; `nodeJudge` inchangé : juges sans jeton ; permission ajoutée au job : `actions: read`, en lecture | closed |
| T-01-61 | Tampering | preuves incomplètes (pagination tronquée) ou d'une autre PR, d'un autre SHA | medium | mitigate | `--paginate --slurp` ; `pr` et `headSha` des preuves comparés au jugement (`approval-evidence-invalid`) ; runs filtrés par dépôt et branche de tête de la PR | closed |
| T-01-62 | Elevation of privilege | job `reset-approval` en écriture dans le workflow de la PR | low | mitigate | Job sans checkout, sans action, sans code de la PR ; `pull-requests: write` au seul niveau du job ; contexte passé par `env:` (zizmor) ; `continue-on-error` ; la PR peut réécrire ce job, mais l'autorité est l'horodatage jugé hors PR ; jeton en lecture seule pour les forks | closed |
| T-01-28 | Tampering | paquet halluciné ou typosquatté ajouté par un agent | high | mitigate | Existence sur le registre, âge de création ≥ 30 jours, approbation signée `deps-approved` (sorte du commit d'approbation, D-14), plus `minimumReleaseAge` à l'installation | closed |
| T-01-44 | Spoofing | statut requis `quality` produit par la PR elle-même (workflow réécrit, job renommé, jeton du workflow) | high | mitigate | Statut publié par l'application dédiée depuis `quality-verdict` (définition de la branche par défaut) ; clé dans l'environnement `gate-verdict` restreint à `main` ; ruleset exigeant cette application comme source (plan 01-14) | closed |
| T-01-45 | Elevation of privilege | workflow `workflow_run` privilégié qui exécuterait du code de la PR | high | mitigate | Checkout de la seule branche par défaut, tête extraite comme données (`GIT_LFS_SKIP_SMUDGE=1`), juges lancés depuis la base avec `cwd` hors de la tête, aucune installation ; permissions en lecture, jeton d'application limité à `statuses: write` ; exception zizmor `dangerous-triggers` unique et justifiée | closed |
| T-01-55 | Tampering | `reports/approvals.json` absent, tronqué ou hors schéma, relu par `deps-guard` et le verdict sans le code du juge qui l'écrit | medium | mitigate | Rapport écrit par le juge de la base dans le dossier de travail du verdict, jamais lu dans la tête ; lecteur validé dans chaque script ; rapport illisible = rapport absent : `missing-trusted-report:approvals` (verdict `failure`) ou sortie 2 du garde ; `bootstrap: true` refusé par le verdict | closed |
| T-01-29 | Elevation of privilege | outil MCP qui lit la base sans filtre de membre | high | mitigate | Règles `mcp-tools-no-db` et `db-access-restricted` bloquantes ; verdict lu dans `summary.error` | closed |
| T-01-30 | Tampering | dépendance ajoutée puis inutilisée, ou utilisée sans être déclarée | medium | mitigate | knip bloquant (`dependencies`, `unlisted`), sans `ignore` fourre-tout ; garde `deps` (plan 01-08) | closed |
| T-01-31 | Information disclosure | faux secret du cas `sec-generated-secret` | medium | mitigate | Jeton généré à l'application par `crypto.randomBytes`, jamais committé ; garde `git grep` sur `ghp_` dans `quality/` | closed |
| T-01-32 | Tampering | worktrees jetables et `LEFTHOOK=0` | medium | mitigate | Variable posée seulement dans l'environnement du processus fils, sur un worktree détaché jetable ; nettoyage en `finally` et `git worktree prune` | closed |
| T-01-33 | Repudiation | cas vert par accident (outil absent, config cassée) | high | mitigate | `matchesExpected` exige la règle attendue ; contrôle propre par check avant les cas ; `case-not-applicable` et `control-failed` sont rouges | closed |
| T-01-46 | Repudiation | cas vert pour une autre violation que celle visée (cas à plusieurs défauts) | medium | mitigate | Une violation par cas ; `matchesExpected` exige la règle attendue ; contrôle propre par check avant les cas (plan 01-10) | closed |
| T-01-47 | Repudiation | cas « test faible » décrit par un objectif et non par un patch, vert ou rouge selon l'exécuteur | medium | mitigate | Patch fixe (suppression d'un fichier, remplacement par un texte constant) ; portée de mutation limitée à `allocate.ts` par construction ; score consigné | closed |
| T-01-48 | Tampering | violation volontaire laissée dans le dépôt (workflow non épinglé, table sans RLS, lockfile vulnérable) | medium | mitigate | Violations appliquées seulement dans les worktrees jetables ; gardes `git diff --exit-code` et `test -f` dans les critères d'acceptation | closed |
| T-01-34 | Elevation of privilege | `nightly.yml` | medium | mitigate | `permissions: {}` + lecture seule au job, `persist-credentials: false`, actions par SHA, aucun contexte dans `run:` ; trufflehog en advisory | closed |
| T-01-35 | Repudiation | limites de la gate non dites | medium | mitigate | Section « Limites connues » de `docs/quality-gate.md`, chaque limite avec son contrôle compensatoire | closed |
| T-01-36 | Elevation of privilege | `demo-prs.ts` utilisé par l'agent pour committer des chemins protégés | medium | mitigate | L'outil exige `PROSPERITY_HUMAN_GATE_EDIT=1` dans l'environnement de l'appelant sans jamais la poser ; le garde Bash refuse toute commande d'agent qui contient cette variable (plan 01-14) ; l'intégrité exige toujours le label approuvé ; l'outil ne crée, ne pose ni ne retire jamais de label avec le jeton de l'humain (seul le workflow temporaire de `bot-label` en pose un, sous `github-actions[bot]`, pour prouver le refus) | closed |
| T-01-69 | Repudiation | messages du garde de l'agent qui présenteraient encore la signature comme le mécanisme d'approbation | low | mitigate | Messages et commentaires réécrits pour nommer le label de D-15 (tâche 1) ; gardes `grep` sur les trois fichiers ; refus inchangés, prouvés par les tests du garde non modifiés | closed |
| T-01-37 | Elevation of privilege | édition de la gate par l'agent (Edit, Write, NotebookEdit, Bash) | high | mitigate | Deny `Edit(...)` par chemin protégé (couvre tous les outils d'écriture), garde Bash `bash-guard.ts`, pré-commit `protected-paths`, intégrité en CI ; `quality/lock.test.ts` prouve la cohérence et l'absence de règle morte ; refus Edit et Write constatés en session neuve | closed |
| T-01-38 | Spoofing | labels, ruleset ou réglages Actions modifiés par l'agent | high | mitigate | Deny `gh label*`, `gh pr edit*`, `gh issue edit*`, `gh api*labels*`, `gh api` rulesets/actions/permissions et toute écriture `gh api`, `gh auth token` ; garde Bash ; gestes réservés à l'humain (tâche 3) ; refus (d), (e) et (g) constatés en session neuve. Résiduel accepté par D-15 (T-01-27 du plan 01-07) : un agent qui contournerait règles deny et garde pourrait, avec le jeton administrateur, poser un label ou modifier le ruleset ; atténuations durables (jeton distinct non administrateur, commit signé de D-14) hors phase 1 | closed |
| T-01-39 | Tampering | PR qui réécrit `quality.yml` pour sauter les étapes de confiance | high | mitigate | Le job `gate` de la PR n'est pas requis ; le statut requis `quality` est publié par le juge hors PR (`quality-verdict`, plans 01-07 et 01-08), défini sur la branche par défaut, qui collecte lui-même les preuves, rejoue l'intégrité depuis `main` et exige pour `.github/**` le label `gate-change-approved` posé par un acteur de l'allowlist de `main` après le dernier push ; prouvé par `lock.test.ts` (h) et le scénario `workflow-rewrite` (D-07b) ; seule la PR de bootstrap, avant l'existence du juge sur `main`, dépend de la relecture D-01 | closed |
| T-01-40 | Spoofing | statut `quality` rapporté par une autre source | high | mitigate | Ruleset final : source du statut = application `prosperity-gate` (son `integration_id`) ; clé de l'application dans l'environnement `gate-verdict` restreint à `main` ; contexte transitoire `gate` (15368) limité à la fusion de la PR de bootstrap | closed |
| T-01-41 | Elevation of privilege | `disableAllHooks` dans `.claude/settings.local.json` | medium | mitigate | Deny `Edit(/.claude/settings*.json)` et refus de `disableAllHooks` par le garde Bash | closed |
| T-01-49 | Elevation of privilege | fusion par l'agent d'une PR qui touche un chemin protégé ou une dépendance (`gh pr merge`, API, auto-fusion, push vers `main`) | high | mitigate | Le ruleset sans contournement exige le statut `quality` du juge hors PR, vert pour une telle PR seulement si le label requis a été posé par un acteur de l'allowlist de `main` après le dernier push ; règles deny de fusion, de revue, de labels, d'API en écriture et de push vers `main`, garde Bash, auto-fusion désactivée. Résiduel accepté (D-15), documenté (plan 01-13) : le jeton partagé permettrait à un agent qui contournerait deny et garde de poser le label puis de fusionner ; une PR sans chemin protégé ni dépendance reste fusionnable dès que la gate est verte | closed |
| T-01-50 | Tampering | application, environnement `gate-verdict` ou secrets modifiés par l'agent | high | mitigate | Deny `gh secret*`, `gh variable*`, `gh api*environments*`, `gh repo edit*` et toute écriture `gh api` ; la clé privée n'est jamais lisible (secret d'environnement) ; création et réglage de l'application et de l'environnement par l'humain seul (tâche 3) | closed |
| T-01-53 | Spoofing | allowlist de la PR de bootstrap, base sans `quality/approvers.json` (confiance au premier usage) | medium | mitigate | En amorçage, l'allowlist est le propriétaire du dépôt de base lu dans l'API, jamais un fichier de la PR ; le verdict hors PR refuse tout rapport `bootstrap: true` ; la PR de bootstrap n'est fusionnée qu'après la relecture D-01, sous le ruleset transitoire ; après la fusion, seule l'allowlist de `main` compte | closed |
| T-01-63 | Elevation of privilege | PR qui élargit l'allowlist `quality/approvers.json` (bot, autre compte) | high | mitigate | Allowlist lue dans la base : une PR ne se juge jamais avec la sienne ; `quality/**` protégé : une telle PR exige le label `gate-change-approved` posé par un acteur de l'allowlist actuelle ; deny Edit de l'agent ; relecture humaine du diff (CODEOWNERS en documentation) | closed |
| T-01-64 | Information disclosure | jeton ou adresse Sonar dans le dépôt public, un argument de commande, un log, un SUMMARY ou l'environnement des tests | high | mitigate | Lecture depuis l'environnement ou un fichier hors dépôt en mode 0600 (refus sinon) ; jeton passé par `-e SONAR_TOKEN` sans valeur et par l'en-tête HTTP, jamais en argument ; `childEnv` pour ESLint et Vitest ; `redactInvocation` ; garde `git grep` ; règle gitleaks par défaut `sonar-api-token` prouvée ; consigne du SUMMARY sans adresse ; jeton d'analyse d'un seul projet, un par machine | closed |
| T-01-65 | Tampering | image du scanner non épinglée, remplacée ou trop récente | medium | mitigate | `readScannerImage` n'accepte qu'une image officielle épinglée par digest ; maturité de 7 jours au choix de l'étiquette ; mise à jour par PR approuvée sur un chemin protégé | closed |
| T-01-66 | Elevation of privilege | code non fusionné (PR, fork, branche de travail) exécuté sur kfzserver | high | mitigate | Le service ne récupère que `origin main` d'un clone du dépôt public, sans jeton GitHub ; aucun runner auto-hébergé, aucun job GitHub vers le homelab (D-13) ; timer activé seulement après la fusion de la PR de bootstrap ; préparation (tâche 3) sans exécution de code du dépôt. Résiduel documenté : `main` lui-même s'exécute, comme au déploiement | closed |
| T-01-67 | Tampering | `sonar-project.properties` réécrit pour détourner le jeton (hôte, proxy) ou masquer des fichiers au tableau de bord | medium | mitigate | Chemin protégé (deny, CODEOWNERS, intégrité au plan 01-14) ; `forbiddenProperties` refuse hôte, jeton, identifiants et proxy ; hôte imposé par `-Dsonar.host.url` en ligne de commande | closed |
| T-01-68 | Tampering | Sonar qui influencerait le verdict ou tournerait dans la CI GitHub | medium | mitigate | Aucun check Sonar dans `quality/checks/`, aucune étape Sonar dans `.github/workflows/` (gardes `grep`) ; refus de `pnpm sonar` quand `CI` ou `GITHUB_ACTIONS` est défini (test) ; le script n'écrit rien dans `reports/gate.json` | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

`T-01-SC` (supply chain des installs npm/pnpm) apparaît dans chaque plan ; il est consolidé en une seule entrée, vérifiée sur l'ensemble des plans. Preuves `file:line` par menace : rapport de l'auditeur `gsd-security-auditor` du 2026-11-25 (vérification à profondeur ASVS L1 sur le code, réglages GitHub confirmés par l'UAT 01).

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01 | T-01-06 (low) | Rattachement d'historique `merge -s ours` : décision one-way, arbre inchangé vérifié (`git diff --quiet HEAD^1 HEAD`) | humain (01-01, tâche 2) | 2026-11 |
| AR-02 | T-01-24 (low) | Garde Bash qui plante = aucune décision (code 0) ; la CI reste le juge (D-04) ; `docs/quality-gate.md` limite 2 | humain (01-06) | 2026-11 |
| AR-03 | T-01-27 (high) | Label posé par l'agent avec le jeton `gh` administrateur partagé, indiscernable d'un label humain (D-15). Barrières : règles deny, garde Bash, fusion humaine seule ; `docs/quality-gate.md` limite 1 ; durcissement (jeton non administrateur, commit d'approbation signé D-14) hors phase 1 | humain (D-15) | 2026-11 |

*Accepted risks do not resurface in future audit runs.*

---

## Residuals and Unregistered Flags (non-blocking)

Mitigations présentes au niveau L1 ; points relevés par l'auditeur, à traiter ou à accepter formellement dans une phase ultérieure.

| Ref | Threat | Observation |
|-----|--------|-------------|
| R1 | T-01-26 | Rejeu d'approbation possible par force-push aller-retour (Z → X labellisé → avance rapide vers Z) : l'ancre (`quality/approvals.ts:62-77`) juge le label frais ; seul `reset-approval`, dans le workflow de la PR, compense. Absent des « Limites connues » (WR-01). |
| R2 | T-01-03 | `quality-verdict.yml:40` (`install_args: node`) sans `--locked` explicite ; `quality/lock.test.ts:153-155` ne contrôle que `quality.yml` et `nightly.yml`. |
| R3 | T-01-64 | `EnvironmentFile=` du service Sonar expose `SONAR_TOKEN` à `mise install`/`pnpm install` (scripts de cycle de vie bloqués par `strictDepBuilds`) (WR-05). |
| R4 | T-01-15 | Avis OSV sans score CVSS jamais bloquants (`quality/checks/cve.ts:39`) (IN-04). |
| R5 | T-01-16 | Erreurs d'analyse Semgrep de niveau `warn` ignorées (`quality/checks/sast.ts:64-66`) (WR-06). |
| R6 | T-01-60 | `findPullRequest` (`quality/verdict-io.ts:144-155`, repli fork) passe l'environnement complet, `GATE_STATUS_TOKEN` compris, à un `gh` GET. |
| R7 | T-01-05 | Procédural : SHA-256 du binaire mise local non re-vérifiable hors ligne. |
| F1 | (non enregistré) | `local-container-exec` (01-15, `quality/sonar/local.ts`) : `--network host`, sources montées, groupe `docker` équivalent root ; documenté seulement dans `docs/quality-gate.md:340-341`. |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-25 | 68 | 68 | 0 | gsd-security-auditor (opus), ASVS L1, block_on high |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-25
