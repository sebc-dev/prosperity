# Phase 1: Socle et quality gate - Pattern Map

**Mapped:** 2026-11-21
**Files analyzed:** 41 (fichiers à créer ; aucun fichier existant à modifier hors `.claude/settings.json` à créer)
**Analogs found:** 0 en dépôt / 41 ; 41 couverts par un extrait vérifié de `01-RESEARCH.md` ou un analogue interne à la phase

## Constat de départ

Dépôt vierge. `git ls-files` hors `.planning/` ne renvoie que `.claude/CLAUDE.md` (documentation, pas du code). Il n'existe **aucun analogue applicatif** : toute la phase se construit depuis les extraits que RESEARCH.md a déjà exécutés dans un bac à sable. Ce document dit donc, pour chaque fichier, (a) quel extrait de RESEARCH.md copier, (b) quel fichier **de la phase elle-même** sert d'analogue interne (premier fichier écrit = modèle des suivants).

Règle tracked-source (#3645) : aucun chemin ci-dessous ne pointe un miroir gitignoré. L'installation GSD sous `.claude/` n'est pas un analogue de code projet (non suivie par git).

Seule exception autorisée : le format de déclaration de hook, lu dans `.claude/settings.local.json` (non suivi, local à ce poste), est cité ci-dessous pour D-04/D-06 uniquement.

## File Classification

| Fichier à créer | Rôle | Flux de données | Analogue | Qualité |
|---|---|---|---|---|
| `mise.toml`, `mise.lock`, `.mise/locks/**` | config (outillage) | n/a | RESEARCH § Code Examples `mise.toml` | extrait vérifié |
| `package.json`, `pnpm-workspace.yaml`, `pnpm-lock.yaml` | config (supply-chain) | n/a | RESEARCH § `pnpm-workspace.yaml` | extrait vérifié |
| `tsconfig.json` | config | n/a | RESEARCH § `tsconfig.json` | extrait vérifié |
| `eslint.config.mjs` | config (lint) | transform | RESEARCH § `eslint.config.mjs` | extrait vérifié |
| `biome.json` | config (formateur seul) | n/a | aucun extrait (CLAUDE.md §4 : formateur uniquement) | aucun |
| `.dependency-cruiser.cjs` | config (architecture) | transform | RESEARCH § `.dependency-cruiser.cjs` | extrait vérifié |
| `knip.json`, `.jscpd.json` | config | transform | aucun extrait ; consignes Pitfall 12 | partiel |
| `vitest.config.ts` | config (tests) | batch | RESEARCH § `vitest.config.ts` | extrait vérifié |
| `stryker.config.mjs` | config (mutation) | batch | RESEARCH § `stryker.config.mjs` | extrait vérifié |
| `.gitleaks.toml` | config (secrets) | transform | aucun extrait ; Pattern 3 (piège secret) | partiel |
| `lefthook.yml` | config (hooks git) | event-driven | RESEARCH § `lefthook.yml` | extrait vérifié |
| `semgrep/*.yml` (+ tests) | config (SAST) | transform | RESEARCH § Règles Semgrep | extrait vérifié |
| `.github/workflows/quality.yml` | config (CI) | request-response | RESEARCH § Workflow `quality.yml` | extrait vérifié |
| `.github/workflows/nightly.yml` | config (CI) | batch | `quality.yml` (même phase) | interne |
| `.github/CODEOWNERS`, `.github/zizmor.yml` | config | n/a | aucun | aucun |
| `.claude/settings.json` | config (agent) | event-driven | RESEARCH Pattern 5 + format hook ci-dessous | partiel |
| `quality/run.ts` | service (runner) | batch | RESEARCH Pattern 1 | conception |
| `quality/gate-report.ts` | utilitaire (schéma + écriture) | file-I/O | RESEARCH Pattern 1 | conception |
| `quality/checks/*.ts` | service (un par outil) | transform | `quality/checks/<premier>.ts` (interne) + table « Identifiants de règle » | interne |
| `quality/integrity.ts`, `approvals.ts`, `deps-guard.ts` | service (CI only) | request-response | RESEARCH Patterns 2 et 4 | conception |
| `quality/escape-hatches.ts`, `baseline.json`, `protected-paths.json` | utilitaire / config | file-I/O | RESEARCH Pitfall 11 | conception |
| `quality/agent-guard/*.ts` | middleware (hook PreToolUse) | event-driven | RESEARCH Pattern 5, Pitfall 7 + format hook | conception |
| `quality/selftest/<cas>/{patch,expected.json}` + runner | test | batch | RESEARCH Pattern 3 | conception |
| `src/shared/money/*.ts` (+ `*.test.ts`) | modèle (domaine pur) | transform | aucun ; contraintes D-09 | aucun |
| `src/db/sql-migration-provider.ts` | service (infra) | file-I/O | RESEARCH § Intégration PG | extrait vérifié |
| `db/migrations/0001_foundation.sql` | migration | CRUD (DDL) | RESEARCH § Intégration PG | extrait vérifié |
| `test/*.int.test.ts`, méta-tests, `globalSetup` | test (intégration) | request-response | RESEARCH § Intégration PG (test) | extrait vérifié |

## Pattern Assignments

### `package.json` / `pnpm-workspace.yaml` (config, supply-chain)

**Source :** RESEARCH § `pnpm-workspace.yaml` (exécuté), lignes 401-412 du fichier RESEARCH.

```yaml
minimumReleaseAge: 10080
minimumReleaseAgeStrict: true
blockExoticSubdeps: true
trustPolicy: no-downgrade
strictDepBuilds: true
allowBuilds:
  cpu-features: false
  esbuild: false
  protobufjs: false
  ssh2: false
```

Points d'attention : ces réglages vivent dans `pnpm-workspace.yaml`, pas `.npmrc`. Versions exactes sans `^`. Utiliser les **pins de repli** du tableau Standard Stack (vitest 5.1.0, fast-check 4.10.2, knip 6.45.1, typescript-eslint 8.72.2, dependency-cruiser 18.7.2, biome 2.6.7, testcontainers 12.2.1), jamais `minimumReleaseAgeExclude`. Les binaires (`biome`, `jscpd`, `depcruise`) doivent apparaître dans `scripts` pour que knip les voie utilisés (Pitfall 12). Pas de `zod`, `tsx`, `kysely-codegen` en phase 1.

### `mise.toml` (config)

**Source :** RESEARCH § `mise.toml`.

```toml
[tools]
uv = "0.13.9"            # >= 0.12.10 requis pour verrouiller le graphe Python de semgrep
node = "26.13.0"
pnpm = "12.21.0"
gitleaks = "8.30.1"
osv-scanner = "2.7.1"
actionlint = "1.7.12"
zizmor = "1.32.0"
hadolint = "2.15.1"
trufflehog = "3.100.0"
lefthook = "2.2.2"
"pipx:semgrep" = "1.186.0"
```

Générer `mise.lock` avec `mise lock --platform linux-x64`. Ajouter `mise.toml`, `mise.lock`, `.mise/**` et toutes les configurations que mise fusionne (`mise.*.toml`, `.mise.toml`, `.config/mise/**`, `.tool-versions`…) aux chemins protégés (D-11, plan 01-06).

### `tsconfig.json`, `eslint.config.mjs`, `vitest.config.ts`, `stryker.config.mjs`, `.dependency-cruiser.cjs`

**Source :** les blocs complets de RESEARCH § Code Examples (lignes 415-521 pour tsconfig/eslint/depcruise/stryker/vitest). Les copier tels quels comme point de départ ; ils ont été exécutés avec les versions épinglées.

Adaptations à prévoir (non couvertes par les extraits) :
- `eslint.config.mjs` : ajouter des blocs `files:` séparés pour les règles de domaine (`Date`, `process.env`, `console`, `sql.raw`) ; exception `sql.raw` limitée au bloc `files: ['src/db/sql-migration-provider.ts']`, jamais par commentaire `eslint-disable` (Pitfall 6).
- `.dependency-cruiser.cjs` : ajouter la règle `src/db/` accessible seulement depuis `modules/*/adapters/db`, `composition`, `worker`. Sortie à lire en `json` (exit 0 même en échec, Pitfall 3).
- `stryker.config.mjs` : garder `plugins` explicites (Pitfall 2) ; ajouter `disableBail: true` à mesurer (Pitfall 4) ; `reports/` et `*.stryker-incremental.json` au `.gitignore`.
- `vitest.config.ts` : seuils 100 % sur `src/shared/**`, plancher global 85/80 sur tout `src/**` (aucun dossier exclu, décision humaine), périmètre `GATE_COVERAGE_SCOPE` (`pure` pour le check `unit`, `all` pour le check `coverage`, run fusionné `unit` + `integration` du plan 01-05) ; seuils comparés au cliquet par `integrity.ts`.

Layout à valider (Q5) : globs « purs » = `src/shared/**` et `src/modules/*/domain/**`.

### `lefthook.yml` (config, event-driven)

**Source :** RESEARCH § `lefthook.yml`.

```yaml
min_version: 2.2.2
output: [failure, summary]
pre-commit:
  parallel: false
  jobs:
    - name: gitleaks-staged
      run: mise exec -- gitleaks git --staged --redact --no-banner
    - name: protected-paths
      run: mise exec -- node quality/agent-guard/precommit-protected.ts
    - name: format
      glob: "*.ts"
      run: mise exec -- pnpm exec biome format --write {staged_files}
      stage_fixed: true
pre-push:
  jobs:
    - name: quality-push
      run: mise exec -- pnpm quality --profile push
```

Limite : `LEFTHOOK=0` désarme le pré-commit (Pitfall 7) ; le hook agent doit refuser cette variable.

### `.github/workflows/quality.yml` (config, CI)

**Source :** RESEARCH § Workflow `quality.yml`.

```yaml
name: quality
on:
  pull_request:
    types: [opened, synchronize, reopened]   # révision D-14
permissions: {}
jobs:
  quality:
    name: quality
    runs-on: ubuntu-24.04
    permissions: { contents: read, pull-requests: read, actions: read }
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with: { fetch-depth: 0, persist-credentials: false }
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with: { ref: "${{ github.base_ref }}", path: base, persist-credentials: false }
      - uses: jdx/mise-action@90f833d396d0cc3674b631d2d225e306476c303a # v5.2.10
        with: { version: 2026.11.12, github_token: "${{ secrets.GITHUB_TOKEN }}" }
      - run: pnpm install --frozen-lockfile
      - run: pnpm quality
      - uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        if: always()
        with: { name: gate, path: reports/gate.json }
```

Contraintes : aucun filtre `paths`, un seul job nommé `quality`, jobs optionnels = steps conditionnels (Pitfall 10) ; jamais `pull_request_target` ; jamais `${{ github.event.* }}` dans `run:`. (Révision D-14 : plus de job de retrait de label, le workflow garde un seul job sans permission en écriture.) `nightly.yml` : copier ce squelette (mêmes SHA, mêmes permissions) avec `schedule:` et le profil complet + auto-test + trufflehog.

### `semgrep/*.yml` (config, SAST)

**Source :** RESEARCH § Règles Semgrep du projet (5 règles : `tool-handler-without-principal`, `raw-registertool`, `sql-concatenation`, `insecure-random-token`, `non-constant-time-secret-compare`). Copier tel quel. Piège : les patterns contenant `: ` doivent être entre guillemets. Charger avec `--metrics=off`. Les packs registre dérivent (Q4) : ne pas les rendre bloquants sans figer le jeu.

### `.claude/settings.json` (config, event-driven)

**Analogue partiel, format de déclaration de hook** (D-04/D-06) : `.claude/settings.local.json` (non suivi ; sert seulement à montrer la forme). Structure `hooks.<Event>[].matcher` + `hooks[].{type:"command", command, timeout}` :

```json
{
  "hooks": {
    "PostToolUse": [
      { "matcher": "Bash|Edit|Write|MultiEdit|Agent|Task",
        "hooks": [ { "type": "command", "command": "node \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/gsd-context-monitor.js", "timeout": 10 } ] }
    ]
  }
}
```

Pour le garde de l'agent : même forme, événement `PreToolUse`, `matcher: "Bash"`, commande `node "$CLAUDE_PROJECT_DIR"/quality/agent-guard/<hook>.ts` (Node 26 exécute le `.ts` nativement). Les hooks de plusieurs fichiers de settings fusionnent : ne pas toucher à `settings.local.json`, qui porte les hooks GSD.

Règles `permissions.deny` (RESEARCH Pattern 5, Pitfalls 7 et 8) :
- `Edit(/quality/**)`, `Edit(**/eslint.config.*)`, `Edit(/.claude/settings*.json)`, `Edit(/.claude/CLAUDE.md)`, plus les chemins de `protected-paths.json` (D-05 : pas `.claude/**`). `Write(...)` avec chemin ne matche pas : utiliser `Edit(...)`.
- `Bash(git commit --no-verify*)`, `Bash(git push --force*)`.
- Labels (D-03) : `gh pr edit*--add-label*`, `gh pr edit*--remove-label*`, `gh label*`, `gh api*labels*`, `gh issue edit*label*` ; extension Pitfall 8 : `gh api*rulesets*`, `gh api*actions/permissions*`, `gh auth token`.

Limite documentée : un deny n'est pas une frontière de sécurité (`sh -c`, chemin absolu) ; c'est le hook puis la CI qui rattrapent.

### `quality/run.ts`, `quality/gate-report.ts`, `quality/checks/*.ts` (service, batch)

**Pas d'analogue en dépôt. Modèle :** RESEARCH Pattern 1. Le premier check écrit (suggestion : `typecheck.ts`, le plus simple) devient l'analogue interne des suivants.

Contrat à respecter dans chaque check :
- un outil par `spawn` sans shell ; lire la **sortie structurée**, jamais le code de sortie seul ;
- vérifier la version de l'outil contre `mise.toml` ;
- produire `{check, tool, version, severity, passed, issues[]}` + champs additifs `status` (`passed|failed|skipped`) et `skipped_reason` (`ci-only` pour le profil `push`, D-12). Le profil `full` échoue si un check bloquant est `failed` ou `skipped`.

Source d'extraction par outil (table « Identifiants de règle par outil » de RESEARCH, à reproduire en commentaire de chaque check) :

| Check | Lire |
|---|---|
| eslint `-f json` | `messages[].ruleId` (`null` pour directive inutile : matcher le message) |
| tsc | texte `error TSxxxx`, exit 2 |
| depcruise json | `summary.violations[].rule.name`, `summary.error` |
| knip json | `issues[]` |
| jscpd | `statistics.newClones` |
| gitleaks json | `[].RuleID` |
| semgrep json | `results[].check_id` (suffixe) |
| zizmor json / actionlint | `[].ident` |
| osv-scanner json | `groups[].max_severity >= 7.0` calculé par le runner (aucun seuil natif) |
| stryker | `reports/mutation/mutation.json` ; diff via `--mutate <fichiers>` (pas de `--since`) |
| vitest coverage | `json-summary` + stderr de seuil |

Les scripts de gate s'exécutent avec `node` natif, sans `tsx`. Imports relatifs avec extension `.ts`.

### `quality/integrity.ts`, `approvals.ts`, `deps-guard.ts` (service, CI only)

**Pas d'analogue.** Modèle : RESEARCH Patterns 2 et 4. Règles :
- exécutés depuis la copie de la ref de base (`git worktree add ../base origin/<base_ref>`), jamais depuis la PR ; baseline absente côté base = mode « amorçage » (Pitfall 13) ;
- `approvals.ts` (révisé par D-14, le label n'approuve plus) : lit le commit de tête dans git, exige un commit vide `gate-approval: <sortes>` + `Approved-Parent: <SHA>` signé au format SSH, vérifie la signature par `ssh-keygen -Y find-principals` puis `-Y verify -n git` contre `quality/allowed_signers` de la base, puis contrôle lui-même le type de clé et les drapeaux FIDO de présence (0x01) et de vérification (0x04) via `quality/sshsig.ts` ; aucune API GitHub (plan 01-07 tâche 2) ;
- `deps-guard.ts` : diff de `package.json`/lockfile, âge npm et existence ; exige `deps-approved` ;
- `integrity.ts` : refuse toute baisse de `minimumReleaseAge`, tout ajout à `minimumReleaseAgeExclude`, baisse de `coverage.thresholds`, de `stryker.thresholds.break`, de `--max-warnings`.

Utiliser `gh api` depuis les scripts plutôt que `actions/github-script` (tag annoté).

### `quality/escape-hatches.ts`, `baseline.json`, `protected-paths.json`

**Modèle :** RESEARCH Pitfall 11. Compter `@ts-ignore`, `@ts-expect-error`, `@ts-nocheck`, `eslint-disable`, `biome-ignore`, `as any`, `as unknown as`, `!.`, `.skip`, `.todo`, `vi.mock(`, plus les directives qui retirent du code d'un juge (`Stryker disable`/`restore`, `v8`/`istanbul`/`c8 ignore`, `nosem`, `gitleaks:allow`, `jscpd:ignore`, `@public`/`@beta`/`@alias`), sans égard à la casse ni aux espaces (plan 01-06), sur `src/**`, `test/**` et configs racine ; exclure `quality/**`, `semgrep/**`, `.planning/**`, `.claude/**`. Lister via `git ls-files -co --exclude-standard`. Budget initial 0. `protected-paths.json` = liste unique consommée par le hook, lefthook, l'intégrité et CODEOWNERS (D-05, D-11), qui inclut aussi chaque fichier de configuration ou d'exclusion qu'un outil lit de lui-même (`.gitleaksignore`, `.semgrepignore`, `.npmrc`, `.pnpmfile.*`, configs locales de mise, `lefthook-local.yml`, `.gitignore`, `.gitattributes`, harnais de test ; plan 01-06).

### `quality/agent-guard/*.ts` (middleware, event-driven)

**Pas d'analogue.** Modèle : Pattern 5 et Pitfall 7. Le hook lit la chaîne brute de la commande (stdin JSON de PreToolUse). À refuser : `mv`, `cp`, `rm`, `git checkout --`/`restore` sur chemins protégés, `--no-verify`, `git commit -n`, `git -c core.hooksPath`, `git config core.hooksPath`, `lefthook uninstall`, `LEFTHOOK=0`, toute commande contenant `GATE_CHANGE_APPROVED=`, `disableAllHooks`, `gh api` hors GET, `gh auth token`, `curl`/`wget` vers `api.github.com`. Non exhaustif par décision (D-04). `precommit-protected.ts` : lefthook refuse un commit touchant `protected-paths.json` sans variable d'autorisation humaine.

### `quality/selftest/` (test, batch)

**Modèle :** RESEARCH Pattern 3. Cas = `quality/selftest/<cas>/{patch,expected.json}` avec `expected = {check, rule}`. Runner : `git worktree add --detach <tmp> HEAD`, `git apply`, `pnpm install --frozen-lockfile`, `pnpm quality --only <id> --json`, vert si le check échoue **et** que `rule` est dans les identifiants de sortie. Cas minimum (D-07) : `as`, `any`, complexité, mcp-tools → `adapters/db`, cycle, export mort, bloc dupliqué, secret (généré à l'application, pas de littéral dans le patch), SQL concaténé, handler sans `Principal` (patch ajoutant `src/mcp/tools/bad.ts`), action CI non épinglée, test faible, hausse du compteur d'échappatoires, seuil baissé, table sans RLS.

### `src/shared/money/*.ts` (modèle, transform, domaine pur)

**Aucun analogue ; aucun extrait RESEARCH.** Contraintes D-09 : `Money` = `bigint` de centimes + devise `char(3)` (EUR seule acceptée) ; parse chaîne → `bigint` sans `parseFloat`/`Number()` ; répartition au plus grand reste (Σ parts = total) ; formatage « 84,00 € ». Imports autorisés uniquement `src/shared/**` (règle `domain-is-pure`). Tests colocalisés `*.test.ts` : exemples + propriétés fast-check (Σ parts = total, aller-retour parse/format) via `@fast-check/vitest`. Couverture 100 % (lignes, branches, fonctions, instructions) et Stryker ≥ 80. Pas de `Math.round`, `Date`, `console`. Pas de `as` (`assertionStyle: 'never'`) : valider aux frontières par type guards.

### `src/db/sql-migration-provider.ts`, `db/migrations/0001_foundation.sql`, `test/*.int.test.ts`

**Source :** RESEARCH § Intégration PG, extraits exécutés sur `postgres:18.7-trixie`. Copier le fournisseur (import `Migrator`/`MigrationProvider` depuis **`kysely/migration`**, pas la racine, Pitfall 6 ; classe avec champ privé `#dir`, pas de `down`) et la migration (rôle `prosperity_app` `NOLOGIN NOINHERIT NOCREATEDB NOCREATEROLE NOBYPASSRLS`, `REVOKE CREATE ON SCHEMA public FROM PUBLIC`, schéma `prosperity`, `ALTER DEFAULT PRIVILEGES`).

Recette de test (même source) : `globalSetup` Vitest démarrant **un** conteneur, `CREATE DATABASE tpl` → migration → `db.destroy()` → `CREATE DATABASE t_w1_f1 TEMPLATE tpl` par fichier ; assertions : `SHOW server_version` ~ `^18\.7`, `SELECT uuidv7()`, `SET ROLE prosperity_app` puis `CREATE TABLE` en `prosperity` et `public` → SQLSTATE `42501`. Fichiers `*.int.test.ts` sous `test/`. Pas de `vi.mock(` (compté comme échappatoire). Méta-test « toute table à `owner_member_id` a RLS actif » : passe à vide en phase 1.

## Shared Patterns

### Verdict par sortie structurée, jamais par code de sortie
**Source :** RESEARCH Pitfall 3. **S'applique à :** tous les `quality/checks/*.ts`. depcruise renvoie 0 en `json` malgré les violations ; osv-scanner n'a pas de seuil de sévérité.

### Intégrité jugée depuis la base
**Source :** RESEARCH Pattern 2. **S'applique à :** `integrity.ts`, `approvals.ts`, `deps-guard.ts`, `protected-paths.json`, baseline.

### Zéro échappatoire, dérogation par config ciblée
**Source :** `eslint.config.mjs` (RESEARCH). **S'applique à :** tout le code TS. Exception d'une règle = bloc `files:` dédié dans la config, jamais `eslint-disable` sans description.

### SHA complets pour les actions, `pull_request` uniquement
**Source :** RESEARCH § Workflow. **S'applique à :** `quality.yml`, `nightly.yml`. SHA vérifiés : checkout `3d3c42e5aac5ba805825da76410c181273ba90b1`, upload-artifact `cf430e030ddbb5b0abf93d22962f4752f3646cd9`, mise-action `90f833d396d0cc3674b631d2d225e306476c303a`.

### Liste unique des chemins protégés
**Source :** `quality/protected-paths.json` (à créer). **S'applique à :** `.claude/settings.json` deny, hook, lefthook, job d'intégrité, `.github/CODEOWNERS`, déclencheur d'auto-test (D-08). `.claude/**` n'est PAS protégé en bloc (D-05).

## No Analog Found

Planificateur : utiliser les extraits RESEARCH indiqués, ou la conception décrite.

| Fichier | Rôle | Flux | Raison |
|---|---|---|---|
| `src/shared/money/*` | modèle pur | transform | dépôt vierge ; seules les contraintes D-09 existent |
| `quality/run.ts` et checks | runner | batch | conception Pattern 1, sans code existant |
| `quality/agent-guard/*` | hook | event-driven | conception Pattern 5 |
| `quality/integrity.ts`, `approvals.ts`, `deps-guard.ts` | CI | request-response | conception Patterns 2 et 4 |
| `quality/selftest/*` | auto-test | batch | conception Pattern 3 |
| `biome.json`, `knip.json`, `.jscpd.json`, `.gitleaks.toml`, `.github/CODEOWNERS`, `.github/zizmor.yml` | config | n/a | aucun extrait vérifié dans RESEARCH |

## Points de vigilance pour le planificateur

1. Le verrou (deny, CODEOWNERS, ruleset, intégrité) est le **dernier plan** (D-01), avec relecture humaine explicite.
2. Le ruleset `Main` (id 17645569) exige `ci-required` : à remplacer par `quality` (`integration_id` 15368), action humaine (Pitfall 9).
3. Les pins de CLAUDE.md échouent avec `minimumReleaseAge` ; utiliser les pins de repli (Q1).
4. Stryker : pas de `--since`, bug #6335 à mesurer par 20 exécutions du canari en Wave 0.
5. Le jeu `SUS (too-new)` impose un `checkpoint:human-verify` avant l'installation des dépendances.

## Metadata

**Portée de la recherche d'analogues :** dépôt entier (`git ls-files`), `.claude/settings.local.json` (format de hook uniquement), `.claude/hooks/` (confirmation que `PreToolUse` est bien un événement utilisé par GSD).
**Fichiers de code applicatif trouvés :** 0.
**Sections de RESEARCH lues :** lignes 1-653 sur 877 ; les sections ultérieures (Open Questions, Validation Architecture, etc.) n'ont pas été lues et peuvent contenir des précisions sur Q1 à Q8.
**Date d'extraction :** 2026-11-21
