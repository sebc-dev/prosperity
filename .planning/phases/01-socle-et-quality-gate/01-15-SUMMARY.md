---
phase: 01-socle-et-quality-gate
plan: 15
subsystem: infra
tags: [sonarqube, advisory, sonar-scanner, docker, systemd, quality-gate, d-16]

requires:
  - phase: 01-socle-et-quality-gate
    provides: "gate `pnpm quality`, chemins protégés (`quality/protected-paths.json`), `docs/quality-gate.md` (01-13)"
provides:
  - "`pnpm sonar` : rapports ESLint JSON (configuration bloquante et sécurité) et LCOV, scanner officiel épinglé par digest dans un conteneur, attente de la tâche du serveur (`SUCCESS`) ; `--dry-run` sans réseau"
  - "`quality/sonar/sonar-kit.ts` : fonctions pures (configuration, image épinglée, propriétés interdites, chemins relatifs, environnement des processus enfants, invocation masquée, décision de tâche) et `wait.ts` (attente à horloge injectée)"
  - "`sonar-project.properties` protégé ; `pnpm sonar` refuse hôte, jeton, identifiants et proxy dans ce fichier"
  - "Unités systemd utilisateur `deploy/sonar/prosperity-sonar.{service,timer}` : analyse nightly de `main` sur le poste kfzcore (worktree git détaché)"
  - "Section `## Analyse SonarQube (advisory, D-16)` de `docs/quality-gate.md`"
affects: [01-14]

actuals:
  tokens: 13818   # chars/4 sur le diff e0c5849..1678dca (55 270 caractères)
  tasks: 3
  commits: 7      # MESURÉ : git rev-list --count e0c5849..1678dca (hors commit de ce SUMMARY)
plan_head_before: e0c5849756cb155b58bebb5dc93b3bbacc9a88fc
plan_head_after: 1678dca4884fdf9c3920929bd080230bcc8cf43d

tech-stack:
  added: []
  patterns:
    - "Scanner = image conteneur épinglée par digest, hors graphe npm (aucune dépendance ajoutée)"
    - "Jeton Sonar : environnement du processus du moteur (`-e SONAR_TOKEN` sans valeur) et en-tête HTTP ; jamais en argument, jamais imprimé, retiré de l'environnement des processus de lint et de tests (`childEnv`)"

key-files:
  created:
    - quality/sonar/run.ts
    - quality/sonar/sonar-kit.ts
    - quality/sonar/sonar-kit.test.ts
    - quality/sonar/wait.ts
    - quality/sonar/wait.test.ts
    - quality/sonar/config.ts
    - quality/sonar/local.ts
    - quality/sonar/reports.ts
    - quality/sonar/run.test.ts
    - quality/sonar/scanner.json
    - sonar-project.properties
    - deploy/sonar/prosperity-sonar.service
    - deploy/sonar/prosperity-sonar.timer
  modified:
    - package.json
    - quality/protected-paths.json
    - docs/quality-gate.md

key-decisions:
  - "Scanner = image `sonarsource/sonar-scanner-cli` épinglée par digest (étiquette 12.4.0.4321_8.4.0, publiée le 2026-11-10, SonarScanner CLI 8.4.0) plutôt que paquet npm ou binaire `mise`"
  - "Exécution du scanner sur le poste kfzcore, serveur joint par son adresse HTTPS du tailnet ; mode SSH sur kfzserver écarté (voir Deviations)"
  - "Nightly de `main` par un timer utilisateur de kfzcore, sur un worktree git détaché du dépôt principal (aucun second clone)"
  - "Vitest rendant 1 (test ou seuil) n'arrête pas l'analyse tant que le LCOV existe (advisory) ; avertissement imprimé"
  - "`--coverage.reporter=lcovonly` plutôt que `lcov` (pas de rapport HTML inutile) ; `-Dsonar.working.directory` passé en ligne de commande car l'image impose `/tmp/.scannerwork`"

patterns-established:
  - "Un outil advisory vit hors de `quality/checks/` et hors de `reports/gate.json` : aucun effet sur le verdict"

requirements-completed: [QUAL-01, QUAL-07]

coverage:
  - id: D1
    description: "`pnpm sonar` produit les rapports, lance le scanner épinglé et ne rend 0 que quand la tâche du serveur est `SUCCESS`"
    requirement: QUAL-01
    verification:
      - kind: other
        ref: "node quality/sonar/run.ts (analyse réelle, sortie 0, `analyse traitée (SUCCESS)`)"
        status: pass
      - kind: unit
        ref: "quality/sonar/sonar-kit.test.ts, quality/sonar/wait.test.ts"
        status: pass
    human_judgment: false
  - id: D2
    description: "Le refus en CI, la configuration hors dépôt en 0600 et les propriétés interdites sont appliqués par le script"
    requirement: QUAL-01
    verification:
      - kind: unit
        ref: "quality/sonar/run.test.ts (vrais processus node)"
        status: pass
    human_judgment: false
  - id: D3
    description: "`sonar-project.properties`, `quality/sonar/**` et `deploy/sonar/**` sont des chemins protégés"
    requirement: QUAL-07
    verification:
      - kind: other
        ref: "isProtected() sur les trois chemins (loadProtectedPaths)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Unités systemd valides et worktree du nightly préparé sur kfzcore, timer non activé"
    verification:
      - kind: other
        ref: "systemd-analyze --user verify (copies du dépôt et unités installées) ; timer désactivé"
        status: pass
    human_judgment: true
    rationale: "L'activation du timer attend la fusion de la PR de bootstrap (plan 01-14, tâche 3) ; le premier passage réel du service reste à constater par l'humain"
  - id: D5
    description: "Tableau de bord du projet : couverture non nulle, aucun fichier de `quality/selftest/cases/` analysé, avertissements de sécurité importés"
    verification:
      - kind: other
        ref: "API du serveur (mesures, facettes d'issues), lecture seule"
        status: pass
    human_judgment: true
    rationale: "La constatation visuelle dans l'interface web reste à l'humain ; les mêmes chiffres ont été relus par l'API"

duration: 2h 55m
completed: 2026-11-22
status: complete
---

# Phase 1 Plan 15: Analyse SonarQube advisory Summary

**`pnpm sonar` envoie au SonarQube Community du homelab les rapports ESLint et LCOV du dépôt, par le scanner officiel épinglé par digest dans un conteneur du poste, et n'aboutit que lorsque le serveur a traité l'analyse ; advisory, sans effet sur la gate, nightly de `main` par un timer utilisateur.**

## Performance

- **Duration :** environ 2 h 55 (reprise après trois checkpoints)
- **Tasks :** 3 (tracer TDD, auto, checkpoint humain)
- **Files :** 16 modifiés ou créés (1305 insertions, 1 suppression)

## Accomplishments

- **Analyse réelle réussie.** `node quality/sonar/run.ts` rend 0 et imprime `analyse traitée (SUCCESS)`. Serveur SonarQube Community Build 26.10.0.133078 (lu à l'exécution), SonarScanner CLI 8.4.0. Le journal ne contient ni le jeton ni l'adresse du serveur.
- **Mesures relues sur le serveur :** couverture 98,0 % (`src/shared/money/money.ts` : 100 %, 27 lignes à couvrir), 7915 lignes de code, 0 bug, 0 vulnérabilité, 0 point chaud, 174 « code smells », duplication 1,0 %. Les 174 issues sont les avertissements `eslint-plugin-security` importés comme issues externes (sous-ensemble de règles `detect-non-literal-fs-filename`, `detect-object-injection`, `detect-unsafe-regex`, `detect-non-literal-regexp`). Aucun fichier de `quality/selftest/cases/` n'est analysé (le seul fichier de ce préfixe qui porte des issues est `quality/selftest/cases.ts`, un vrai source).
- **Image épinglée :** `docker.io/sonarsource/sonar-scanner-cli:12.4.0.4321_8.4.0@sha256:6e6eca4d552695a98fb7dab84f0c1bd0885ebbfe272654d1552e24bd7f452d51`, publiée le 2026-11-10 (12 jours, au-delà des 7 jours exigés), digest confirmé par `docker buildx imagetools inspect`.
- **Gate :** `pnpm quality` rend `verdict : pass` ; seul `lint-security` (advisory) échoue, à 192 issues (environ 177 avant ce plan : les nouveaux fichiers en ajoutent une quinzaine).
- **Tests :** 55 tests (3 fichiers) : fonctions pures, attente de la tâche à horloge injectée, refus du CLI par de vrais processus `node`.
- **Garde-fous vérifiés :** `CI=true node quality/sonar/run.ts` sort 2 ; `--dry-run` sort 0 sans jeton ni adresse dans la sortie, avec `@sha256:` et `***` ; gitleaks arrête `SONAR_TOKEN=sqp_…` (règle `sonar-api-token`) ; lockfile inchangé ; aucun check Sonar dans `quality/checks`, aucune mention de Sonar dans les workflows ; aucun fichier suivi ne porte d'adresse du tailnet ni de jeton Sonar.

## Task Commits

1. **Tâche 1, RED** : `c2b248e` (`test(01-15)` : tests de la bibliothèque, du CLI et de l'attente, squelettes sans comportement)
2. **Tâche 1, GREEN** : `4a8883c` (`feat(01-15)` : bibliothèque et attente), `b433875` (`feat(01-15)` : point d'entrée, image épinglée, propriétés du projet, script `sonar`, chemin protégé)
3. **Tâche 2** : `aad4be0` (`feat(01-15)` : unités systemd et documentation)
4. **Refonte après décision humaine** : `ed0edad` (`refactor(01-15)` : mode SSH retiré, scanner local, nightly sur le poste)
5. **Correctif de la vraie analyse** : `6d42f90` (`fix(01-15)` : répertoire de travail du scanner)
6. **Worktree du nightly** : `1678dca` (`docs(01-15)` : worktree détaché du dépôt principal)
7. **Tâche 3** : préparation de kfzcore faite par l'orchestrateur (aucun commit de code, voir plus bas)

## TDD Gate Compliance

- **RED** : `c2b248e`. Preuve classée `RED_EVIDENCE_OK` par `gsd_run check tdd-red-evidence` (format `tap-flat`, cible `redactInvocation laisse l’invocation intacte quand il n’y a pas de jeton`, attendu `docker run x`, obtenu `docker`). Évaluation sémantique : la cible s'est exécutée et a échoué sur l'assertion prévue (le squelette rend la seule commande) ; 123 tests étaient rouges sur des assertions du squelette, pas sur des erreurs de chargement. Le classificateur refuse les rapports dont les diagnostics multiligne (valeurs d'objets) cassent le format TAP : la preuve a donc été prise sur un test à valeurs d'une ligne, isolé par `-t`.
- **GREEN** : `4a8883c` puis `b433875`, les mêmes tests passent.
- **REFACTOR** : `ed0edad`, tests verts après (55 tests).
- **Correctif** (`6d42f90`) : test d'abord (rouge sur l'argument manquant), puis code.

## Deviations from Plan

### Historique du lieu d'exécution (décisions de l'humain)

1. **Plan :** `pnpm sonar` lancé depuis le poste, fichier d'environnement sur le poste.
2. **Décision humaine (2026-11-22) :** scanner exécuté sur kfzserver par SSH, jeton uniquement sur kfzserver. Réalisé : scripts distants sur l'entrée standard de `ssh … sh -s`, vérification préalable avant les rapports, dossier jetable envoyé par `tar`, lecture de la tâche par `curl -K -`. Les scripts étaient exécutés pour de vrai dans les tests (faux dossier personnel, faux moteur, serveur HTTP local). Les sondes en lecture seule (version du serveur, lecture authentifiée de la tâche) ont fonctionné.
3. **Blocage :** l'utilisateur SSH de kfzserver n'est pas dans le groupe `docker`, et la fiche du serveur interdit de l'y mettre ; ni Podman ni `sudo` sans mot de passe. La vérification préalable a échoué fermé (`accès refusé au moteur de conteneur distant`) avant tout rapport.
4. **Décision humaine :** scanner sur kfzcore, serveur joint par son adresse HTTPS du tailnet (le front officiel, pas un tunnel). Mode SSH supprimé (`ed0edad` : `remote-kit`, `ssh`, `remote`, `backend` et leurs tests, tous écrits dans ce plan). Nightly par un timer utilisateur de kfzcore. D-16 reste vrai : advisory, rien dans la CI GitHub, rien sur GitHub ne joint le homelab.
5. **Décision humaine (worktree) :** pas de second clone ; le nightly utilise un worktree git détaché du dépôt principal (`git -C <dépôt principal> worktree add --detach ~/prosperity-sonar origin/main`). Les étapes du service (`git fetch origin main`, `git checkout --detach --force origin/main`, `git clean -fd`) conviennent à un worktree ; les hooks lefthook, partagés avec le dépôt, ne se déclenchent pas car le service ne commit ni ne pousse jamais.

### Écarts techniques

**1. [Rule 1 - Bug] Répertoire de travail du scanner imposé par l'image**
- **Constaté pendant :** première analyse réelle (tâche 1)
- **Problème :** l'image impose `sonar.working.directory=/tmp/.scannerwork` ; `report-task.txt` disparaissait avec le conteneur et le script sortait 1 (« analyse non confirmée ») alors que le scanner rendait 0.
- **Correctif :** `-Dsonar.working.directory=/usr/src/reports/sonar/scannerwork` en ligne de commande (test d'abord).
- **Fichiers :** `quality/sonar/sonar-kit.ts`, `quality/sonar/sonar-kit.test.ts`
- **Commit :** `6d42f90`

**2. [Rule 3 - Blocage] Règles de lint qui refusent les signatures du plan**
- `readScannerImage` rend `{ image } | { error }` au lieu de `string | { error }` : `sonarjs/function-return-type` refuse un retour qui mêle chaîne et objet. Les fonctions internes de validation suivent la même forme.
- Expressions rationnelles réécrites sans retour arrière sur-linéaire (`sonarjs/super-linear-regex`) : analyse de `CLÉ=valeur` par `indexOf`, retrait des barres obliques finales par boucle.

**3. [Rule 3 - Décision mineure] `lcovonly`** à la place de `lcov` : pas de rapport HTML ; Vitest remplace bien la liste de reporters de `vitest.config.ts` en ligne de commande (constaté).

**4. Fichiers hors liste du plan, pour tenir les seuils (300 lignes, 60 lignes par fonction, complexité 10)** : `wait.ts` et `wait.test.ts` (attente de la tâche à horloge injectée), `config.ts`, `local.ts`, `reports.ts`, `run.test.ts` (refus du CLI par de vrais processus).

**5. Vérification automatisée adaptée (tâche 2)** : la commande du plan qui lisait le jeton dans le fichier d'environnement pour le chercher dans la sortie de `--dry-run` a été rejouée à l'identique en fin de plan (aucun jeton, aucune adresse, `@sha256:` et `***` présents).

**6. Choix conservé du plan** : le jeton passe par `-e SONAR_TOKEN` (valeur dans l'environnement du processus du moteur) plutôt que par `--env-file` ; mêmes propriétés (jamais en argument, jamais imprimé).

**7. `http://` sur la boucle locale** est accepté sans drapeau (`http://localhost`, `127.0.0.1`, `[::1]`) ; `SONAR_ALLOW_INSECURE_HTTP=1` reste exigé pour tout autre hôte en `http://`. Utile aux analyses sur la machine même du serveur ; sans effet sur l'adresse HTTPS actuelle.

**Total des écarts :** 1 correctif de bogue, 3 blocages ou décisions de forme, 5 décisions humaines de lieu. **Impact :** aucun sur la gate ni sur la sécurité ; le périmètre du plan est livré.

## Authentication Gates / checkpoints

- **Tâche 1, précondition (deux reprises) :** fichier d'environnement absent, puis moteur de conteneur inaccessible sur kfzserver : points d'arrêt humains, résolus par les décisions ci-dessus. Le fichier d'environnement de kfzcore (mode 0600, `SONAR_HOST_URL` en HTTPS, `SONAR_TOKEN` non vide) a été créé par l'humain ; le projet `prosperity` et le jeton d'analyse de projet aussi. L'exécuteur n'a jamais lu le jeton en clair dans une sortie (lectures par programme, masquées).
- **Tâche 3 (checkpoint humain, résolu avec une variante) :** préparation faite par l'orchestrateur sur kfzcore : worktree `~/prosperity-sonar` créé par `git -C /home/negus/orca/projects/prosperity worktree add --detach ~/prosperity-sonar origin/main` (HEAD `3c1c955`, ancien `main` sans `pnpm sonar`, attendu tant que la PR de bootstrap n'est pas fusionnée) ; unités copiées en mode 644 dans `~/.config/systemd/user/`, `systemctl --user daemon-reload`, `systemd-analyze --user verify` sans erreur ; `~/.local/bin/mise` présent. **Le timer est désactivé** (ni activé ni démarré). Les contrôles du plan propres à kfzserver (version lue sur kfzserver, `podman pull`, socket de Podman) n'ont plus d'objet depuis le changement de lieu.

## Issues Encountered

- `lint-security` (advisory) passe d'environ 177 à 192 issues : spawn et accès fichiers à chemins variables dans les nouveaux scripts. Sans effet sur le verdict ; à revoir avec le reste du bruit de ce check.
- La commande `git`/`mise`/`gitleaks` composée est parfois refusée par le garde de l'environnement d'exécution (« commande trop complexe ») : contournement par commandes séparées, sans incidence sur le code.

## Known Stubs

Aucun.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: local-container-exec | quality/sonar/local.ts | `pnpm sonar` lance un conteneur Docker du poste avec `--network host` et les sources montées ; l'image est officielle et épinglée par digest (T-01-65), `docker` donne des droits équivalents à root à son groupe (documenté dans les limites) |

## Next Phase Readiness

- **Plan 01-14 (verrou)** : `sonar-project.properties` est déjà dans `quality/protected-paths.json` ; `quality/sonar/**` et `deploy/sonar/**` le sont par `quality/**` et `deploy/**`. À l'activation du verrou (tâche 3 du plan 01-14, après la fusion de la PR de bootstrap) : `mise trust` dans `~/prosperity-sonar`, `systemctl --user enable --now prosperity-sonar.timer`, puis premier passage par `systemctl --user start prosperity-sonar.service` et lecture du journal (`journalctl --user -u prosperity-sonar`). Le nightly ne tourne que si kfzcore est allumé (`Persistent=true`).
- Rien d'autre ne reste dans ce plan.

## Self-Check: PASSED

- Fichiers créés présents : `quality/sonar/{run,sonar-kit,sonar-kit.test,wait,wait.test,config,local,reports,run.test}.ts`, `quality/sonar/scanner.json`, `sonar-project.properties`, `deploy/sonar/prosperity-sonar.{service,timer}`.
- Commits présents : `c2b248e`, `4a8883c`, `b433875`, `aad4be0`, `ed0edad`, `6d42f90`, `1678dca`.
- Passes TDD : un commit `test(01-15)` précède les commits `feat(01-15)`.
