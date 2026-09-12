# Outillage qualité de code, duplication et mutation pour un dépôt React 19/TypeScript + Python, dans une « gate agentique »

> Rapport Claude Research du 2026-09-12, reproduit tel quel. Prompt composé en session Claude Code
> (skill `research-prompter`), à partir de la boucle « SonarQube sans serveur » du dépôt
> `colibri-cms` et de l'état de `.claude/quality.json` de ce dépôt. Fiche de chantier associée :
> `docs/chantiers/en-cours/2026-09-12-quality-gate-sonar-sans-serveur.md`.

## TL;DR
- **La gate bloquante doit reposer sur le lint statique rapide et déterministe** : côté frontend, ESLint 9 flat config + typescript-eslint v8 (`recommendedTypeChecked` + `stylisticTypeChecked`), eslint-plugin-react-hooks v6, jsx-a11y, un sous-ensemble d'eslint-plugin-sonarjs v4 et eslint-plugin-boundaries ; côté backend, Ruff (E/F/C90/PLR/SIM/RET/PERF/PT/B) et deptry. Tout le reste (knip, jscpd, vulture, complexité cognitive Python) commence en **advisory** puis bascule en blocking une fois le baseline propre.
- **La mutation testing (StrykerJS côté TS, mutmut v3/cosmic-ray côté Python) doit rester HORS gate bloquante** : son coût « scales worse than test execution » même en incrémental, et il est aggravé côté Python par testcontainers ; à exécuter en nightly + run PR advisory sur fichiers changés.
- **Point technique clé** : en Python, seul **flake8-cognitive-complexity** implémente la vraie complexité *cognitive* au sens Sonar/Campbell ; radon, xenon et Ruff C901 ne mesurent que la complexité *cyclomatique*. Et rules.sonarsource.com/python couvre en plus la **taint analysis inter-procédurale/cross-file** que Ruff ne fait pas.

## Key Findings

### Correspondance avec la grille de règles Sonar (bug / code smell / complexité / duplication / dead code)
| Catégorie Sonar | Frontend (TS/TSX) | Backend (Python) |
|---|---|---|
| **Bug** | typescript-eslint type-aware (`no-floating-promises`, `no-misused-promises`, `no-unsafe-*`) ; sonarjs (règles catégorie *bug*) | Ruff `F`/`B`/`PLE` |
| **Code smell** | typescript-eslint stylistic ; sonarjs code smells | Ruff `SIM`/`RET`/`PLR`/`PERF`/`UP` |
| **Complexité** | `sonarjs/cognitive-complexity` (vraie cognitive, défaut 15) | flake8-cognitive-complexity (vraie cognitive, défaut 7) ; Ruff `C901` + radon/xenon (cyclomatique uniquement) |
| **Duplication** | jscpd | jscpd |
| **Dead code** | knip | vulture + deptry |

### Ce que Sonar Python couvre au-delà de Ruff
La documentation Sonar (sonarsource.com, page taint analysis) décrit une analyse « performed cross-function and cross-file to reduce false positives » réalisée par « symbolic execution, path sensitive analysis & cross-function/cross file taint analysis » (SQL injection, XSS, SSRF, désérialisation). **Ruff est un linter par-fichier** : il couvre style, bugs simples et complexité cyclomatique, mais **pas** l'analyse de flux de données taint inter-procédurale. C'est la différence structurelle à assumer : Ruff ne remplace pas la couche sécurité/taint de Sonar.

## Details

### Tableau 1 — Frontend (React 19 / TSX)

| Check | Outil + version (sept. 2026) | Version stable & sûre à adopter | Sévérité recommandée | Coût estimé |
|---|---|---|---|---|
| Lint type-aware | typescript-eslint v8 + ESLint 9 flat config | oui | **blocking** | build TS préalable : « a few seconds or less » sur petits projets, plus long sur gros |
| Règles Sonar JS/TSX | eslint-plugin-sonarjs 4.2.0 | oui | **blocking** (sous-ensemble) | inclus dans le run ESLint |
| Hooks / React Compiler | eslint-plugin-react-hooks 6.1.1 | oui | **blocking** | inclus |
| Accessibilité | eslint-plugin-jsx-a11y | oui | advisory → blocking | inclus |
| Frontières archi | eslint-plugin-boundaries | oui | **blocking** | inclus |
| Dead code / deps inutilisées | knip 6.35.0 | oui | advisory (blocking après nettoyage) | quelques secondes à dizaines de s |
| Duplication | jscpd 5.1.2 (npm ; tag GitHub 5.2.0) | oui | advisory (blocking via baseline) | quelques secondes (moteur Rust) |
| Mutation | @stryker-mutator/core 10.0.0 + vitest-runner | oui mais coûteux | **hors gate / nightly** | minutes à heures |

### Tableau 2 — Backend (Python)

| Check | Outil + version (sept. 2026) | Version stable & sûre à adopter | Sévérité recommandée | Coût estimé |
|---|---|---|---|---|
| Lint + complexité cyclomatique | Ruff 0.16.7 | oui | **blocking** | sub-seconde à quelques s (Rust, cache) |
| Complexité cognitive (Sonar) | flake8-cognitive-complexity 0.1.0 | partiel — maintenance faible | advisory | quelques s |
| Complexité cyclomatique / MI | radon 6.0.1 / xenon 0.9.3 | oui | advisory | quelques s |
| Dead code | vulture 2.16 | oui, mais bruyant | advisory | quelques s |
| Dépendances (unused/missing/transitive) | deptry 0.25.1 | oui | **blocking** | quelques s |
| Mutation | mutmut 3.7.0 / cosmic-ray | oui mais coûteux | **hors gate** | minutes à heures (×N avec testcontainers) |

*(Note : deptry 0.25.0 a été retiré de PyPI pour un échec de release ; 0.25.1 est identique et corrige le process. Le projet a migré vers l'org `osprey-oss`.)*

### Coût réel du type-aware linting et stratégies de réduction
typescript-eslint v8 a stabilisé `parserOptions.projectService` (auparavant `EXPERIMENTAL_useProjectService`), qui « uses the same type information services as editors » et supporte les TypeScript project references pour les monorepos. La doc officielle (typescript-eslint.io, *Linting with Type Information*) prévient, **verbatim** : « By using typed linting in your config, you incur the performance penalty of asking TypeScript to do a build of your project before ESLint can do its linting. For small projects this takes a negligible amount of time (a few seconds or less); for large projects, it can take longer. »

Stratégies de réduction confirmées par la doc perf de typescript-eslint :
- **Cache ESLint** (`--cache`) — noter qu'en flat config le cache n'est pas activé par défaut, il faut le demander explicitement.
- **Exécution sur fichiers touchés** en PR (le build complet reste en nightly).
- **`--max-warnings 0`** pour transformer les warnings en signal bloquant net.
- **`NODE_OPTIONS=--max-semi-space-size=256`** en cas d'OOM (`Reached heap limit`) sur gros projets.
- ⚠️ Le gain de `projectService` vs l'ancien `project` **n'est plus systématique** : l'équipe traite « the lack of significant improvement as a bug » (issue #9571). Ne pas supposer un gain automatique — mesurer.

**Config frontend (eslint.config.mjs, ESLint 9 flat config) :**
```js
import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import sonarjs from 'eslint-plugin-sonarjs';
import reactHooks from 'eslint-plugin-react-hooks';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import boundaries from 'eslint-plugin-boundaries';

export default tseslint.config(
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  ...tseslint.configs.stylisticTypeChecked,
  sonarjs.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    plugins: { 'react-hooks': reactHooks, 'jsx-a11y': jsxA11y, boundaries },
    rules: {
      ...reactHooks.configs.flat.recommended.rules,
      'sonarjs/cognitive-complexity': ['error', 15],
      'sonarjs/no-identical-functions': 'error',
      'sonarjs/no-duplicate-string': ['error', { threshold: 5 }],
      'boundaries/element-types': ['error', { default: 'disallow', rules: [
        { from: 'pages',     allow: ['components', 'business', 'hooks', 'lib'] },
        { from: 'business',  allow: ['hooks', 'lib'] },
        { from: 'hooks',     allow: ['lib'] },
      ]}],
    },
    settings: { 'boundaries/elements': [
      { type: 'pages',      pattern: 'src/pages/*' },
      { type: 'components', pattern: 'src/components/*' },
      { type: 'business',   pattern: 'src/business/*' },
      { type: 'hooks',      pattern: 'src/hooks/*' },
      { type: 'lib',        pattern: 'src/lib/*' },
    ]},
  },
);
```

**Calibrage `tests/**` (Testing Library, MSW, fixtures) :**
```js
{
  files: ['**/*.{test,spec}.{ts,tsx}', 'src/mocks/**', 'src/test/**'],
  rules: {
    '@typescript-eslint/no-floating-promises': 'off', // userEvent / waitFor
    '@typescript-eslint/unbound-method': 'off',        // matchers Testing Library
    '@typescript-eslint/no-non-null-assertion': 'off',
    'sonarjs/no-duplicate-string': 'off',              // libellés de test répétés
    'sonarjs/cognitive-complexity': 'off',             // arrange/act/assert longs
    'boundaries/element-types': 'off',                 // tests importent tout
  },
}
```
Pour MSW, garder `src/mocks/**` déclaré aussi comme `entry` dans knip (handlers importés dynamiquement).

### eslint-plugin-sonarjs : utilité au-delà de typescript-eslint, redondances, seuil
Depuis la v2, le plugin expose **toutes** les règles JS/TS de SonarJS. En v3, Sonar a nettoyé les doublons ; **verbatim** (forum Sonar Community, thread *Eslint-plugin-sonarjs peerDependencies conflicts*) : « In v3 we removed many rules that were modified from external plugins (those were all added in 2.0.0). We decided that from now on, we will only publish rules that are our own implementation in the ESLint plugin. » Le README officiel confirme que SonarJS « uses some rules [that] are not shipped in this ESLint plugin to avoid duplication with already existing rules from ESLint core and third-party ESLint plugins ». En v4 (4.2.0), le nettoyage se poursuit : le changelog SonarJS mentionne « Add ESLint v10 support; remove code-eval, enforce-trailing-comma, super-invocation from eslint-plugin-sonarjs ».

**Règles à réelle valeur ajoutée (au-delà de typescript-eslint) :**
- `cognitive-complexity` — vraie complexité cognitive au sens Campbell, message « Refactor this function to reduce its Cognitive Complexity from X to the N allowed », seuil par défaut **15** (`const DEFAULT_THRESHOLD = 15`).
- `no-identical-functions`, `no-duplicate-string`, `no-duplicated-branches` — couche anti-duplication *sémantique* que jscpd (token-based) ne couvre pas de la même façon.
- `no-collapsible-if`, `no-small-switch`, `max-switch-cases`, `no-redundant-boolean`, `no-inverted-boolean-check`, `prefer-immediate-return`, `no-useless-catch`.
- Règles JSX (short-circuit, etc.).

**Seuil de complexité cognitive** : 15 par défaut. Abaisser à **10** aligne sur une gate stricte façon Sonar « clean code », mais génère plus de bruit initial → introduire en advisory à 15 puis resserrer.

### knip : faux positifs Vite / TanStack Router / Capacitor / shadcn vendored
Philosophie officielle (knip.dev, *Resolve reported issues*), **verbatim** : « When Knip reports something you didn't expect, it's telling the truth about its module graph: it couldn't reach that code from an entry file. So a surprising result is usually a real finding or a configuration gap, not a false positive to silence. » La doc ajoute : « Reach for ignore* options only as a last resort. »

- **TanStack Router (routes générées / file-based)** — **verbatim** : « the `src/routeTree.gen.ts` file generated by @tanstack/router must exist so Knip can find the imported route files » → **générer les routes avant knip**. Plugin `tanstack-router` disponible.
- **Vite** — plugin Vite officiel ; les fichiers de config sont automatiquement ajoutés comme *entry* pour la résolution statique des imports.
- **Capacitor** — plugin `capacitor` existant, mais support Ionic incomplet (issue #604) : `@capacitor/android`/`@capacitor/ios` sont « used by the project, but knip seems unable to detect that » → les mettre en `ignoreDependencies`.
- **shadcn/ui vendorisé** — composants copiés non tous importés → déclarer `src/components/ui/**` en `entry` (ou `ignore` si volontairement vendored).

**knip.json :**
```json
{
  "$schema": "https://unpkg.com/knip@6/schema.json",
  "entry": ["src/main.tsx", "src/routes/**/*.tsx", "src/components/ui/**", "src/mocks/**"],
  "project": ["src/**/*.{ts,tsx}"],
  "ignore": ["src/routeTree.gen.ts"],
  "ignoreDependencies": ["@capacitor/android", "@capacitor/ios"],
  "vite": true,
  "tanstack-router": true,
  "vitest": {}
}
```
Calibrage tests : garder `**/*.{test,spec}.*` couverts par le plugin `vitest` (knip sait qu'ils sont des entry de test), et déclarer les fixtures/handlers MSW en `entry` pour éviter les faux « unused exports ».

### jscpd : multi-langage TS+Python et baseline origin/main
jscpd v5 est un **moteur Rust** (binaire autonome, sans runtime Node ; l'ancien moteur TypeScript reste publié en `jscpd@4`). La doc (jscpd.dev) indique un support de **223 langages/formats de documents pour la détection de duplication, dont 130 auto-détectés par extension** (TypeScript et Python inclus). Le README Rust précise, **verbatim** : « The Rust engine is a ground-up rewrite of jscpd. It is a drop-in replacement for the Node.js CLI — same algorithm, same reporters, same .jscpd.json config — but 24-37x faster. »

**Oui, jscpd a un vrai mode baseline/incrémental** (docs.rs/jscpd, README) :
```bash
# Baseline stocké puis échec seulement sur les nouveaux clones
jscpd --update-baseline --baseline .jscpd-baseline.json .
jscpd --baseline .jscpd-baseline.json --fail-on-new-clones .

# Ou directement contre une ref git, sans fichier baseline stocké :
jscpd --baseline-from-ref origin/main --fail-on-new-clones .
```
Reporters disponibles : `console`, `console-full`, `json`, `xml`, `csv`, `html`, `markdown`, `badge`, `sarif`, `ai`, `xcode`, `threshold`, `silent`, `openmetrics`, `codeclimate`. Par défaut TS et Python sont **tokenisés dans des pools séparés** — comportement souhaitable ici (on ne cherche pas des clones cross-langage TS↔Python).

**.jscpd.json :**
```json
{
  "minTokens": 50,
  "minLines": 5,
  "format": ["typescript", "tsx", "python"],
  "ignore": ["**/node_modules/**", "**/dist/**", "**/*.gen.ts", "**/tests/**"],
  "reporters": ["console", "json"],
  "threshold": 5
}
```
Calibrage tests : exclure `**/tests/**` et `**/*.{test,spec}.*` (répétition arrange/act/assert normale, sinon faux positifs massifs). Commande PR : `jscpd --baseline-from-ref origin/main --fail-on-new-clones .`.

### Équivalences Ruff ↔ Sonar Python
Ruff 0.16.7 (publié le 10 sept. 2026) réimplémente en Rust des centaines de règles issues de l'écosystème flake8. *Interprétation à qualifier* : un billet (Simon Willison / blog Astral, 25 juil. 2026) rapporte que Ruff v0.16.0 « enables 413 rules by default, up from 59 » et que « the number of rules in Ruff has grown from 708 to 968 » — chiffres cohérents avec la doc mais à traiter comme reprise secondaire.

Correspondances demandées (docs.astral.sh/ruff) :
- `C90` = **mccabe** → `C901` « complex-structure », complexité **cyclomatique**, configurable via `[tool.ruff.lint.mccabe] max-complexity`.
- `PLR` = **Pylint refactor** ; `SIM` = **flake8-simplify** ; `RET` = **flake8-return** ; `PERF` = **Perflint** ; `PT` = **flake8-pytest-style**.

**Ce que Sonar couvre en plus** : taint analysis cross-function/cross-file, symbolic execution, analyses path-sensitive (voir *Key Findings*). Ruff ne le fait pas.

**pyproject.toml (Ruff) :**
```toml
[tool.ruff]
target-version = "py312"
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "C90", "PLR", "SIM", "RET", "PERF", "PT"]

[tool.ruff.lint.mccabe]
max-complexity = 10

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["PLR2004", "S101", "PLR0913", "PT011", "PLR0915"]
```
Calibrage `tests/**` : neutraliser les « magic value » (`PLR2004`), l'usage d'`assert` (`S101`), le nombre d'arguments/statements (fixtures pytest volumineuses).

### Complexité cognitive en Python : qui implémente réellement quoi
- **radon 6.0.1** : complexité **cyclomatique** (CC), Maintainability Index, Halstead, raw metrics — **aucune complexité cognitive**. Plugin flake8 avec seuil CC par défaut 10.
- **xenon 0.9.3** : gate CI **au-dessus de radon** → cyclomatique.
- **Ruff `C901`** : mccabe → **cyclomatique**.
- **flake8-cognitive-complexity 0.1.0 (Melevir, code `CCR001`)** : **seule** implémentation de la vraie complexité **cognitive** au sens Sonar. **Verbatim** README : « Cognitive complexity is analog of cyclomatic complexity, that measure how difficult to understand piece of code. Introduced by G. Ann Campbell and currently used by SonarSource, CodeClimate and others » et « Default complexity is 7, can be configured via --max-cognitive-complexity option. » ⚠️ Maintenance faible (dernière release ancienne, ~36 000 téléchargements/semaine, 71 stars) ; Ruff a une issue ouverte (#2418) pour l'implémenter mais **ne le fait pas encore**.

**Conclusion opérationnelle** : pour approcher la métrique Sonar, utiliser flake8-cognitive-complexity en advisory (seuil 7→15 à calibrer) ; utiliser radon/xenon/Ruff C901 comme filet cyclomatique blocking.

### Mutation testing
**StrykerJS + vitest-runner** (depuis Stryker 7.0 ; core 10.0.0 en sept. 2026). Le runner impose des contraintes non surchargeables : `singleThread: true` (Stryker gère son propre parallélisme via workers), `coverage.enabled: false` (Stryker fait sa propre analyse de couverture), `bail`, `watch: false` ; par défaut il ne lance que les tests liés aux fichiers mutés (`related`). Fonctions clés :
- **Incrémental** : `--incremental` persiste les résultats dans un fichier ; les runs suivants sautent les mutants dont le code et les tests n'ont pas changé.
- **Diff** : `--since <ref>` pour ne muter que les fichiers changés ; `--concurrency` pour paralléliser.
- **⚠️ Bug connu (issue #6004)** : avec vitest-runner en mode incrémental, les IDs de tests sont non déterministes → un diff « ~15k LOC » no-op dans `stryker-incremental.json` à chaque run, ce qui bloque le versionnage du baseline.

**Pourquoi hors gate** : la doc/pratique confirment que la mutation « scales worse than test execution » même en incremental + perTest → **nightly complet + run PR advisory sur fichiers changés** (`--since origin/main --incremental --concurrency`). La bascule vers un `break` threshold ne se fait que quand le score est stable et le bug de baseline résolu.

**Python : mutmut v3 vs cosmic-ray.**
- **mutmut 3.7.0** (`requires-python >=3.10`) : nouveau modèle d'exécution vs v2, mécanisme de **trampoline** par fonction et **hachage de source par fonction** pour l'invalidation de cache incrémentale. **Verbatim** README : « Between runs, mutmut only re-tests mutants in functions whose source changed. » Contrainte : « Mutmut must be run on a system with fork support. This means that if you want to run on windows, you must run inside WSL. » Le README revendique « Parallel and fast execution » et une exécution qui ne lance que les tests atteignant le code muté (pas de multiplicateur chiffré officiel — la formulation « extrêmement rapide vs milliers de fichiers écrits sur disque » provient de DeepWiki, généré par IA, à ne pas citer comme officielle).
- **cosmic-ray** : outil mature, seul identifié avec intégration build-tool dans les comparatifs académiques (ACM/IEEE 2024-2025), mais historiquement lourd à installer ; conseil pratique (guides QA) : « Set the test command to the smallest test set that exercises the mutated module » et gate réaliste = « baseline must pass, mutation run must complete, and new survivors in selected modules require review ».
- **Impact testcontainers** : démarrer un conteneur (ex. Postgres) **par test** rend la mutation prohibitive (chaque mutant relance la suite). Guidance officielle (Docker/Testcontainers *getting started*) : fixtures **module/session-scoped** — « The setup fixture has scope="module", so it runs once for all tests in the file. » La fonctionnalité de **réutilisation** existe (`.withReuse(true)` / propriété `testcontainers.reuse.enable=true`) mais est **expérimentale et « not suited for CI usage »**, et son implémentation « currently differs across Testcontainers libraries » (support Python incomplet). → Pour la mutation Python : conteneur **session-scoped** + fixture function-scoped qui nettoie les données (TRUNCATE/rollback) entre tests.

**stryker.config.mjs :**
```js
export default {
  packageManager: 'npm',
  testRunner: 'vitest',
  vitest: { configFile: 'vitest.config.ts' },
  coverageAnalysis: 'perTest',
  incremental: true,
  mutate: [
    'src/lib/**/*.ts', 'src/lib/drizzle/queries/**/*.ts',
    'src/hooks/**/*.ts', 'src/business/**/*.ts',
    '!src/**/*.{test,spec}.ts',
  ],
  thresholds: { high: 80, low: 60, break: null }, // break=null → jamais bloquant
  reporters: ['json', 'html', 'clear-text'],
};
```
mutmut (backend) : cibler `backend/**/domain.py`, pointer la plus petite suite pytest qui exerce le module, conteneurs session-scoped, run nocturne.

### Format de sortie JSON lisible par un agent, et agrégation
JSON/SARIF natif confirmé par les docs officielles :
- **ESLint** : `--format json` et `--format sarif`.
- **Ruff** : `--output-format json|sarif|github` (+ `--output-format github` pour annotations Actions).
- **knip** : `--reporter json`.
- **jscpd** : reporters `json` et `sarif`.
- **deptry** : `-o report.json` (sortie JSON avec `code`/`message`/`module`/`location`) ; option d'annotations GitHub Actions.
- **Stryker** : reporter `json` (rapport de mutation).

**Agrégation recommandée** : un fichier JSON par check dans `reports/`, puis un agrégat unifié `reports/gate.json` que l'agent lit — champs par check : `{ tool, version, severity: blocking|advisory, issues: n, files: [...], passed: bool }`. Exécution : **fichiers touchés en PR** (ESLint `--cache`, Ruff, jscpd `--baseline-from-ref origin/main`, Stryker `--since`) + **run complet nocturne**. SARIF là où l'agent/plateforme le consomme (ESLint, Ruff, jscpd) ; JSON « plat » ailleurs.

## Recommendations

**Étape 1 — Immédiat (blocking, coût faible et déterministe)**
- Frontend : ESLint 9 flat + typescript-eslint v8 `recommendedTypeChecked` + `stylisticTypeChecked`, react-hooks v6 (`configs.flat.recommended`), jsx-a11y, sous-ensemble sonarjs (`cognitive-complexity@15`, `no-identical-functions`, `no-duplicate-string`), boundaries. Sortie `--format json`+`sarif`, `--cache`, `--max-warnings 0`.
- Backend : Ruff (`E/F/W/I/UP/B/C90/PLR/SIM/RET/PERF/PT`, `max-complexity=10`) + deptry (`-o report.json`).
- Overrides `tests/**` comme montré.

**Étape 2 — Court terme (advisory, à faire mûrir)**
- knip (après génération de `routeTree.gen.ts`), jscpd avec baseline `origin/main`, vulture (`--min-confidence 80`), flake8-cognitive-complexity, radon/xenon.
- **Basculer knip et jscpd en blocking** une fois le baseline propre.

**Étape 3 — Hors gate (nightly + PR advisory)**
- StrykerJS (vitest-runner, `coverageAnalysis: perTest`, `--incremental`, `--since`) sur `lib/drizzle/queries`, `hooks`, `business`.
- mutmut v3 (ou cosmic-ray) sur `backend/**/domain.py` avec conteneurs testcontainers **session-scoped**.

**Ce qui ferait RÉVISER une sévérité `blocking` (conditions de bascule)**
- Type-aware trop lent (> ~2-3 min en PR même avec cache/fichiers touchés) → lint non-typé en PR, typé en nightly.
- knip/jscpd : faux positifs non résolus persistants → repli en advisory jusqu'à baseline stable.
- `strictTypeChecked` trop bruyant → repli sur `recommendedTypeChecked` (la doc réserve `strict-type-checked` aux équipes dont « a nontrivial percentage of its developers are highly proficient in TypeScript », et le classe non-« stable » au sens semver).
- Mutation : **jamais** blocking tant que le coût dépasse la fenêtre CI ou que le bug de baseline non déterministe (issue #6004) persiste.

**Seuils/benchmarks de bascule vers blocking**
- Mutation → advisory strict quand score ≥ 80 % stable sur modules critiques (`thresholds.break`).
- knip/jscpd → blocking après 0 faux positif sur ~2 sprints.
- Budget cumulé de la gate PR maintenu sous ~3-5 min (au-delà : réduire le périmètre type-aware ou passer certains checks en nightly).

## Caveats
- **Affirmations reposant sur une source unique (à confirmer)** : le bug de baseline non déterministe de vitest-runner (issue GitHub #6004, unique) ; le retrait des règles externes en sonarjs v3 (forum Sonar Community, propos d'un mainteneur).
- **[INCERTAIN]** typescript-eslint : v8 confirmée stable ; l'existence d'une **v9 stable** en sept. 2026 n'a pas été vérifiée — adopter v8.
- **[INCERTAIN]** eslint-plugin-jsx-a11y et eslint-plugin-react (core) : numéros de version exacts non vérifiés dans cette recherche ; à figer au moment de l'installation.
- flake8-cognitive-complexity reste en **0.1.0** avec maintenance faible — risque de compatibilité avec les flake8 récents ; alternative : accepter que le frontend porte la vraie cognitive et le backend se contente du cyclomatique en blocking.
- mutmut : la comparaison « extrêmement rapide vs milliers de fichiers sur disque » vient de **DeepWiki (généré par IA)**, pas du README officiel qui ne donne aucun multiplicateur chiffré.
- jscpd : npm « latest » = 5.1.2, tag GitHub = 5.2.0 (décalage de dist-tag) ; vérifier la version installée.
- deptry : 0.25.0 retiré de PyPI ; utiliser 0.25.1.
- Ruff : les chiffres « 413 règles par défaut / 968 au total » proviennent d'un billet de blog (reprise secondaire), pas d'un décompte officiel figé.
- Aucune doc **testcontainers-python** officielle ne traite spécifiquement du coût de mutation ; la guidance (fixtures scoped, réutilisation expérimentale) est inférée des guides d'intégration généraux.
- **Checks écartés et pourquoi** : (1) *SonarQube/SonarCloud complet en gate PR* — écarté car serveur lourd/edition payante pour la taint analysis (« Security engine custom configuration is available as part of the Enterprise Edition and above »), remplacé par sonarjs (front) + Ruff/bandit-via-Ruff (back) ; (2) *jscpd cross-format TS↔Python* — écarté (pools séparés voulus) ; (3) *radon/xenon comme mesure « cognitive »* — écartés pour cet usage car cyclomatiques uniquement ; (4) *mutation en gate bloquante* — écartée (coût) ; (5) *deadcode (auto-fix) comme remplaçant de vulture* — non retenu par défaut faute de sourçage suffisant sur sa maturité ici, à évaluer ; (6) *les listicles « meilleurs linters » et comparatifs SonarSource sur ses propres règles* — écartés au profit des docs primaires, conformément à la demande.
