# Quality gate

Une seule commande, `pnpm quality`, juge le dépôt : même commande, mêmes versions d'outils
(épinglés par `mise.toml`, `mise.lock` et `pnpm-lock.yaml`) sur le poste et en CI. **La CI est
le seul juge** : les hooks locaux sont un confort, jamais une garantie (voir « Limites connues »).

Ce document décrit la commande, ses profils et ses checks, la procédure d'approbation et de
fusion réservée à l'humain, le juge de confiance hors PR, les décisions réversibles en vigueur et,
surtout, ce que la gate ne garantit pas.

## 1. Commandes

Toutes les commandes passent par `mise` pour utiliser les versions épinglées.

| Besoin | Commande |
|---|---|
| Gate complète (profil `full`) | `mise exec -- pnpm quality` |
| Profil du pré-push (budget 60 s) | `mise exec -- pnpm quality --profile push` |
| Quelques checks seulement | `mise exec -- pnpm quality --only typecheck,lint,format` |
| Quelques cas de l'auto-test | `GATE_SELFTEST_CASES='<glob>,<glob>' mise exec -- pnpm quality --only selftest` |
| Auto-test seul, cas choisis | `mise exec -- node quality/selftest/run.ts --case '<glob>,<glob>'` |
| Auto-test complet | `mise exec -- node quality/selftest/run.ts` |

`--case` prend une liste de globs séparés par des virgules ; le code de sortie est 2 si un
élément ne retient aucun cas (aucun worktree n'est alors créé). Le résultat se lit dans
`reports/gate.json` (la gate) et `reports/selftest.json` (l'auto-test). Un code de sortie 0
signifie verdict `pass`, 1 verdict `fail`, 2 une erreur d'usage.

Variables d'environnement qui font passer la gate du profil de PR au profil du nightly :

| Variable | Effet |
|---|---|
| `GATE_FORCE_SELFTEST=1` | joue l'auto-test même si aucun chemin protégé n'est modifié |
| `GATE_MUTATION_SCOPE=all` | mutation sur tout le périmètre au lieu du diff depuis la base |
| `FAST_CHECK_NUM_RUNS=1000` | 1000 exécutions fast-check (100 par défaut) |
| `GATE_SEMGREP_PACKS=full` | joue aussi les packs Semgrep du registre (advisory) |
| `GH_TOKEN` | lecture de l'API GitHub par zizmor en ligne |
| `PROSPERITY_HUMAN_GATE_EDIT=1` | autorise un commit **humain** sur un chemin protégé (jamais posée par un agent ni par un outil) |

Pré-commit (lefthook, budget 10 s) : `gitleaks-staged`, `format` (Biome, réécrit et ré-indexe),
`lint-staged` (ESLint avec cache sur les fichiers indexés), `workflow-lint-staged` (actionlint),
`escape-hatches`. Pré-push : `pnpm quality --profile push`.

## 2. Checks

Sévérité `blocking` : un échec fait échouer le verdict. Colonne « pré-push » : `run` joue le
check, `skipped: ci-only` le déclare sauté dans `reports/gate.json` (jamais en silence, D-12).

| Id | Outil | Version | Sévérité | Pré-push | CI (`full`) |
|---|---|---|---|---|---|
| `typecheck` | tsc | `package.json` | blocking | run | joué |
| `lint` | ESLint + typescript-eslint, sonarjs, vitest, eslint-comments | `package.json` | blocking | run | joué |
| `lint-security` | eslint-plugin-security | `package.json` | **advisory** | skipped: ci-only | joué, sans effet sur le verdict |
| `format` | Biome (formateur seul) | `package.json` | blocking | run | joué |
| `arch` | dependency-cruiser | `package.json` | blocking | run | joué |
| `deadcode` | knip | `package.json` | blocking | run | joué |
| `duplication` | jscpd | `package.json` | blocking | run | joué |
| `escape-hatches` | script du dépôt (compteur à cliquet, `quality/baseline.json`) | `quality/` | blocking | run | joué |
| `unit` | Vitest (globs purs à 100 %) | `package.json` | blocking | run | joué |
| `integration` | Vitest + Testcontainers (PostgreSQL 18 réel) | `package.json` | blocking | skipped: ci-only | joué (Docker du runner) |
| `coverage` | `@vitest/coverage-v8`, un processus fusionnant `unit` et `integration` | `package.json` | blocking | skipped: ci-only | joué |
| `mutation` | Stryker | `package.json` | blocking | skipped: ci-only | joué (diff) ; complet au nightly |
| `secrets` | gitleaks | `mise.toml` | blocking | run | joué |
| `sast` | Semgrep, règles du projet (`semgrep/`) | `mise.toml` | blocking | run | joué, plus packs du registre en advisory |
| `cve` | osv-scanner et `pnpm audit --prod` | `mise.toml` / `package.json` | blocking | skipped: ci-only | joué |
| `container` | hadolint | `mise.toml` | blocking | skipped: ci-only | joué |
| `workflow-lint` | actionlint | `mise.toml` | blocking | run | joué |
| `workflow-audit` | zizmor | `mise.toml` | blocking | skipped: ci-only | joué |
| `selftest` | auto-test de la gate (`quality/selftest/`) | `quality/` | blocking | skipped: ci-only | déclenché si un chemin protégé change (D-08) ; forcé au nightly |
| `integrity` | juge d'intégrité (`quality/integrity.ts`) | `quality/` | blocking | skipped: ci-only | rapport de confiance du juge hors PR |
| `approvals` | juge d'approbation (`quality/approvals.ts`) | `quality/` | blocking | skipped: ci-only | rapport de confiance du juge hors PR |
| `deps` | garde des dépendances (`quality/deps-guard.ts`) | `quality/` | blocking | skipped: ci-only | rapport de confiance du juge hors PR |

Les trois derniers (`integrity`, `approvals`, `deps`) **échouent fermés** avec la règle
`missing-trusted-report` quand leur rapport de confiance est absent : c'est voulu tant que
l'étape qui les alimente dans le workflow de PR n'est pas câblée (verrou de la phase 1,
plan 01-14). Hors `pull_request` (nightly), ils rendent `passed` avec la note « hors
pull_request ».

`hadolint` rend `passed` avec la note « non applicable : aucun Containerfile suivi » tant que le
dépôt n'en contient pas (Q9) : jamais `skipped`.

## 3. Rapport `reports/gate.json` et verdict

```json
{
  "profile": "push | full",
  "commit": "<SHA>",
  "base": "<SHA de la base>",
  "generated_at": "<ISO 8601>",
  "verdict": "pass | fail",
  "checks": [
    {
      "check": "lint", "tool": "eslint", "version": "…",
      "severity": "blocking | advisory", "passed": true,
      "status": "passed | failed | skipped",
      "skipped_reason": "ci-only", "note": "…",
      "issues": [{ "rule": "…", "message": "…", "file": "…", "line": 1 }],
      "duration_ms": 0
    }
  ]
}
```

Règle de verdict (D-12) : un check `advisory` n'influe jamais ; un bloquant `failed` fait
échouer ; un bloquant `skipped` fait échouer, sauf en profil `push` hors CI avec la raison
`ci-only`. En CI et en profil `full`, un bloquant sauté fait toujours échouer : aucun saut
silencieux. Lecture de QUAL-01 pour la phase 1 : **même verdict pour chaque check joué en local
et en CI, mêmes versions, même commande** ; le pré-push n'est pas une CI complète.

Un check qui ne peut pas juger (outil absent, version qui ne correspond pas aux épingles, rapport
manquant) échoue avec une règle d'infrastructure (`tool-error`, `tool-version-mismatch`,
`check-crashed`, `config-error`, `missing-trusted-report`…) ; l'auto-test ne la compte jamais
comme une détection.

## 4. Approbation et fusion réservées à l'humain

### 4.1 Procédure d'approbation par label (D-15, qui rétablit D-02)

L'approbation humaine d'une modification de chemin protégé (`gate-change-approved`) ou d'une
dépendance ajoutée ou modifiée (`deps-approved`) est un **label GitHub posé par un humain de
l'allowlist, après le dernier push de la PR, vérifié par la CI**.

1. Relire le diff du SHA de tête exact de la PR : `git fetch`, puis `git switch --detach <sha relu>`.
2. **Après** le dernier push, depuis son propre terminal ou l'interface, poser le ou les labels
   requis : `gh pr edit <n> --add-label gate-change-approved`, `gh pr edit <n> --add-label deps-approved`.
3. Le workflow `quality` se rejoue sur `labeled` ; le juge hors PR (4.2) publie alors le statut
   `quality`.

Un label n'est accepté que si **toutes** ces conditions sont réunies :

- le dernier événement `labeled` de ce label vient d'un acteur de `quality/approvers.json` (lu
  dans `main`, jamais dans la PR ; aujourd'hui `sebc-dev`), pour un label de la liste `labels` ;
- il est postérieur à l'ancre « dernier push » prise **côté serveur** : le premier run
  `pull_request` du SHA de tête sur la branche de la PR, relevé au dernier push forcé. La date du
  commit n'est jamais utilisée, parce que l'auteur la contrôle ;
- le label est encore présent (un `unlabeled` postérieur l'annule).

Tout push suivant invalide l'approbation, y compris la mise à jour de la branche exigée par le
ruleset : le job `reset-approval` retire alors les labels (hygiène ; l'autorité reste la
comparaison d'horodatage du juge). Il faut relire, puis reposer le label.

Raisons de refus, telles qu'elles apparaissent dans le rapport d'approbation :

| Raison | Sens |
|---|---|
| `approval-missing` | aucun label requis n'a été posé |
| `approval-removed` | le label a été posé puis retiré |
| `approval-actor-not-allowed` | le label a été posé par un acteur hors de `approvers.json` (par exemple `github-actions[bot]`) |
| `approval-stale` | le label précède l'ancre du dernier push |
| `approval-no-anchor` | aucune ancre serveur n'a pu être établie pour ce SHA |
| `approval-head-moved` | la tête de la PR a changé entre la collecte des preuves et le jugement |
| `approval-evidence-invalid` | les preuves collectées sont illisibles ou incohérentes |
| `approvers-config-missing` | `quality/approvers.json` est absent de la base |

Contrôle local en deux temps (la collecte lit l'API en lecture seule, le jugement n'a pas de
jeton) :

```sh
node quality/approval-evidence.ts --repo sebc-dev/prosperity --pr <n> --head-sha <sha> --out <preuves>
node quality/approvals.ts --base-dir . --evidence <preuves> --head-sha <sha> --pr <n> --out <rapport>
```

Autres règles de la procédure :

- Modifier l'allowlist `quality/approvers.json` passe par une PR approuvée par un acteur déjà listé.
- **L'agent ne crée, ne pose ni ne retire aucun label** (D-03) ; le garde Bash et les règles deny
  le lui refusent (voir « Limites connues » pour la portée réelle de ce refus).
- Un commit humain sur un chemin protégé s'écrit `PROSPERITY_HUMAN_GATE_EDIT=1 git commit …`.
- **La fusion est réservée à l'humain** : règles deny et garde Bash sur `gh pr merge`, auto-fusion
  désactivée sur le dépôt.

### 4.2 Juge de confiance hors PR (`quality-verdict`)

Dans la PR, le workflow `quality` joue `pnpm quality` mais **ne fait pas foi**, parce qu'il
s'exécute dans la version de la PR : celle-ci peut le réécrire. Le seul check requis est le statut
`quality`, publié par le workflow **`quality-verdict`** :

- déclencheur `workflow_run` sur la fin de `quality` : GitHub lit sa définition sur la **branche
  par défaut**, une PR ne peut donc ni la modifier ni la désactiver pour elle-même ;
- il publie le statut avec le jeton d'une **application GitHub dédiée**, dont la clé privée vit
  dans l'environnement `gate-verdict`, restreint à `main` ;
- il collecte lui-même, en lecture seule et avec le seul jeton du workflow, les preuves
  d'approbation (tête de la PR, labels, événements, runs), puis rejoue le juge d'approbation sans
  jeton, l'intégrité et les dépendances **depuis la base**, sur la tête de la PR lue comme
  *données* : aucun fichier de la PR n'est exécuté ;
- mise en place : ruleset transitoire `gate`, puis ruleset final exigeant `quality` avec pour
  source l'application (plan 01-14). Le job de la PR s'appelle `quality` jusqu'à ce plan, puis
  `gate`.

### 4.3 Passage manuel de démonstration (D-07b)

`node quality/selftest/demo-prs.ts <scénario>` ouvre des PR de démonstration pour ce que seul
GitHub prouve. **Il est lancé par l'humain** : il refuse de tourner si `PROSPERITY_HUMAN_GATE_EDIT`
ne vaut pas `1` dans l'environnement de l'appelant et ne la pose jamais lui-même. Il ne crée, ne
pose ni ne retire jamais de label avec le jeton de l'humain : il imprime les gestes que l'humain
fait. Scénarios : `blocked-check`, `human-label`, `bot-label`, `deps-unapproved`,
`workflow-rewrite`, `deps-too-recent` (local seulement, ne committe rien). Les labels
`gate-change-approved` et `deps-approved` doivent exister dans le dépôt (créés par l'humain).

## 5. Décisions réversibles en vigueur

- **Approbation par label (D-15)** : réversible vers le commit d'approbation signé par clé
  matérielle (D-14) sans changer le schéma de `reports/approvals.json` ni ses consommateurs
  (`integrity`, `deps-guard`, `verdict`). La signature matérielle reste l'option de durcissement ;
  une clé `ed25519-sk` est disponible. Les refus de l'agent hérités de D-14 (signature de commit ou
  de tag, configuration de signature, sujet `gate-approval:`, `ssh-keygen`, `ssh-add`, API des clés
  du compte) sont conservés comme **hygiène**.
- **Disposition `src/`** (`quality/layout.json`, Q5) : sont purs `src/shared/**` et
  `src/modules/*/domain/**` ; la mutation vise en plus `src/modules/*/application/**`. Changer ces
  globs touche des fichiers protégés.
- **Packs Semgrep (Q4, plan 01-04)** : les règles du projet (`semgrep/`) sont bloquantes ; les
  packs du registre (`p/typescript`, `p/nodejs`, `p/jwt`, `p/owasp-top-ten`) sont joués en profil
  `full` et au nightly, leurs résultats `ERROR` sont listés en advisory (`pack:<id>`), sans effet
  sur le verdict. Écart assumé à CLAUDE.md §10.2 : verdict déterministe, aucune dépendance réseau
  pour le bloquant, licence des règles du registre. Une règle utile est promue en la réécrivant
  dans `semgrep/` par une PR approuvée.
- **hadolint sans Containerfile (Q9)** : `passed` avec la note « non applicable », jamais `skipped`.
- **`knip --production` différé (Q6)** : non activé en phase 1 (les exports du canari ne sont
  utilisés que par des tests) ; à introduire en phase 2 avec `src/index.ts`.
- **Périmètre de couverture** (décision humaine) : le plancher global 85 % lignes / 80 % branches
  porte sur tout `src/**`, infrastructure base de données comprise, et il est jugé par le check
  `coverage`, un seul processus Vitest qui joue les projets `unit` et `integration` et fusionne
  leur couverture. Le check `unit` ne juge que les globs purs à 100 %.
- **Historique hérité** : les commits atteignables depuis l'ancien `main` (`LEGACY_MAIN_SHA`) sont
  exclus du scan gitleaks ; le scan reste complet pour tout commit nouveau.
- **Stryker, bug #6335** : mitigation `disableBail: true` retenue au plan 01-03 ; son efficacité
  n'est pas démontrée (le bug ne s'est pas reproduit en 20 exécutions) et le seuil `break` reste à
  80. Le fichier d'incrémental n'est jamais committé (bug #6004).
- **SonarQube (D-16)** : analyse advisory hébergée sur le homelab, hors CI GitHub et hors verdict.

## 6. Nightly

Le workflow `nightly` (planifié chaque jour à 03:23 UTC et déclenchable à la main, runner
`ubuntu-24.04`, lecture seule) rejoue la gate complète avec `GATE_FORCE_SELFTEST=1`,
`GATE_MUTATION_SCOPE=all`, `FAST_CHECK_NUM_RUNS=1000` et `GATE_SEMGREP_PACKS=full`, puis lance
`trufflehog` en advisory. Il publie l'artefact `gate-nightly` (`gate.json`, `selftest.json`,
`trufflehog.json`). Un workflow planifié tourne sur la branche par défaut : il ne s'exécute
qu'après la fusion de la PR de bootstrap.

## Analyse SonarQube (advisory, D-16)

### Rôle

SonarQube Community, hébergé sur le homelab (kfzserver), donne à l'humain un tableau de bord et un
historique (dette, points chauds de sécurité à revoir, duplication, couverture). Il est
**advisory** : aucun check de `pnpm quality` ne le lit, le verdict ne change pas, aucune PR n'est
bloquée, rien ne tourne dans la CI GitHub, et il n'y a ni runner auto-hébergé ni job GitHub qui
joindrait le homelab (D-13). `pnpm sonar` refuse de tourner quand `CI` ou `GITHUB_ACTIONS` est défini.

### Déclenchement

| Besoin | Commande |
|---|---|
| Analyse à la demande, depuis le poste (mode SSH, défaut) | `mise exec -- pnpm sonar` |
| Rapports et invocation masquée, sans réseau | `mise exec -- pnpm sonar --dry-run` |
| Analyse locale sur la machine Sonar (nightly, ou à la main sur kfzserver) | `SONAR_MODE=local mise exec -- pnpm sonar` |
| Analyse nightly de `main` | timer systemd utilisateur de kfzserver (`deploy/sonar/`) |

Codes de sortie : **0** analyse traitée par le serveur (tâche du moteur de calcul `SUCCESS`) ou, en
`--dry-run`, rapports produits ; **1** rapport manquant, scanner en échec, tâche `FAILED`,
`CANCELED` ou expirée (10 min) ; **2** configuration refusée (CI, mode inconnu, cible SSH ou
fichier d'environnement non conforme, image non épinglée, propriété interdite).

Le script produit d'abord les rapports sous `reports/sonar/` (ignoré par git) : ESLint en JSON avec la
configuration bloquante puis avec `eslint.security.config.mjs`, et la couverture LCOV de Vitest
(projets `unit` et `integration`, ou `unit` seul avec `SONAR_COVERAGE=unit`). Un LCOV absent arrête
tout : une couverture à 0 % trompeuse n'est jamais publiée. Les chemins absolus des rapports sont
réécrits en chemins relatifs à la racine.

### Deux modes d'exécution

- **Mode SSH (défaut)** : décision du 2026-11-22. Le serveur Sonar n'écoute que sur la boucle locale
  de kfzserver. Depuis le poste, `pnpm sonar` produit les rapports, envoie par `tar` sur SSH les seules
  entrées utiles (`src`, `quality`, `test`, `tsconfig.json`, `package.json`,
  `sonar-project.properties`, `reports/sonar`) dans un dossier jetable de kfzserver, y lance le conteneur
  du scanner, attend la tâche du serveur par SSH puis supprime le dossier. Le **jeton ne vit que sur
  kfzserver** : le conteneur le reçoit par `--env-file`, la lecture de la tâche par `curl -K -` (jamais en
  argument de commande). Les scripts distants arrivent sur l'entrée standard de `ssh <hôte> sh -s` et ne
  sont construits que de valeurs validées. Une vérification préalable, avant les rapports, contrôle le
  fichier d'environnement distant (mode 0600, clés présentes, sans guillemet ni espace, adresse en
  `https://` ou en `http://` sur la boucle locale) et l'accès de l'utilisateur au moteur de conteneur.
- **Mode local** (`SONAR_MODE=local`) : le scanner tourne sur la machine qui lance la commande ; hôte
  et jeton viennent de l'environnement ou de `SONAR_ENV_FILE` (défaut `~/.config/prosperity-sonar/env`),
  refusé s'il est dans le dépôt ou lisible par le groupe ou les autres. `http://` n'est accepté que sur la
  boucle locale (ou avec `SONAR_ALLOW_INSECURE_HTTP=1`). C'est le mode du timer nightly.

### Configuration hors dépôt

| Variable | Rôle |
|---|---|
| `SONAR_MODE` | `ssh` (défaut) ou `local` |
| `SONAR_SSH_HOST` | cible SSH (défaut `kfzserver`, ou `user@hôte`) ; jamais une option `ssh` |
| `SONAR_REMOTE_ENV_FILE` | fichier d'environnement distant (défaut `~/.config/prosperity-sonar/env`) |
| `SONAR_CONTAINER_ENGINE` | `docker` (défaut en mode SSH) ou `podman` (premier trouvé en mode local, Podman d'abord) |
| `SONAR_COVERAGE` | `full` (défaut, `unit` et `integration`) ou `unit` |
| `SONAR_HOST_URL`, `SONAR_TOKEN`, `SONAR_ENV_FILE`, `SONAR_ALLOW_INSECURE_HTTP` | mode local seulement |

Sur kfzserver, `~/.config/prosperity-sonar/env` (mode 0600) contient `SONAR_HOST_URL=http://localhost:9000`
et `SONAR_TOKEN=…` (jeton d'analyse **de projet**, un par machine pour les révoquer séparément ; valeurs
sans guillemet). Pour `SONAR_COVERAGE=full` en mode local sous Podman : `DOCKER_HOST` vers le socket
utilisateur de Podman et `TESTCONTAINERS_RYUK_DISABLED=true` dans le même fichier. L'adresse du serveur
n'entre jamais dans un fichier suivi.

### Installation sur kfzserver (nightly)

Prérequis : `git`, `mise` dans `~/.local/bin`, un moteur de conteneur utilisable **sans privilèges** par
l'utilisateur du timer (membre du groupe du moteur, ou Podman sans privilèges), `loginctl enable-linger`.
Clone en lecture seule : `git clone https://github.com/sebc-dev/prosperity.git ~/prosperity-sonar`.
Copier `deploy/sonar/prosperity-sonar.service` et `.timer` dans `~/.config/systemd/user/`, adapter le
chemin de `mise`, puis `systemctl --user daemon-reload`. **Après la fusion de la PR de bootstrap seulement**
(avant, `main` n'a pas `pnpm sonar`) : `mise trust` dans le clone, `systemctl --user enable --now
prosperity-sonar.timer`, premier passage par `systemctl --user start prosperity-sonar.service`, journal par
`journalctl --user -u prosperity-sonar`. L'unité fixe `SONAR_MODE=local` : sur kfzserver le scanner tourne
localement.

### Image du scanner et choix

L'image officielle `sonarsource/sonar-scanner-cli` est épinglée **par digest** dans
`quality/sonar/scanner.json` (étiquette complète, date de publication ; au moins 7 jours, comme
`minimumReleaseAge`). `pnpm sonar` refuse une image sans digest, `latest` ou d'un autre dépôt. La mise
à jour est une PR approuvée par le label `gate-change-approved` (`quality/**` est protégé). Choix du
scanner : un conteneur plutôt que le paquet npm du scanner (nouvelle dépendance soumise à QUAL-09, moteur et
JRE téléchargés hors lockfile) ou un binaire épinglé par `mise` (installé aussi en CI par `mise-action`,
contraire à D-16). Coût : un moteur de conteneur sur la machine qui exécute le scanner.

### Recouvrement avec la gate

Les règles JS/TS de Sonar sont celles d'`eslint-plugin-sonarjs`, déjà **bloquant** ; la duplication
recoupe `jscpd` (**bloquant** sur les nouveaux clones) ; la couverture affichée recoupe les seuils Vitest
(**bloquants**). Sonar ajoute le tableau de bord, l'historique, la revue des points chauds de sécurité et
l'import des avertissements advisory d'`eslint-plugin-security` (issues externes). Référence :
`origin/main:docs/recherches/2026-09-12-quality-gate-sonar-sans-serveur.md`.

### `sonar-project.properties` : chemin protégé

Ce fichier ne peut pas affaiblir la gate bloquante, mais il décide de ce que montre le tableau de bord
que l'humain relit et, sans garde, pourrait orienter le jeton (hôte, proxy). Il est protégé (deny agent,
CODEOWNERS, intégrité, dérivés de `quality/protected-paths.json`), comme `quality/sonar/**` et
`deploy/sonar/**`. `pnpm sonar` refuse en plus un fichier qui définit `sonar.host.url`, `sonar.token`,
`sonar.login`, `sonar.password` ou une propriété `sonar.scanner.proxy*`, `http.proxy*`, `https.proxy*`.

### Limites de l'analyse Sonar

- **Le nightly exécute le code et les tests de `main` sur kfzserver** : même confiance que le déploiement
  de la phase 2 (code fusionné par l'humain après la gate). Rien d'une PR, d'un fork ni d'une branche de
  travail n'y est exécuté. En mode SSH, le poste n'y envoie que ses sources et rapports, sans exécuter de code.
- **Le jeton n'est pas une barrière contre l'agent du poste.** En mode SSH il ne quitte pas kfzserver
  (jamais copié sur le poste, ni dans un argument ou un journal), mais l'accès SSH que le poste a sur
  kfzserver permettrait de lire le fichier. Jeton d'analyse d'un seul projet, révocable dans Sonar.
- **Le scanner partage le réseau de l'hôte** (`--network host`) pour joindre un serveur qui n'écoute que
  sur sa boucle locale.
- **Analyse sans `node_modules`** en mode SSH (non envoyé) : l'analyse de types de Sonar est moins précise.
- **Accès au moteur de conteneur** : sur kfzserver, l'utilisateur SSH doit pouvoir parler au démon
  (groupe `docker`) ou disposer de Podman sans privilèges ; la vérification préalable le signale
  (`accès refusé au moteur de conteneur distant`).
- **Vitest peut rendre 1** (test ou seuil de couverture) : le LCOV est publié quand même, avec un
  avertissement, l'analyse étant advisory.
- **gitleaks** : la règle par défaut `sonar-api-token` arrête `SONAR_TOKEN=sqp_…` mais pas un jeton nu
  sans mot-clé.
- La Community Build n'analyse qu'une branche (ici `main`) et n'a pas d'analyse de propagation (taint).

## Limites connues

La gate réduit le risque, elle ne l'élimine pas. Chaque limite est suivie du contrôle qui la
rattrape ; aucune ne doit être lue comme « sans danger ».

1. **Jeton `gh` partagé : risque accepté de D-15.** L'agent utilise le jeton `gh` administrateur de
   `sebc-dev`. Un label qu'il poserait avec ce jeton serait **indiscernable d'un label humain**
   (même acteur, même API), et un agent qui contournerait à la fois les règles deny et le garde
   Bash pourrait aussi modifier le ruleset, les réglages Actions ou l'environnement du juge.
   *Contrôles :* règles deny sur les labels, l'API en écriture et la fusion (D-03) et garde Bash
   (`quality/agent-guard/`), actifs depuis le verrou du plan 01-14 ; **avant le verrou, seule la
   relecture humaine protège** ; fusion humaine ; relecture des événements de labels de la PR.
   *Atténuations durables hors phase 1 :* un jeton distinct non administrateur, ou le commit
   d'approbation signé par clé matérielle (D-14), sans changement du schéma de
   `reports/approvals.json`.
2. **Une règle deny n'est pas une frontière de sécurité.** `sh -c '…'`, un binaire appelé par son
   chemin absolu ou `git -C . push` ne sont pas arrêtés par une règle de permission ; le garde
   Bash n'est pas exhaustif. *Contrôle :* la CI est le seul juge ; le job d'intégrité et le juge
   hors PR rattrapent les contournements exotiques.
3. **Les hooks locaux se désactivent** (`LEFTHOOK=0`, `--no-verify`). *Contrôle :* la CI rejoue
   tout ; `--no-verify` et le push forcé sont refusés à l'agent (règles deny et garde Bash).
4. **`.claude/settings.local.json` pourrait porter `disableAllHooks`**, ce qui désarmerait les
   hooks de l'agent. *Contrôle :* règles deny sur `.claude/settings*.json` ; le garde ne protège
   que la session locale, pas la CI.
5. **Une PR peut réécrire son propre workflow `pull_request`.** Son job n'est donc pas requis.
   *Contrôle :* le statut requis `quality` vient du juge hors PR, qui exige
   `gate-change-approved` pour toute modification de `.github/**` ; la démonstration
   `workflow-rewrite` en fait la preuve. **Avant la fusion de la PR de bootstrap, ce juge
   n'existe pas encore sur `main`** et seule la relecture humaine du plan 01-14 (D-01) protège.
6. **Le code de la PR s'exécute dans le job de la PR**, tests compris, et pourrait influencer des
   checks joués dans le même job (le juge hors PR ne rejoue que approbations, intégrité et
   dépendances). *Contrôle :* la configuration et les scripts de la gate sont des chemins protégés ;
   les tests sont jugés par la mutation et les règles de lint des tests ; la relecture humaine
   reste nécessaire pour un changement suspect de `src/` ou `test/`.
7. **PR de fork.** Le jeton est en lecture seule, donc `reset-approval` échoue sans conséquence ;
   l'horodatage reste l'autorité. D-13 interdit le runner auto-hébergé et `pull_request_target`.
8. **Chaque pose ou retrait de label rejoue la gate complète** (coût en minutes de CI), parce que
   le workflow `quality` s'exécute sur `labeled` et `unlabeled`.
9. **`workflow-audit` rend `passed` quand zizmor ne peut pas valider un workflow** (un simple
   avertissement est émis). *Contrôle :* `workflow-lint` (actionlint) reste bloquant, et
   `.github/**` exige `gate-change-approved`. Cette limite a été relevée par l'auto-test du plan 01-12.
10. **`sast` peut rendre une erreur d'infrastructure passagère** (`tool-error`, téléchargement
    du registre Semgrep) : le check échoue alors fermé et se relance ; il ne rend jamais `passed`
    sur un scan qui n'a pas eu lieu.
11. **Première PR jugée en mode amorçage.** Le verrou (deny agent, CODEOWNERS, job d'intégrité,
    ruleset sur `main`) n'est actif qu'au plan 01-14 ; d'ici là les chemins protégés se modifient
    librement (D-01) et `integrity`, `approvals`, `deps` échouent fermés avec
    `missing-trusted-report`.
12. **Un seul collaborateur.** GitHub refuse l'auto-approbation : la revue CODEOWNERS native ne
    peut pas servir, CODEOWNERS reste une documentation et un filet si un collaborateur arrive.
13. **La mutation ne juge que le périmètre pur** (`layout.mutate`) ; le reste de `src/` est jugé
    par les tests, la couverture (plancher 85/80) et la relecture humaine.
14. **Vitest lancé hors de `pnpm quality` dans un hook git.** `pnpm quality` retire de son
    environnement les variables qui désignent le dépôt de l'appelant (`GIT_DIR`, `GIT_WORK_TREE`…)
    avant de jouer les checks : sans cela, les tests qui créent un dépôt jetable commitaient dans la
    branche de l'appelant lors d'un `git push` depuis un worktree lié. Une commande `vitest` appelée
    directement depuis un hook n'a pas cette protection. *Contrôle :* les hooks du dépôt n'appellent
    que `pnpm quality` ou `node quality/run.ts`.
15. **Les labels d'approbation doivent exister dans le dépôt.** Tant que `gate-change-approved` et
    `deps-approved` n'ont pas été créés par l'humain, le job `reset-approval` échoue (« not found »)
    sans conséquence (`continue-on-error`) et aucun label ne peut être posé.
