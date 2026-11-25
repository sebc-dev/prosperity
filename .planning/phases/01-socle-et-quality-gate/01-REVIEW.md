---
phase: 01-socle-et-quality-gate
reviewed: 2026-11-25T00:00:00Z
depth: standard
files_reviewed: 111
files_reviewed_list:
  - .dependency-cruiser.cjs
  - .github/CODEOWNERS
  - db/migrations/0001_foundation.sql
  - deploy/sonar/prosperity-sonar.service
  - deploy/sonar/prosperity-sonar.timer
  - eslint.config.mjs
  - eslint.security.config.mjs
  - quality/agent-guard/bash-guard.test.ts
  - quality/agent-guard/bash-guard.ts
  - quality/agent-guard/gh-rules.ts
  - quality/agent-guard/git-rules.ts
  - quality/agent-guard/misc-rules.ts
  - quality/agent-guard/precommit-protected.test.ts
  - quality/agent-guard/precommit-protected.ts
  - quality/agent-guard/shell-split.ts
  - quality/agent-guard/write-rules.ts
  - quality/approval-evidence-collect.test.ts
  - quality/approval-evidence-fixtures.ts
  - quality/approval-evidence.test.ts
  - quality/approval-evidence.ts
  - quality/approvals-cli.test.ts
  - quality/approvals-fixtures.ts
  - quality/approvals-judge.test.ts
  - quality/approvals.test.ts
  - quality/approvals.ts
  - quality/check-kit.ts
  - quality/checks/approvals.test.ts
  - quality/checks/approvals.ts
  - quality/checks/arch.ts
  - quality/checks/container.ts
  - quality/checks/coverage.ts
  - quality/checks/cve.ts
  - quality/checks/deadcode.ts
  - quality/checks/deps.test.ts
  - quality/checks/deps.ts
  - quality/checks/duplication.ts
  - quality/checks/escape-hatches.ts
  - quality/checks/format.ts
  - quality/checks/integration.ts
  - quality/checks/integrity.ts
  - quality/checks/lint-security.ts
  - quality/checks/lint.ts
  - quality/checks/mutation.ts
  - quality/checks/sast.ts
  - quality/checks/secrets.ts
  - quality/checks/selftest.test.ts
  - quality/checks/selftest.ts
  - quality/checks/typecheck.ts
  - quality/checks/unit.ts
  - quality/checks/workflow-audit.ts
  - quality/checks/workflow-lint.ts
  - quality/deps-diff.ts
  - quality/deps-guard-cli.test.ts
  - quality/deps-guard.test.ts
  - quality/deps-guard.ts
  - quality/escape-hatches.test.ts
  - quality/escape-hatches.ts
  - quality/gate-report.ts
  - quality/integrity-fs.ts
  - quality/integrity.test.ts
  - quality/integrity.ts
  - quality/lock.test.ts
  - quality/pnpm-policy.ts
  - quality/protected-paths.ts
  - quality/run.test.ts
  - quality/run.ts
  - quality/selftest/case-runner.ts
  - quality/selftest/cases.ts
  - quality/selftest/context.ts
  - quality/selftest/cycle.test.ts
  - quality/selftest/demo-prs.ts
  - quality/selftest/fixture.ts
  - quality/selftest/run.test.ts
  - quality/selftest/run.ts
  - quality/selftest/worktrees.ts
  - quality/sonar/config.ts
  - quality/sonar/local.ts
  - quality/sonar/reports.ts
  - quality/sonar/run.test.ts
  - quality/sonar/run.ts
  - quality/sonar/sonar-kit.test.ts
  - quality/sonar/sonar-kit.ts
  - quality/sonar/wait.test.ts
  - quality/sonar/wait.ts
  - quality/tools.test.ts
  - quality/tools.ts
  - quality/verdict-cli.test.ts
  - quality/verdict-fixtures.ts
  - quality/verdict-io.test.ts
  - quality/verdict-io.ts
  - quality/verdict-rules.ts
  - quality/verdict.test.ts
  - quality/verdict.ts
  - quality/vitest-kit.ts
  - semgrep/prosperity.ts
  - src/db/migrate.ts
  - src/db/provision.ts
  - src/db/sql-migration-provider.ts
  - src/shared/money/allocate.properties.test.ts
  - src/shared/money/allocate.test.ts
  - src/shared/money/allocate.ts
  - src/shared/money/money.properties.test.ts
  - src/shared/money/money.test.ts
  - src/shared/money/money.ts
  - stryker.config.mjs
  - test/db.ts
  - test/foundation.int.test.ts
  - test/global-setup.ts
  - test/meta.int.test.ts
  - test/setup/fast-check.ts
  - vitest.config.ts
findings:
  critical: 1
  warning: 7
  info: 7
  total: 15
  necessity: 0
status: issues_found
---

# Phase 01 : rapport de revue de code

**Revue :** 2026-11-25
**Profondeur :** standard (lecture complète des modules de jugement, vérifications empiriques ciblées)
**Fichiers revus :** 111
**Statut :** issues_found

## Résumé

La phase construit la gate elle-même (runner, checks, juge d'intégrité, approbation par label D-15, verdict hors PR, garde de dépendances, garde Bash de l'agent, auto-test, Sonar advisory), le canari monétaire et le socle base de données. La conception est sérieuse : échec fermé quasi partout (rapport illisible = absent, code de sortie non nul sans issue = échec), juges rejoués depuis la branche par défaut sur la tête lue comme données, jetons retirés de l'environnement des juges, écritures atomiques, `computeVerdict` pur. L'arithmétique monétaire (`allocate`, `parseAmount`, `formatMoney`) ne contient pas de bogue prouvable.

Le défaut majeur est dans le maillon central de toute la chaîne de confiance : la correspondance des chemins protégés. `isProtected` s'appuie sur `path.matchesGlob` de Node, qui n'applique ni `**` ni `*` aux segments commençant par un point. Tout fichier caché sous un dossier protégé (`quality/checks/.x.ts`, `.github/workflows/.x.yml`) échappe donc au juge d'intégrité sans label `gate-change-approved`, et `discoverChecks` charge justement les fichiers cachés de `quality/checks/` (CR-01, reproduit).

Les autres constats : un trou dans l'ancre « dernier push » de l'approbation (WR-01), une expiration de `runTool` qui peut ne jamais se résoudre (WR-02), un runner qui rend `pass` avec zéro check (WR-03), un pré-commit aveugle aux renommages (WR-04), le jeton Sonar exposé aux scripts d'installation (WR-05), les erreurs d'analyse Semgrep de niveau `warn` ignorées (WR-06, à confirmer) et une lecture du worktree qui suit les liens symboliques côté intégrité mais pas côté dépendances (WR-07).

Hors périmètre rappelé : le test de parallélisme du selftest (e241321), les ~198 constats `lint-security`, l'override `minimatch`, le pin pnpm 12.18.0, la limite connue 9 de `workflow-audit`.

Deux changements de la PR #301 n'existent que sur `origin/main` et ont été relus via `git show origin/main:<chemin>` : `quality/sonar/reports.ts` (option `--coverage.reportOnFailure`, absente de HEAD) et `deploy/sonar/prosperity-sonar.service` (ligne `Environment=PATH=…`, absente de HEAD). La branche courante est donc en retard sur ces deux fichiers (voir IN-01).

Le référentiel de nécessité (`necessity-review.md`) a été lu ; aucun constat de nécessité n'est retenu (les gardes lues franchissent toutes une frontière de confiance ou sont une défense en profondeur délibérée).

## Critical Issues

### CR-01 : `isProtected` ignore les fichiers cachés — contournement du juge d'intégrité et exécution de code non protégé dans la gate

**File:** `quality/protected-paths.ts:44-45` (cause) ; effets dans `quality/integrity.ts:49-61`, `quality/checks/selftest.ts:50-54`, `quality/agent-guard/precommit-protected.ts:22`, `quality/agent-guard/write-rules.ts:55-67` ; chargeur : `quality/run.ts:79-83`
**Issue:** `isProtected` appelle `matchesGlob` de `node:path/posix`, qui n'a pas d'option `dot` : `**` et `*` ne couvrent jamais un segment commençant par `.`. Vérifié sur Node 26.13.0 :

- `matchesGlob('quality/checks/.evil.ts', 'quality/**')` donne `false` ;
- `matchesGlob('.github/workflows/.evil.yml', '.github/**')` donne `false` ;
- `matchesGlob('mise/.x', 'mise/**')`, `matchesGlob('deploy/.x.service', 'deploy/**')` donnent `false`.

Reproduction avec le vrai `quality/integrity.ts` : une base contenant `quality/protected-paths.json`, `quality/thresholds.json`, `quality/checks/a.ts` et `.github/workflows/quality.yml`, et une tête qui ajoute `quality/checks/.evil.ts` et `.github/workflows/.evil.yml`. Le juge sort 0 avec `"status": "passed", "issues": []` et aucun label.

L'impact dépasse la liste des fichiers : `discoverChecks` (`quality/run.ts:79-83`) lit tout `quality/checks/` avec `readdir` et ne garde que `name.endsWith('.ts')`. Un `quality/checks/.x.ts` est donc **importé et exécuté** par `pnpm quality`. Son code de module peut poser `process.on('exit', () => { process.exitCode = 0 })`, réécrire `reports/gate.json` ou exporter un `check` qui rend `passed`. Le run `quality` de la PR sort alors `success` (`gate-not-success` ne se déclenche pas) et le verdict hors PR ne voit aucun écart d'intégrité : tous les checks de la gate (lint, tests, mutation, secrets, SAST…) deviennent contournables sans label humain. La même lacune désarme le déclencheur du selftest (D-08), le pré-commit de l'agent et la garde `bash-guard` (les écritures `cp x quality/checks/.y.ts` ne sont pas vues comme protégées).

CODEOWNERS (sémantique gitignore) couvre bien ces chemins ; seule l'implémentation du juge diverge de la liste qu'elle est censée appliquer.
**Fix:** remplacer `matchesGlob` par un comparateur qui traite les points comme des caractères ordinaires, par exemple `minimatch(path, glob, { dot: true })` (déjà présent transitivement ; l'ajouter en dépendance directe avec approbation `deps-approved`), ou une conversion glob vers expression régulière locale (`**` = `.*`, `*` = `[^/]*`). Ajouter dans `quality/lock.test.ts` un test paramétré : pour chaque glob de `protected-paths.json`, vérifier qu'un chemin d'exemple caché sous le préfixe est protégé. En défense en profondeur, filtrer `discoverChecks` sur `!name.startsWith('.')` et fixer la liste d'ids attendue (voir WR-03).

## Warnings

### WR-01 : ancre « dernier push » = plus ancien run du SHA ; un fast-forward vers un SHA déjà vu conserve une ancre ancienne

**File:** `quality/approvals.ts:62-78`
**Issue:** `lastPushAnchor` vaut `max(min(created_at des runs du SHA de tête), dates des head_ref_force_pushed)`. Les poussées en fast-forward n'émettent pas `head_ref_force_pushed` et le `min` ne regarde que le premier run de ce SHA. Séquence qui garde une approbation périmée valable : (1) l'auteur pousse Z (descendant de X), run R_Z à t0 ; (2) il réinitialise la branche sur X par force-push (événement à t1) ; (3) le mainteneur pose le label sur X à t2 > t1 ; (4) l'auteur repousse Z en fast-forward à t3. L'ancre vaut `max(t0, t1) = t1 < t2` : le label, posé sur X, est jugé frais pour Z. La seule protection restante est le job `reset-approval`, qui vit dans `quality.yml` de la PR (que l'auteur contrôle, quitte à faire approuver le changement de workflow par le même label) et que le commentaire du fichier dit précisément ne pas considérer comme l'autorité. L'exploitation exige un force-push de l'auteur, que la garde agent refuse (mais cette garde est consultative, D-04).
**Fix:** ancrer sur l'instant où la tête a pris la valeur courante, pas sur le premier run du SHA : par exemple le `created_at` du **dernier** run `pull_request` du SHA dont l'action est `opened|synchronize|reopened` (champ `triggering_actor`/événement non disponible : à défaut, exclure les runs déclenchés par `labeled`/`unlabeled` en lisant `display_title`/`run_attempt`, ou stocker le SHA dans le texte du label via un commentaire d'approbation signé). Au minimum, ajouter à l'ancre la date du dernier événement `head_ref_force_pushed` **ou** `head_ref_restored` et documenter la limite dans `01-14-SUMMARY.md`.

### WR-02 : le délai maximal de `runTool` ne se résout pas si un petit-enfant garde les tubes ouverts

**File:** `quality/tools.ts:84-109`
**Issue:** à l'expiration, `child.kill('SIGKILL')` ne tue que le processus direct ; la promesse n'est résolue que par l'événement `close`, qui attend la fermeture de stdout/stderr. Vitest (workers), Stryker (processus enfants), `pnpm`, `mise` qui n'`exec` pas, ou un scanner de conteneur héritent des descripteurs : tuer le parent laisse les petits-enfants vivants, `close` n'arrive jamais et la gate reste suspendue jusqu'au `timeout-minutes` du job (20 min en PR, 60 en nightly). La garantie documentée (« délai maximal appliqué, SIGKILL, code 124 ») n'est alors pas tenue ; en local, le pré-push se fige.
**Fix:**
```ts
const child = spawn(opts.command, [...opts.args], { /* … */ detached: true });
const timer = setTimeout(() => {
  timedOut = true;
  try { process.kill(-child.pid!, 'SIGKILL'); } catch { child.kill('SIGKILL'); }
}, timeoutMs);
// et résoudre aussi sur 'exit' après une courte garde si 'close' tarde
child.on('exit', () => setTimeout(() => finish(timedOut ? 124 : /* code */ 1, ''), 2000).unref());
```
(le `!` est à remplacer par une garde `child.pid === undefined`, la règle `no-non-null-assertion` du projet l'interdit). Ajouter un test avec un enfant qui lance un petit-enfant `sleep` détenant stdout.

### WR-03 : le runner rend `pass` (exit 0) quand aucun check n'est exécuté

**File:** `quality/run.ts:50-55`, `quality/run.ts:81-96`, `quality/gate-report.ts:84-90`
**Issue:** `--only ,` (ou `--only ""`) donne `only = []`, `selectChecks` renvoie `[]`, `runPool` crée zéro worker et `computeVerdict(profile, [], inCi)` vaut `pass` car `[].some(...)` est faux. De même, si `quality/checks/` est vide ou ne contient plus que des fichiers filtrés, la gate est verte. Le seul garde-fou est le juge d'intégrité sur les chemins protégés (voir CR-01 : lui-même contournable). Le runner n'a aucune liste attendue de checks.
**Fix:** échec explicite quand `results.length === 0`, et en profil `full` sans `--only` comparer les ids découverts à une liste figée (par exemple `quality/checks.manifest.json`, chemin protégé) : un check manquant = `failed` avec la règle `check-missing:<id>`. Rejeter `--only` vide avec `UsageError`.

### WR-04 : le pré-commit et le déclencheur du selftest ne voient pas un fichier protégé renommé hors de son dossier

**File:** `quality/agent-guard/precommit-protected.ts:18`, `quality/checks/selftest.ts:27`
**Issue:** `git diff --cached --name-only --diff-filter=ACMRD` et `git diff --name-only base...HEAD` détectent les renommages par défaut (`diff.renames`) et n'impriment alors que le **nouveau** chemin. `git mv quality/checks/lint.ts misc/lint.ts` n'est donc listé que comme `misc/lint.ts` (non protégé) : le pré-commit laisse passer sans `PROSPERITY_HUMAN_GATE_EDIT`, et `isSelftestTriggered` ne se déclenche pas. Le juge d'intégrité rattrape la suppression côté CI (la base liste l'ancien chemin), mais la couche 3 de D-04 et le déclencheur D-08 sont incomplets.
**Fix:** ajouter `--no-renames` aux deux commandes `git diff` (et `-c core.quotepath=off` n'est pas nécessaire grâce à `-z`).

### WR-05 : `EnvironmentFile` expose `SONAR_TOKEN` à `mise install` et aux scripts d'installation de `pnpm`

**File:** `deploy/sonar/prosperity-sonar.service:16-24`
**Issue:** `EnvironmentFile=%h/.config/prosperity-sonar/env` s'applique à **tous** les `ExecStart`, donc à `mise install --locked` (téléchargement et exécution d'installateurs) et à `pnpm install --frozen-lockfile` (scripts de cycle de vie des paquets autorisés par `allowBuilds`). Le code de `pnpm sonar` prend soin de ne donner le jeton ni au lint ni aux tests (`childEnv`), mais le service le donne avant, à des processus qui exécutent du code tiers. Or `loadConfig` (`quality/sonar/config.ts:42-55`) lit déjà ce fichier lui-même (défaut `~/.config/prosperity-sonar/env`, vérification du mode 0600) : la directive est redondante.
**Fix:** supprimer `EnvironmentFile=` du service ; `pnpm sonar` relira le fichier. Si l'on tient à l'environnement systemd, le réserver à un second service ne contenant que `ExecStart=… pnpm sonar`.

### WR-06 : erreurs Semgrep de niveau `warn` (fichiers non analysables) ignorées — à confirmer

**File:** `quality/checks/sast.ts:60-66`
**Issue:** `parseScan` ne retient que les entrées `errors[]` avec `level === 'error'`. Dans la sortie JSON de Semgrep, les échecs d'analyse d'un fichier cible (erreur de syntaxe, `PartialParsing`) sont rapportés avec `level: "warn"` et le code de sortie reste 0 hors `--strict`. Un fichier de `src/` que Semgrep ne sait pas lire (syntaxe TypeScript récente, fichier malformé) est alors silencieusement exclu du scan et le check passe, contrairement à l'intention du commentaire (« dont les échecs d'analyse »). Non reproduit ici (le scan avec registre n'a pas abouti hors ligne) : à confirmer avec une fixture d'erreur de syntaxe dans `semgrep/`.
**Fix:** traiter toute entrée de `errors[]` (quel que soit `level`) dont le type désigne une erreur de syntaxe/analyse comme issue `semgrep-parse-error`, ou ajouter `--strict` à `scan`. Ajouter un cas de `quality/selftest/cases/` pour ce scénario.

### WR-07 : le juge d'intégrité lit le worktree en suivant les liens symboliques ; la garde de dépendances, elle, les refuse

**File:** `quality/integrity-fs.ts:33-52`, comparer `quality/deps-guard.ts:200-205`
**Issue:** `digest`, `readText` et `readJson` utilisent `readFile(join(dir, path))`, qui suit les liens. `deps-guard` a explicitement ajouté `lstat` pour cette raison (la tête d'une PR est une donnée non fiable), mais `integrity` non. Reproduit : remplacer `quality/` par un lien vers un dossier jumeau dont le contenu est identique laisse le juge à `passed` (les empreintes sont égales, et les fichiers `quality/*` disparaissent de `git ls-files`). Dans le scénario testé, la PR suivante est arrêtée **par accident** : `baseFiles.has('quality/thresholds.json')` devient faux et le juge bascule en `bootstrap`, qui exige l'approbation. La protection ne repose donc pas sur un contrôle voulu. Le même mécanisme laisse `digest` lire hors de l'arbre (lien absolu) sans conséquence aujourd'hui, mais sans garde.
**Fix:** comparer des entrées d'index plutôt que des octets du worktree : `git ls-files -s -z` (mode + SHA de blob) pour les deux côtés, et traiter tout mode `120000` (lien) ou changement de mode sous un chemin protégé comme `protected-path-changed`. À défaut, `lstat` et refus des liens dans `readBytes`.

## Info

### IN-01 : la branche est en retard sur deux changements de la PR #301

**File:** `quality/sonar/reports.ts:41-50`, `deploy/sonar/prosperity-sonar.service:18`
**Issue:** `origin/main` porte `--coverage.reportOnFailure` (sans lui Vitest n'écrit aucun LCOV quand un test échoue, l'analyse advisory perd alors la couverture) et `Environment=PATH=%h/.local/bin:…` (sans lui `mise` est introuvable sous systemd). La branche `sebc-dev/jiaolong` n'a ni l'un ni l'autre ; le prochain merge/rebase doit les conserver.
**Fix:** rebaser sur `origin/main` ou reporter les deux lignes avant la PR de bootstrap.

### IN-02 : règle `Write(...)` absente de `.claude/settings.json` — probablement couverte, non démontré

**File:** `.claude/settings.json:3-70`
**Issue:** les règles de refus sont toutes de la forme `Edit(...)`, aucune `Write(...)` ni `NotebookEdit(...)`. D'après la documentation de Claude Code, les règles `Edit` s'appliquent à tous les outils intégrés d'édition de fichiers, ce qui rendrait l'écart théorique ; rien dans le dépôt ne le prouve (aucun test ne tente une écriture refusée), et le hook `PreToolUse` ne cible que `Bash`. Je ne le retiens pas comme défaut avéré.
**Fix:** doubler les règles critiques par `Write(/quality/**)`, `Write(/.github/**)`, `Write(/.claude/settings*.json)` (coût nul) et consigner dans la checklist de la gate un essai manuel d'écriture refusée.

### IN-03 : `parseAmount` accepte les espaces internes arbitraires (`12 50` devient 1 250,00 €)

**File:** `src/shared/money/money.ts:12-30`
**Issue:** tous les blancs sont supprimés avant validation, donc `"12 50"` est lu comme 1250 euros, `"1 0 0"` comme 100. Le but est d'accepter les séparateurs de milliers (U+00A0, U+202F) ; une saisie « 12 50 » est une faute de frappe plausible pour 12,50 € et produit un montant 100 fois trop grand sans erreur. Aucun bogue d'arithmétique, mais le canari doit refuser l'ambigu.
**Fix:** n'accepter les blancs que comme séparateurs de groupes de trois chiffres (`^\d{1,3}(?:[\s\u00a0\u202f]\d{3})*(?:[.,]\d+)?$`) et rejeter le reste avec `invalid-amount` ; ajouter le test `"12 50"` en erreur.

### IN-04 : le contrôle de vulnérabilités ignore les avis sans score CVSS

**File:** `quality/checks/cve.ts:28-44`
**Issue:** `groupIssue` renvoie `undefined` quand `max_severity` est vide ou non numérique (`Number.isNaN(score)`). Un avis OSV sans CVSS (fréquent pour les avis GHSA récents) ne bloque donc jamais, alors que `pnpm audit` couvre une partie des mêmes cas. La décision A9 parle de seuil à 7.0 ; l'absence de score n'y est pas tranchée.
**Fix:** décider explicitement : soit traiter l'absence de score comme bloquante, soit la lister en issue `advisory`/note (`unscored:<id>`) pour qu'elle reste visible.

### IN-05 : `escape-hatches` ne compte que `src/`, `test/` et la racine

**File:** `quality/escape-hatches.ts:62-69`
**Issue:** `isCountedPath` exclut tout autre dossier (`ui/`, `db/`, `scripts/`, un futur `app/`) et les fichiers `.mjs` imbriqués. CLAUDE.md prévoit un workspace `ui/` : les `as any`, `@ts-ignore` et `eslint-disable` y échapperaient au cliquet tant que le périmètre n'est pas étendu. Le jour où `layout.json` gagne un dossier, la liste de `isCountedPath` n'évolue pas avec elle.
**Fix:** lire les dossiers comptés dans `quality/layout.json` (ou compter tout fichier de code suivi hors une liste d'exclusions explicite : `quality/`, `semgrep/`, `.planning/`, `.claude/`).

### IN-06 : la garde Bash est contournable par des enveloppes avec options valuées (consigné D-04)

**File:** `quality/agent-guard/bash-guard.ts:55-71`
**Issue:** `unwrap` retire les options qui suivent une enveloppe mais pas leur valeur : `sudo -u x rm quality/a`, `timeout -k 1 5 rm …` ou `env -C dir cp … quality/` voient `x`/`1`/`dir` pris pour la commande. D-04 déclare la garde non exhaustive et la CI juge ; je le note seulement comme dette connue, y compris l'échec ouvert quand le hook plante (`bash-guard.ts:196-199`, code de sortie non bloquant), sans auto-test de présence du hook.
**Fix:** consigner la limite dans la documentation de la gate ; ajouter un test de fumée (`pnpm quality` ou pré-commit) qui exécute le hook sur une commande refusée connue et échoue si la sortie n'est pas `deny`.

### IN-07 : travail non fiable exécuté avant les étapes de confiance dans le même runner

**File:** `.github/workflows/quality.yml:40-60`
**Issue:** `pnpm install --frozen-lockfile` (code de la PR : scripts de cycle de vie, `.pnpmfile.cjs`) s'exécute avant la création de `gate-base` et avant les étapes `approval-evidence` / `approvals` / `integrity` / `deps` qui produisent `reports/*.json` lus ensuite par `pnpm quality`. Un script d'installation peut déposer un processus résident, écrire `$GITHUB_ENV` (`NODE_OPTIONS`) ou préfabriquer `reports/*.json`. Le verdict hors PR rejoue les juges et ne reprend que la conclusion du run, donc l'impact est borné ; il reste que les « étapes de confiance » du job de la PR ne le sont pas.
**Fix:** créer `gate-base` et lancer les quatre étapes de confiance avant `pnpm install`, ou produire ces rapports dans un job séparé sans installation, et supprimer `reports/` avant `pnpm quality`.

---

_Revue : 2026-11-25_
_Relecteur : Claude (gsd-code-reviewer)_
_Profondeur : standard_
