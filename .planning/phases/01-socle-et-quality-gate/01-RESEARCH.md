# Phase 1: Socle et quality gate - Research

**Researched:** 2026-11-21
**Domain:** quality gate déterministe (`pnpm quality`) pour un dépôt TypeScript écrit par des agents IA : outillage statique, tests, sécurité, anti-contournement, CI GitHub Actions, verrou des chemins protégés
**Confidence:** MEDIUM-HIGH (outillage et comportements clés **exécutés** dans un bac à sable ; points GitHub/Claude Code vérifiés en API ou en docs officielles ; les prototypes de workflow et de hook restent à écrire)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Amorçage des protections**
- **D-01:** Les chemins protégés sont écrits librement pendant la phase 1. Le **dernier plan** active le verrou complet (deny agent, CODEOWNERS, job d'intégrité, ruleset sur `main`) et le prouve par un test : une tentative d'édition d'un fichier de config de la gate par l'agent est refusée. Avant ce plan, la relecture humaine de la config de la gate est la seule protection : le plan final doit inclure un point de relecture explicite.
- **D-02:** « Approbation humaine » = **label posé par `sebc-dev`, vérifié par la CI**. Le job lit les événements de la PR (API issues events, `labeled`, `actor.login`) et n'accepte `gate-change-approved` / `deps-approved` que si (a) l'auteur est dans une allowlist versionnée (aujourd'hui : `sebc-dev`) et (b) le label a été posé **après le dernier commit** de la PR. Tout nouveau push retire le label (job sur `synchronize`) : l'approbation est à refaire. Raison : dépôt public, un seul collaborateur, GitHub refuse l'auto-approbation, donc la revue CODEOWNERS native ne peut pas servir. CODEOWNERS reste présent (documentation, et filet si un collaborateur arrive). — **Reversibility:** reversible — on peut passer plus tard à un commit d'approbation signé sans toucher au reste.
- **D-03:** L'agent n'a pas le droit de poser ni retirer des labels : règles deny sur `gh pr edit*--add-label*`, `gh pr edit*--remove-label*`, `gh label*`, `gh api*labels*` (et `gh issue edit*label*`).
- **D-04:** Arrêt local de l'agent en trois couches, la CI restant le juge final : (1) règles `deny` Edit/Write sur les chemins protégés dans `.claude/settings.json` (versionné) ; (2) hook `PreToolUse` sur Bash qui refuse les écritures shell courantes vers ces chemins (`sed -i`, `>`/`>>`, `tee`, `mv`, `cp`, `rm`, `git checkout --`/`restore` sur ces chemins) ; (3) pré-commit lefthook qui refuse un commit touchant ces chemins sans variable d'autorisation humaine. `--no-verify` et `git push --force*` sont refusés à l'agent. Le hook n'a pas besoin d'être exhaustif : le job d'intégrité CI rattrape les contournements exotiques.
- **D-05:** Sous `.claude/`, seul le **sous-ensemble qui peut désarmer la gate** est protégé : `.claude/settings*.json` et `.claude/CLAUDE.md` (plus `CLAUDE.md`/`AGENTS.md` racine s'ils existent). Les dossiers installés par GSD (`.claude/agents/`, `.claude/commands/`, `.claude/gsd-core/`, `.claude/hooks/gsd-*`, `.claude/scripts/`) restent libres pour les mises à jour de GSD. Cela **remplace** l'entrée `.claude/**` de la liste des chemins protégés de SUMMARY.md.
- **D-06:** Le hook de garde de l'agent vit dans **`quality/agent-guard/`** (protégé via `quality/**`), référencé depuis `.claude/settings.json` — pas dans `.claude/hooks/`.

**Preuve de la gate**
- **D-07:** Preuve **hybride**. (a) Un **auto-test de la gate** (`quality/selftest/`) : chaque cas = un patch qui introduit UNE violation + l'identifiant de règle attendu ; il est appliqué sur une copie jetable du vrai dépôt (`git worktree`), avec la vraie config, et le cas n'est vert que si le check visé échoue **pour la règle attendue**. Couvre au minimum chaque violation du critère 2 (`as`, `any`, complexité, outil MCP → `adapters/db`, cycle, export mort, bloc dupliqué, secret, SQL concaténé, handler sans `Principal`, action CI non épinglée) plus : test faible (mutation + couverture), hausse du compteur d'échappatoires, seuil baissé, table sans RLS (cf. D-10). (b) **4 à 5 vraies PR GitHub** jouées en passage manuel guidé à la fin de la phase, limitées à ce que seul GitHub prouve : le check requis `quality` bloque le merge ; label posé par toi accepté ; label posé par un autre acteur (bot/`github-actions`) refusé ; label retiré au push suivant ; dépendance ajoutée sans `deps-approved` bloquée.
- **D-08:** L'auto-test tourne sur **toute PR qui touche un chemin protégé** (même liste que le job d'intégrité, ce qui couvre les montées de version Renovate via `package.json`/lockfile) **et en nightly**. Pas sur chaque PR de domaine.

**Module canari**
- **D-09:** Le canari est un **vrai module `src/shared/money`, minimal** : type `Money` (montant `bigint` en centimes + devise `char(3)`, EUR seul accepté en v1), parse chaîne → `bigint` (jamais `parseFloat`/`Number()`), répartition au plus grand reste (Σ parts = total), formatage serveur (« 84,00 € »). Pas de change, pas de taux, pas de multi-devise en usage. Tests : exemples + propriétés fast-check (Σ parts = total, aller-retour parse/format). Il doit tenir couverture 100 % lignes+branches et Stryker ≥ 80. Le « test faible » du critère 3 est un **cas d'auto-test** (patch qui retire une assertion), pas un état du dépôt. Pas de module jouet (knip le signalerait comme mort, contraire au budget d'échappatoires à 0). — **Reversibility:** costly — `Money` sera importé par tous les modules à partir de la phase 3.
- **D-10:** L'intégration PostgreSQL de la phase 1 porte sur le **socle de base**, sans table métier : première migration Kysely (SQL brut, forward-only) = rôles séparés migrations / app (app sans droit DDL), schéma, extensions nécessaires. Tests sur PG 18 réel via Testcontainers (une base par worker, `CREATE DATABASE … TEMPLATE` par fichier, `sequence.shuffle` + seed loguée) : version 18.x, `uuidv7()` disponible, rôle app privé de DDL. Les **méta-tests** sont posés dès maintenant, notamment « toute table à `owner_member_id` a RLS actif » : ils passent à vide en phase 1 et un cas d'auto-test (création d'une table sans RLS → échec attendu) prouve qu'ils mordent. Pas de table canari jetable (les migrations forward-only la garderaient pour toujours). — **Reversibility:** one-way — migration forward-only appliquée en base ; la corriger exige une nouvelle migration.

**Outils hors npm et exécution**
- **D-11:** Les outils hors npm (gitleaks 8.30.1, semgrep 1.186.0, osv-scanner 2.7.1, actionlint 1.7.12, zizmor 1.32.0, hadolint 2.15.1 ; trufflehog en nightly) **et** Node/pnpm sont épinglés dans un **`mise.toml` versionné**, lu par lefthook sur le poste et par `jdx/mise-action` (épinglée par SHA) en CI. `mise.toml` est ajouté aux chemins protégés. Raison principale : dépôt public, gitleaks doit arrêter un secret en pré-commit, dans la même version qu'en CI.
- **D-12:** Un seul point d'entrée `pnpm quality`, avec un **profil `push`** pour le pré-push (budget ≤ 60 s) qui joue les mêmes checks dans les mêmes versions mais saute les checks lourds (Stryker sur diff, intégration PG complète, osv-scanner, hadolint, zizmor, e2e) en les déclarant `skipped: ci-only` dans `reports/gate.json` — jamais en silence. La CI joue le profil complet. **Lecture du critère de succès 1 et de QUAL-01 pour cette phase :** « même verdict pour chaque check joué en local et en CI, mêmes versions, même commande ; la CI est le seul juge ». Le vérificateur de phase doit le lire ainsi, pas comme « pré-push = CI complète ».
- **D-13:** La CI tourne sur les **runners hébergés par GitHub** (`ubuntu-latest` épinglé à une version d'image explicite), jamais sur un runner auto-hébergé : le dépôt est public et du code de fork s'exécuterait sur le homelab. Les workflows utilisent `pull_request`, jamais `pull_request_target`.

### Claude's Discretion
- Découpage exact des plans de la phase 1 (le découpage « squelette → types/lint → archi → tests/mutation → sécurité/deps → CI + verrou » des pages de décision est indicatif), à condition que le verrou (D-01) soit le dernier plan.
- Format des cas d'auto-test (`.patch` + `expected.json` ou équivalent) et du rapport `reports/gate.json`, dans le respect du schéma `{check, tool, version, severity, passed, issues[]}` déjà fixé.
- Détails du parseur shell du hook de garde (D-04).

### Deferred Ideas (OUT OF SCOPE)
- Commit d'approbation signé (clé inaccessible à l'agent) en remplacement du label, si un jour l'agent dispose d'un jeton capable de contourner D-02/D-03.
- Runner CI auto-hébergé : écarté tant que le dépôt est public.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| QUAL-01 | Une commande unique `pnpm quality`, identique en pré-push et en CI ; la CI est l'unique juge | § Architecture (runner `quality/run.ts`, profils `full`/`push`, `gate.json`), § Code Examples (workflow `quality`, ruleset), § Pitfalls 1, 12 |
| QUAL-02 | Typage strict, lint type-aware sans avertissement, `as`/`any`/`!` interdits, complexité plafonnée | `tsconfig.json` et `eslint.config.mjs` **exécutés** (règles et identifiants vérifiés) ; TS 6.0.3 + typescript-eslint 8.73 compatibles |
| QUAL-03 | Frontières d'architecture (dependency-cruiser), code mort (knip), duplication (jscpd) | 5 règles dependency-cruiser **exécutées** ; knip JSON ; `jscpd --baseline-from-ref --fail-on-new-clones` **exécuté** ; piège exit code depcruise |
| QUAL-04 | Secrets (gitleaks), règles Semgrep du projet, CVE high/critical, workflows non épinglés | gitleaks 8.30.1, Semgrep 1.186.0 (7 règles locales **exécutées**), osv-scanner 2.7.1 (**pas de seuil de sévérité natif**), zizmor 1.32.0 `unpinned-uses` **exécuté** |
| QUAL-05 | Propriétés fast-check, mutation Stryker bloquante sur les fichiers modifiés, couverture 100 % domaine pur, plancher global à cliquet | Stryker 10.1.1 + Vitest 5.1.x **fonctionne** (plugins explicites) ; **pas de `--since`** dans StrykerJS ; bug #6335 (faux survivants) ; seuils par glob Vitest 5 **exécutés** |
| QUAL-06 | Compteur d'échappatoires à cliquet ; job d'intégrité (baisse de seuil, retrait d'assertion) | Conception : baseline lue **depuis la ref de base**, scripts d'intégrité exécutés depuis la base ; ancre temporelle serveur (runs Actions) |
| QUAL-07 | Chemins de config, CI et déploiement protégés contre un agent (CODEOWNERS, permissions agent, job d'intégrité) | Syntaxe `permissions.deny`/`PreToolUse` (docs officielles) ; contournements vérifiés (`LEFTHOOK=0`, `disableAllHooks`) ; ruleset existant `ci-required` à remplacer |
| QUAL-08 | Intégration sur PostgreSQL 18 réel (Testcontainers), sans mock de repository, ordre aléatoire | PG 18.7 + Testcontainers + `kysely/migration` + base template + `SET ROLE` **exécutés** sur Docker ; seed Vitest loguée |
| QUAL-09 | Nouvelle dépendance : approbation humaine + âge minimal de publication | pnpm `minimumReleaseAge` (échec d'installation **reproduit**), script de diff de lockfile, label `deps-approved` ; **les pins de CLAUDE.md échouent aujourd'hui** (voir § Standard Stack) |
</phase_requirements>

## Summary

La phase 1 n'est pas un problème d'invention : tout l'outillage retenu (TS 6.0.3, ESLint 10.15 + typescript-eslint 8.73, dependency-cruiser 18.8, knip 6.47, jscpd 5.4.3, Vitest 5.1, fast-check 4.10, StrykerJS 10.1.1, Testcontainers 12.2, gitleaks, Semgrep, osv-scanner, zizmor, mise) a été **installé et exécuté** dans un bac à sable pendant cette recherche, avec les versions épinglées de CLAUDE.md. Les formats de sortie JSON/SARIF permettant à l'auto-test de dire « échoue POUR LA RÈGLE ATTENDUE » sont connus et listés (§ Architecture). Le risque de la phase n'est pas l'outillage mais cinq écarts entre les documents de cadrage et la réalité, détaillés ci-dessous.

**Cinq écarts à connaître avant de planifier.** (1) **Les pins de CLAUDE.md ne s'installent pas aujourd'hui avec la politique supply-chain retenue** : `minimumReleaseAge: 10080` fait échouer `pnpm install` sur vitest 5.1.1, fast-check 4.10.3, knip 6.47.0, testcontainers 12.2.2, typescript-eslint 8.73.0, dependency-cruiser 18.8.0, biome 2.6.8 (publiés il y a moins de 7 jours). Un jeu de pins de repli, tous âgés de plus de 7 jours, a été **installé avec succès** (520 paquets) ; les pins cibles arrivent à maturité entre le 2026-11-22 et le 2026-11-27. (2) **StrykerJS n'a pas de `--since`** (CLAUDE.md §10 le suppose) : le mode « fichiers modifiés » se fait en passant `--mutate <liste issue de git diff>`. De plus, le bug ouvert **#6335** (2026-11-18) fait lire des mutants tués comme survivants avec `vitest-runner` 10.1.1 + Vitest 5.1.x : le seuil bloquant peut échouer au hasard, jamais l'inverse. (3) **Le ruleset `Main` existant sur `main` exige le check `ci-required`** de l'ancien projet Python, sans acteur de contournement : tant qu'il n'est pas remplacé par `quality`, plus rien ne peut être fusionné. (4) **L'agent utilise le jeton `gh` de `sebc-dev`** : l'allowlist d'acteur de D-02 ne distingue donc pas l'agent de l'humain ; seules les règles deny/hook de D-03 protègent le label (limite à documenter, pas à nier). (5) **Le layout `src/` de CLAUDE.md (`src/domain/**`) et celui d'ARCHITECTURE.md (`src/modules/<m>/…`, `src/shared/`) divergent** ; le canari vit dans `src/shared/money` : les globs de couverture et de mutation doivent viser `src/shared/**` et `src/modules/*/{domain,application}/**` (recommandation § Architecture).

Autres résultats vérifiés qui changent le plan : `Migrator` n'est plus exporté par la racine de `kysely` 0.29 (importer depuis `kysely/migration`) ; `dependency-cruiser` rend **exit 0** en sortie `json` même avec des violations (parser `summary.error`) ; osv-scanner 2.7.1 n'a **aucun** seuil de sévérité (parser `groups[].max_severity`) ; `LEFTHOOK=0 git commit` désarme le pré-commit (prouvé) ; les types `Temporal` sont présents dans TS 6.0.3 via `lib: ["ESNext.Temporal"]` ; Node 26.13 exécute des `.ts` sans transpileur (scripts de gate sans `tsx`).

**Primary recommendation:** construire d'abord le **runner `quality/run.ts`** (registre de checks, profils, `gate.json`, vérification des versions d'outils contre `mise.toml`), puis brancher chaque famille de checks avec la config exacte des § Code Examples ; poser le verrou (deny agent, ruleset, job d'intégrité depuis la base) dans le **dernier plan** seulement, et exiger du planificateur trois décisions humaines : stratégie de pins vs âge minimal, mitigation du bug Stryker #6335, remplacement du ruleset `ci-required`.

## Architectural Responsibility Map

Ici les « tiers » sont les lieux d'exécution de la gate, pas des couches applicatives.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Verdict final de la gate (`quality`) | CI GitHub (runner hébergé) | — | D-12/D-13 : la CI est l'unique juge ; le local est un confort contournable |
| Rejouer la gate (`pnpm quality`, profil `push`) | Poste développeur | CI (profil `full`) | Même runner, mêmes versions (mise) ; profil `push` ≤ 60 s |
| Arrêt de l'agent (deny, hook, pré-commit) | Poste développeur (Claude Code + lefthook) | CI (job d'intégrité) | Confort local ; la CI rattrape (D-04) |
| Preuve « approbation humaine » (label) | CI (API GitHub, lecture) | GitHub (ruleset, réglages Actions) | Seule la CI voit les événements de PR ; le ruleset rend le check bloquant |
| Épinglage des outils hors npm et de Node/pnpm | `mise.toml` + `mise.lock` (dépôt) | `jdx/mise-action` en CI | Mêmes versions au poste et en CI (D-11) |
| Politique supply-chain npm | pnpm (`pnpm-workspace.yaml`) | script de diff de lockfile (CI) | pnpm bloque à l'installation ; le script exige l'approbation humaine |
| Intégrité des seuils et des chemins protégés | CI, scripts exécutés **depuis la ref de base** | — | Une PR ne doit pas juger avec son propre code modifié |
| Persistance et rôles PostgreSQL du socle | Base PostgreSQL 18 (migration SQL) | Tests d'intégration Testcontainers | Les invariants vivent en SQL ; les tests le prouvent sur un vrai PG |
| Noyau financier canari (`Money`) | Module pur `src/shared/money` | Tests fast-check + Stryker | Domaine pur, sans I/O : mutation rapide |

## Standard Stack

### Core (versions de CLAUDE.md §3/§4, vérifiées au registre le 2026-11-21)

Les versions et dates de publication ci-dessous ont été lues avec `npm view <pkg> time --json`. `[VERIFIED: npm registry]` porte sur l'existence de la version ; l'identité des paquets est celle de CLAUDE.md (source de projet) croisée avec le seam de légitimité (voir audit).

| Library | Version cible | Publiée | Mûrit (+7 j) | Pin de repli installé OK |
|---------|---------------|---------|--------------|--------------------------|
| typescript | 6.0.3 | 2026-04-16 | ok | — |
| eslint | 10.15.0 | 2026-11-13 | ok (2026-11-20) | — |
| typescript-eslint | 8.73.0 | 2026-11-16 | 2026-11-23 | 8.72.2 |
| eslint-plugin-sonarjs | 4.2.2 | 2026-09-28 | ok | — |
| @eslint-community/eslint-plugin-eslint-comments | 4.8.1 | 2026-09-12 | ok | — |
| @vitest/eslint-plugin | 1.6.28 | 2026-10-22 | ok | — |
| @biomejs/biome | 2.6.8 | 2026-11-15 | 2026-11-22 | 2.6.7 |
| dependency-cruiser | 18.8.0 | 2026-11-16 | 2026-11-23 | 18.7.2 |
| knip | 6.47.0 | 2026-11-20 | 2026-11-27 | 6.45.1 |
| jscpd | 5.4.3 | 2026-11-08 | ok | — |
| vitest, @vitest/coverage-v8 | 5.1.1 | 2026-11-18 | 2026-11-25 | 5.1.0 |
| fast-check | 4.10.3 | 2026-11-18 | 2026-11-25 | 4.10.2 |
| @fast-check/vitest | 0.5.0 | 2026-09-11 | ok | — |
| @stryker-mutator/core, vitest-runner, typescript-checker | 10.1.1 | 2026-10-23 | ok | — |
| testcontainers, @testcontainers/postgresql | 12.2.2 | 2026-11-19 | 2026-11-26 | 12.2.1 |
| kysely | 0.29.9 | 2026-11-12 | ok | — |
| pg, @types/pg | 8.23.1 | 2026-09-30 | ok | — |
| @types/node | 26.6.6 | 2026-10-28 | ok | — |

[VERIFIED: npm registry — `npm view <pkg> time --json`, 2026-11-21]. Les dépendances transitives (`@vitest/mocker`, `@vitest/spy`, sous-paquets `@typescript-eslint/*`) sont soumises à la même contrainte d'âge.

**Preuve que les pins cibles échouent aujourd'hui** [VERIFIED: exécution `pnpm install` 12.21.0 avec `minimumReleaseAge: 10080`, `minimumReleaseAgeStrict: true`] :
```
  × installing dependencies
  ╰─▶ 4 versions do not meet the minimumReleaseAge constraint:
        @vitest/mocker@5.1.1 was published at 2026-11-18T07:36:11.814Z, within
      the minimumReleaseAge cutoff (2026-11-14T13:53:01.650Z)
        knip@6.47.0 was published at 2026-11-20T11:44:38.961Z, ...
        vitest@5.1.1 was published at 2026-11-18T07:35:25.218Z, ...
  help: Run the install interactively to approve these picks, add them to
        minimumReleaseAgeExclude in pnpm-workspace.yaml, or wait for the
        packages to mature.
```
**Preuve que le jeu de repli passe** [VERIFIED: exécution] : avec les pins de repli du tableau, la même politique (`minimumReleaseAge: 10080`, `trustPolicy: no-downgrade`, `blockExoticSubdeps: true`, `strictDepBuilds: true`) installe 520 paquets sans erreur.

**Recommandation (à faire arbitrer, voir Open Questions Q1) :** démarrer avec les pins de repli sous `minimumReleaseAge: 10080`, puis monter vers les pins cibles par PR de dépendances (label `deps-approved`) quand ils ont mûri. Ne **pas** utiliser `minimumReleaseAgeExclude` pour passer en force : ce serait affaiblir la politique que QUAL-09 doit prouver.

### Supporting (hors npm, épinglés dans `mise.toml`)

Tous installés à la version exacte demandée par `mise install` [VERIFIED: exécution mise 2026.11.12] : node 26.13.0, pnpm 12.21.0, gitleaks 8.30.1, osv-scanner 2.7.1, actionlint 1.7.12, zizmor 1.32.0, hadolint 2.15.1, trufflehog 3.100.0, lefthook 2.2.2, `pipx:semgrep` 1.186.0.

| Outil | Backend mise | Remarque |
|-------|--------------|----------|
| node, pnpm, gitleaks, osv-scanner, actionlint, zizmor, hadolint, trufflehog, lefthook | `aqua:` ou `core:node` (`mise registry`) | `mise lock` enregistre URL + checksum + provenance `github-attestations` par plateforme |
| semgrep | `pipx:semgrep` (`pypi:semgrep`) | exige `uv` ; **épingler `uv` ≥ 0.12.10** dans `mise.toml`, sinon `mise lock` n'enregistre pas le graphe de dépendances Python (warning vérifié avec uv 0.12.1) ; avec `uv = "0.13.9"` le graphe est écrit dans `.mise/locks/pipx-semgrep/1.186.0` |
| lefthook | `aqua:evilmartians/lefthook` | préférer mise à la dépendance npm : pas de `postinstall` à autoriser |

**Version de mise et de l'action :** mise 2026.11.12 (release 2026-11-21) ; `jdx/mise-action` v5.2.10 = commit `90f833d396d0cc3674b631d2d225e306476c303a` (tag résolu en `commit`) [VERIFIED: `gh api repos/jdx/mise-action/git/ref/tags/v5.2.10`]. L'action ajoute `--locked` automatiquement si `mise.lock` existe [CITED: github.com/jdx/mise-action README]. Il n'y a **pas** d'entrée `sha256` documentée pour vérifier le binaire mise lui-même : pinner `version:` et le SHA de l'action.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| lefthook via mise | lefthook npm | npm : `postinstall` à autoriser dans `allowBuilds`, contraire à l'esprit de la politique |
| Scripts de gate en TS exécutés par `node` | `tsx` 4.23.15 | Node 26.13 exécute `.ts` nativement [VERIFIED: exécution] ; `tsx` serait signalé inutilisé par knip |
| `kysely-codegen` en phase 1 | différer à la phase 3 | Aucune table en phase 1 : paquet inutilisé = knip rouge. À installer avec la première table |
| `eslint-plugin-security` (advisory) | — | Bruyant ; incompatible avec `--max-warnings 0` dans la même passe : seconde passe ESLint avec sa propre config si retenu |

**Installation (phase 1, strictement ce que knip verra utilisé) :**
```bash
# runtime
pnpm add kysely pg
# dev : lint/types/format
pnpm add -D typescript @types/node @types/pg eslint typescript-eslint eslint-plugin-sonarjs \
  @eslint-community/eslint-plugin-eslint-comments @vitest/eslint-plugin @biomejs/biome
# dev : architecture, dead code, duplication
pnpm add -D dependency-cruiser knip jscpd
# dev : tests
pnpm add -D vitest @vitest/coverage-v8 fast-check @fast-check/vitest testcontainers @testcontainers/postgresql
# dev : mutation
pnpm add -D @stryker-mutator/core @stryker-mutator/vitest-runner @stryker-mutator/typescript-checker
```
(les versions exactes vont dans `package.json` sans `^` ; voir pins de repli ci-dessus). Pas de `zod`, `tsx`, `kysely-codegen`, `tsdown` en phase 1.

**Version verification:** `npm view <pkg> time --json` exécuté pour chaque paquet le 2026-11-21 ; aucune version cible inexistante.

## Package Legitimacy Audit

Seam `gsd-tools query package-legitimacy check --ecosystem npm …` exécuté le 2026-11-21. Les verdicts `SUS` portent tous la raison `too-new` : le seam juge la **récence de la dernière version publiée**, pas l'âge du paquet. Les colonnes Age/Downloads/Repo ci-dessous viennent de `npm view <pkg> time.created`, de `api.npmjs.org/downloads/point/last-week/<pkg>` et de `repository.url` [VERIFIED: npm registry]. Aucun `SLOP`. Le verdict `SUS` est conservé tel quel et le planificateur doit insérer un `checkpoint:human-verify` avant l'installation (ce qui coïncide avec le label `deps-approved` que la phase construit).

| Package | Registry | Age (création) | Downloads/sem | Source Repo | Verdict | Disposition |
|---------|----------|----------------|---------------|-------------|---------|-------------|
| typescript | npm | 14 ans | 450 M | github.com/microsoft/TypeScript | OK | Approved |
| eslint | npm | 13 ans | 217 M | github.com/eslint/eslint | SUS (too-new) | Flagged — checkpoint |
| typescript-eslint | npm | 7 ans | 123 M | github.com/typescript-eslint/typescript-eslint | SUS (too-new) | Flagged — checkpoint |
| eslint-plugin-sonarjs | npm | 8 ans | 6,6 M | github.com/SonarSource/SonarJS | OK | Approved |
| @eslint-community/eslint-plugin-eslint-comments | npm | 3 ans | 4,4 M | github.com/eslint-community/eslint-plugin-eslint-comments | OK | Approved |
| @vitest/eslint-plugin | npm | 2 ans | 6,0 M | vitest-dev/eslint-plugin-vitest | SUS (too-new) | Flagged — checkpoint |
| eslint-plugin-security (optionnel) | npm | 11 ans | 5,2 M | github.com/eslint-community/eslint-plugin-security | SUS (too-new) | Flagged — checkpoint |
| vitest, @vitest/coverage-v8 | npm | 5 ans / 3 ans | 195 M / 67 M | github.com/vitest-dev/vitest | SUS (too-new) | Flagged — checkpoint |
| fast-check | npm | 8 ans | 76 M | github.com/dubzzz/fast-check | SUS (too-new) | Flagged — checkpoint |
| @fast-check/vitest | npm | 3 ans | 0,76 M | github.com/dubzzz/fast-check | OK | Approved |
| @stryker-mutator/core, vitest-runner, typescript-checker | npm | 7 / 3 / 6 ans | 7,4 M / 5,3 M / 1,1 M | github.com/stryker-mutator/stryker-js | SUS (too-new) | Flagged — checkpoint |
| dependency-cruiser | npm | 10 ans | 9,8 M | github.com/sverweij/dependency-cruiser | SUS (too-new) | Flagged — checkpoint |
| knip | npm | 4 ans | 34 M | github.com/webpro-nl/knip | SUS (too-new) | Flagged — checkpoint |
| jscpd | npm | 13 ans | 6,2 M | github.com/kucherenko/jscpd | SUS (too-new) | Flagged — checkpoint |
| @biomejs/biome | npm | 3 ans | 30 M | github.com/biomejs/biome | SUS (too-new) | Flagged — checkpoint |
| kysely | npm | 5 ans | 32 M | github.com/kysely-org/kysely | SUS (too-new) | Flagged — checkpoint |
| pg, @types/pg | npm | 15 ans / 10 ans | 106 M / 105 M | github.com/brianc/node-postgres, DefinitelyTyped | OK | Approved |
| @types/node | npm | 10 ans | 668 M | github.com/DefinitelyTyped/DefinitelyTyped | SUS (too-new) | Flagged — checkpoint |
| testcontainers, @testcontainers/postgresql | npm | 8 ans / 3 ans | 12,8 M / 7,1 M | github.com/testcontainers/testcontainers-node | SUS (too-new) | Flagged — checkpoint |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** tous ceux marqués ci-dessus (raison unique : `too-new` sur la dernière version). `npm view <pkg> scripts.postinstall` non exécuté pour chacun : la politique `allowBuilds` explicite (voir Code Examples) fait échouer l'installation sur tout script non autorisé ; sur ce graphe seuls `cpu-features`, `esbuild`, `protobufjs`, `ssh2` (via testcontainers/tsx) ont un script, tous refusés (`false`) sans conséquence [VERIFIED: exécution `pnpm install` → `ERR_PNPM_IGNORED_BUILDS` puis succès avec `allowBuilds`].

Les paquets non-npm (binaires mise) ne passent pas par ce seam : leur légitimité repose sur les checksums et attestations de `mise.lock` (`provenance = "github-attestations"` pour actionlint, vérifié dans le lockfile généré).

## Architecture Patterns

### System Architecture Diagram

```
 Poste dev (agent ou humain)                         GitHub
 ───────────────────────────                         ──────
 git commit ──► lefthook pre-commit (≤10 s)            PR ouverte / push / label
   biome, eslint (staged), gitleaks --staged,             │
   protected-paths, compteur échappatoires                ▼
        │  (LEFTHOOK=0 / --no-verify = contournable)   workflow quality.yml  (pull_request, jamais _target)
 git push ──► lefthook pre-push (≤60 s)                  job "quality"  (ubuntu-24.04, perms minimales)
   pnpm quality --profile push                             ├─ checkout head  + checkout base (scripts de confiance)
        │                                                  ├─ jdx/mise-action (--locked) ──► mise.toml/mise.lock
        ▼                                                  ├─ pnpm install --frozen-lockfile (politique supply-chain)
 pnpm quality ─► quality/run.ts ◄─────────────────────────┤─ pnpm quality  (profil full)
   registre de checks                                       │     └─► reports/gate.json  (artefact)
   ├ typecheck tsc            ──► texte TSxxxx              ├─ integrity   (depuis BASE : seuils, chemins, assertions)
   ├ lint eslint -f json      ──► ruleId                    ├─ approvals   (API : events labeled + runs Actions)
   ├ format biome                                           ├─ deps-guard  (diff package.json / lockfile)
   ├ arch depcruise json      ──► summary.violations        └─ selftest    (si chemin protégé touché, ou nightly)
   ├ deadcode knip json       ──► issues[]                job "reset-approval" (synchronize, perms write, best effort)
   ├ duplication jscpd json   ──► statistics.newClones       │
   ├ secrets gitleaks json    ──► RuleID                    ▼
   ├ sast semgrep json        ──► check_id                 ruleset sur main : check requis "quality"
   ├ cve osv json             ──► groups[].max_severity      (integration_id 15368 = GitHub Actions)
   ├ workflows actionlint+zizmor ► ident                    merge humain (aucun contournement)
   ├ tests vitest (unit+int, shuffle, seed) + coverage
   └ mutation stryker (--mutate <diff>) ► mutation.json
```

Lecture : le même `quality/run.ts` est invoqué partout ; seul le profil change. Les jobs `integrity`/`approvals`/`deps-guard` ne sont **pas** des checks locaux : ils lisent l'état GitHub et n'existent qu'en CI (déclarés `skipped: ci-only` hors CI, jamais en silence).

### Recommended Project Structure

```
mise.toml                  # outils + node + pnpm + uv (protégé)
mise.lock                  # checksums, provenance (protégé)
.mise/locks/**             # graphe Python de semgrep (protégé)
package.json  pnpm-workspace.yaml  pnpm-lock.yaml     # protégés
tsconfig.json  eslint.config.mjs  biome.json  vitest.config.ts  stryker.config.json
.dependency-cruiser.cjs  knip.json  .jscpd.json  .gitleaks.toml  lefthook.yml
.github/workflows/quality.yml  nightly.yml  .github/CODEOWNERS  .github/zizmor.yml
.claude/settings.json      # deny + hook de garde (protégé avec CLAUDE.md, cf. D-05)
quality/
├── run.ts                 # point d'entrée de `pnpm quality`
├── checks/*.ts            # un fichier par check (tool, severity, profils, parseur de sortie)
├── gate-report.ts         # schéma + écriture de reports/gate.json
├── integrity.ts           # exécuté depuis la ref de base en CI
├── approvals.ts           # label : acteur, horodatage, ancre serveur
├── deps-guard.ts          # diff package.json / pnpm-lock.yaml, âge npm
├── escape-hatches.ts      # compteur à cliquet
├── baseline.json          # seuils et compteurs (cliquet)
├── protected-paths.json   # liste unique (hook, lefthook, integrity, CODEOWNERS)
├── agent-guard/           # hook PreToolUse (D-06)
└── selftest/              # cas : patch + expected.json ; runner worktree
semgrep/                   # règles du projet + tests
src/
├── shared/money/          # canari D-09 (pur) ; autres éléments purs partagés
├── modules/<m>/{domain,application,adapters/{db,http,aggregator},public.ts}   # phases ≥ 3
├── mcp/tools/             # phases ≥ 2 : aucun import de adapters/*
├── db/                    # pool, MigrationProvider SQL, runner (infra)
db/migrations/0001_foundation.sql   # SQL brut forward-only
test/                      # intégration PG (`*.int.test.ts`), méta-tests
```

**Réconciliation du layout (Open Question Q5).** CLAUDE.md §10 parle de `src/domain/**`, `src/application/**`, `adapters/{db,http,aggregator}`; ARCHITECTURE.md range tout sous `src/modules/<m>/` et `src/shared/`; D-09 place le canari dans `src/shared/money`. Recommandation : traiter comme « pur » `src/shared/**` et `src/modules/*/domain/**` ; Stryker/couverture 100 % visent ces deux globs plus `src/modules/*/application/**` pour la mutation ; les règles dependency-cruiser ci-dessous sont écrites pour ce layout. À faire valider avant de figer les globs (un changement ultérieur touche des fichiers protégés).

### Pattern 1 : runner unique, registre de checks, rapport normalisé

**What:** `quality/run.ts` exécute des checks déclarés dans un registre ; chaque check lance **un outil par `spawn` sans shell**, lit **sa sortie structurée** (jamais le code de sortie seul, voir Pitfall 3), vérifie la version de l'outil contre `mise.toml`, et produit `{check, tool, version, severity, passed, issues[]}`. Un champ additif `status: "passed" | "failed" | "skipped"` et `skipped_reason` (ex. `ci-only`) porte le profil `push` (D-12). **When:** toujours. **Règle de verdict :** le profil `full` échoue si un check `blocking` est `failed` **ou** `skipped`.
**Example:** voir Code Examples (« Rapport gate.json »).

### Pattern 2 : intégrité jugée par le code de la base

**What:** en CI, `quality/integrity.ts`, `approvals.ts`, `deps-guard.ts` et `protected-paths.json` sont lus/exécutés **depuis une copie de la ref de base** (`git worktree add ../base origin/<base_ref>`), jamais depuis la PR. Sinon une PR qui modifie le script d'intégrité (ou la liste des chemins protégés) se juge elle-même. **When:** tout job qui compare la PR à une baseline. Le premier PR de la phase (base = ancien `main` Python, sans `quality/`) est un cas d'amorçage : baseline absente côté base = « amorçage », approbation humaine requise une fois.
**Limite documentée :** le workflow `quality.yml` de la PR est celui qui s'exécute (`pull_request`) ; une PR peut donc le réécrire. Contrôle restant : fusion humaine seule (aucun bypass, aucune auto-fusion), lecture du diff `.github/**` par `sebc-dev`. [CITED: .claude/CLAUDE.md §10 « Limite : une PR peut modifier son propre workflow »]
**Révision du plan (2026-11-21) :** cette limite est fermée par un juge hors PR. Le job de la PR est renommé `gate` et n'est pas requis ; le seul check requis, le statut `quality`, est publié par un workflow `workflow_run` (`quality-verdict`), dont GitHub lit toujours la définition sur la branche par défaut, avec le jeton d'une application GitHub dédiée dont la clé vit dans un environnement restreint à `main`. Ce juge rejoue approbations, intégrité et dépendances depuis `main` sur la tête lue comme données, sans exécuter de code de la PR. Une PR qui réécrit son workflow obtient `gate` vert mais `quality` rouge (`protected-path-changed`). La documentation GitHub des rulesets confirme qu'on peut fixer une application comme source attendue d'un statut requis et qu'un statut posé par un autre acteur ne permet pas la fusion. Plans 01-07 (juge) et 01-13 (bascule).

### Pattern 3 : auto-test = patch jetable + règle attendue

**What:** `quality/selftest/<cas>/{patch,expected.json}` ; le runner fait `git worktree add --detach <tmp> HEAD`, `git apply`, installe (`pnpm install --frozen-lockfile`, store partagé : ~1 s à chaud [VERIFIED: install à chaud 1,2 s]), lance **uniquement** le check visé (`pnpm quality --only <id> --json`) et vérifie `expected.json` = `{check, rule}`. Le cas est vert si le check échoue **et** que `rule` figure parmi les identifiants de sortie. Tables d'extraction dans « Identifiants de règle par outil » ci-dessous. **Piège secret :** un patch qui contient un faux secret littéral déclenche gitleaks sur le dépôt lui-même ; générer le secret **à l'application** (gabarit + `crypto.randomBytes`) ou l'allowlister dans `.gitleaks.toml`.

### Identifiants de règle par outil (extraction pour l'auto-test)

| Check | Source structurée | Où lire l'identifiant | Vérifié |
|-------|-------------------|-----------------------|---------|
| lint (`as`, `any`, complexité, `parseFloat`, directive inutile…) | `eslint -f json` | `messages[].ruleId` ; **directive `eslint-disable` inutile : `ruleId: null`** (matcher le message) | exécuté |
| typecheck (`noUncheckedIndexedAccess`…) | texte `tsc` (pas de JSON), exit 2 | `error TS2322` etc. | exécuté |
| arch | `depcruise --output-type json` | `summary.violations[].rule.name` ; compter `summary.error` | exécuté |
| code mort | `knip --reporter json` (exit 1) | `issues[].{files,exports,dependencies,devDependencies,unlisted}` | exécuté |
| duplication | `jscpd --reporters json` + `--baseline-from-ref` | `statistics.newClones` (exit 1 avec `--fail-on-new-clones`) | exécuté |
| secrets | `gitleaks git --staged|… --report-format json` | `[].RuleID` (ex. `github-pat`), exit 1 | exécuté |
| SAST projet | `semgrep --config semgrep --json` | `results[].check_id` **préfixé par le chemin du dossier** (`rules.prosperity.<id>`) : matcher le suffixe | exécuté |
| workflows | `zizmor --format json` ; `actionlint` | `[].ident` (`unpinned-uses`, `template-injection`, `excessive-permissions`, `artipacked`) | zizmor exécuté |
| CVE | `osv-scanner scan source -L pnpm-lock.yaml --format json` | `results[].packages[].groups[].max_severity` (pas de seuil natif) | exécuté |
| mutation | `reports/mutation/mutation.json` | `files[<f>].mutants[].{status,mutatorName,location}` ; exit 1 sous `thresholds.break` | exécuté |
| couverture | stderr Vitest + `json-summary` | `ERROR: Coverage for lines (50%) does not meet "src/shared/**" threshold (100%)` | exécuté |

### Pattern 4 : approbation par label liée au dernier push (D-02)

**What:** `approvals.ts` (exécuté depuis la base) appelle l'API pour la PR courante : (1) `GET /repos/{o}/{r}/issues/{n}/events` → événements `labeled` avec `actor.login`, `label.name`, `created_at` ; (2) **ancre « dernier push » côté serveur** : `GET /repos/{o}/{r}/actions/runs?head_sha=<sha>&event=pull_request` → plus petit `created_at` = moment où GitHub a vu ce SHA (les commits forgent leur date, pas les runs). Approuvé si le dernier `labeled` d'un label requis a `actor.login` dans l'allowlist versionnée **et** `created_at` > ancre, **et** le label est encore présent. Les `unlabeled` annulent. [VERIFIED: appels `gh api` sur une PR publique — champs `actor.login`, `label.name`, `created_at` des `labeled` ; runs filtrés par `head_sha` avec `created_at` serveur ≈ 5 s après la date du commit]
**Pourquoi pas les dates de commit :** `committer.date` est contrôlable par l'auteur ; `head_ref_force_pushed` n'existe que pour les force-push. **Retrait du label :** job séparé `reset-approval` (`synchronize`, `pull-requests: write`, `continue-on-error: true`) ; l'autorité reste la comparaison d'horodatage, le retrait n'est que de l'hygiène. Pour une PR de fork, `GITHUB_TOKEN` est en lecture seule [CITED: docs.github.com — « The `GITHUB_TOKEN` has read-only permissions in pull requests from forked repositories »] : le retrait échoue sans conséquence, la lecture des événements fonctionne. Permissions du job `quality` : `contents: read`, `pull-requests: read`, `actions: read`.

### Pattern 5 : arrêt de l'agent en trois couches (D-04), ce que Claude Code fait déjà

**What:** [CITED: code.claude.com/docs/en/permissions] « Deny rules … `Edit` rules apply to all built-in tools that edit files » ; les règles `Edit`/`Read` s'appliquent aussi aux **cibles de redirection (`>`, `>>`, `2>`)** et aux commandes de fichiers que Claude Code reconnaît (`sed`, `tee`, `cat`, `head`, `tail`). Donc la couche 1 couvre déjà une partie de la couche 2 ; le hook ne doit viser que `mv`, `cp`, `rm`, `git checkout --`/`restore`, `pnpm add`, et les contournements listés au Pitfall 7. **Limite officielle :** « a deny or ask rule … isn't a security boundary around the program » (`/usr/bin/curl`, `sh -c '…'`, `git -C . push` ne sont pas arrêtés) : d'où le hook + la CI.
**Syntaxe :** `Edit(/quality/**)` (le `/` unique ancre à la racine du répertoire de travail du fichier de settings) ; pour un fichier à n'importe quelle profondeur : `Edit(**/eslint.config.*)`. Un `Write(...)` avec chemin **ne matche pas** : utiliser `Edit(...)`. Ordre d'évaluation : deny > ask > allow, **tous niveaux confondus** : un deny de `settings.json` ne peut pas être levé par `settings.local.json`. Les `hooks` de plusieurs fichiers de settings **fusionnent** et tournent en parallèle ; un hook identique défini deux fois ne tourne qu'une fois. [CITED: code.claude.com/docs/en/permissions, /hooks]
**Où sont les hooks GSD :** dans **`.claude/settings.local.json`** (non versionné, ignoré par le gitignore **global** de l'utilisateur, pas par le dépôt), pas dans un `settings.json` [VERIFIED: lecture du fichier, `git check-ignore -v` → `/home/negus/.config/git/ignore:25`]. Créer un `.claude/settings.json` versionné n'écrase donc rien. Mais `settings.local.json` peut contenir `"disableAllHooks": true` [CITED: code.claude.com/docs/en/hooks] : le deny `Edit(/.claude/settings*.json)` (qui couvre `settings.local.json`) est indispensable et fait partie de D-05.

### Anti-Patterns to Avoid
- **Se fier au code de sortie d'un outil** : depcruise en `json` rend 0, osv-scanner échoue sur n'importe quelle vuln. Parser la sortie structurée.
- **`pnpm exec stryker` sans `plugins` explicites** : échec `Cannot find Checker plugin "typescript"` sous node_modules strict de pnpm.
- **Baseline et scripts d'intégrité lus depuis la PR.**
- **`minimumReleaseAgeExclude`/`dangerouslyAllowAllBuilds` pour « faire passer »** l'installation.
- **Installer un paquet « au cas où »** (zod, tsx, kysely-codegen) : knip le signale et le budget d'échappatoires est à 0.
- **`vi.mock(` dans les tests d'intégration** : compté comme échappatoire ; PG réel uniquement.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Épinglage/checksum des binaires d'outils | téléchargements `curl` + sha dans un script | `mise.toml` + `mise.lock` + `jdx/mise-action` | checksum, provenance, mode `--locked` natifs |
| Politique âge/provenance des dépendances | parseur d'âge npm maison à l'installation | pnpm `minimumReleaseAge`, `trustPolicy`, `blockExoticSubdeps`, `allowBuilds` | recontrôle chaque entrée du lockfile ; reproduit |
| Détection de cycles et de frontières | script de parsing d'imports | dependency-cruiser (`circular`, `path`/`pathNot`, captures `$1`) | résolution TS, groupes de capture |
| Complexité cognitive | calcul maison | `sonarjs/cognitive-complexity` | |
| Diff de clones | hash maison | `jscpd --baseline-from-ref --fail-on-new-clones` | exécuté |
| Mutation | mutateur maison | StrykerJS | |
| PG de test | PG local manuel / PGlite | Testcontainers + `postgres:18.7-trixie@sha256:…` | PGlite écarté par CLAUDE.md |
| Migrations | runner SQL maison | `kysely/migration` `Migrator` + `MigrationProvider` qui lit des `.sql` | verrou de migration, table d'historique |
| Détection de secrets | regex maison | gitleaks | |
| Jeu de règles CI | revue manuelle | actionlint + zizmor | |
| Montants | `Number`/décimaux | `bigint` + parseur chaîne maison (D-09, seul « maison » légitime) | invariant du domaine |

**Key insight:** la seule logique maison légitime est la **colle** : runner/rapport, auto-test, approbation par label, compteur d'échappatoires, diff de dépendances, hook de garde. Tout le reste est de la configuration d'outils existants.

## Common Pitfalls

### Pitfall 1 : pins cibles refusés par la politique d'âge
**What goes wrong:** `pnpm install` échoue (`4 versions do not meet the minimumReleaseAge constraint`) ; l'agent « corrige » en baissant l'âge ou en ajoutant `minimumReleaseAgeExclude`. **Why:** versions publiées il y a 1 à 6 jours. **How to avoid:** pins de repli (tableau), puis PR de montée avec label ; le job d'intégrité refuse une baisse de `minimumReleaseAge` ou tout ajout à `minimumReleaseAgeExclude`. **Warning signs:** modification de `pnpm-workspace.yaml` sans label.

### Pitfall 2 : Stryker sous pnpm (plugins introuvables)
**What goes wrong:** `Cannot find Checker plugin "typescript"`. **How to avoid:** `"plugins": ["@stryker-mutator/vitest-runner", "@stryker-mutator/typescript-checker"]` explicite [VERIFIED: échec reproduit puis corrigé]. **Aussi :** ne pas utiliser `--logLevel debug` avec `vitest-runner` 10.1.1 + Vitest 5 (issue #6272, JSON circulaire).

### Pitfall 3 : codes de sortie trompeurs
**depcruise** `--output-type json` → exit 0 avec 5 erreurs ; `--output-type err` → exit 5 [VERIFIED: exécution]. **osv-scanner** 2.7.1 : aucun `--severity` ; exit non nul pour toute vuln, y compris moyenne : le jeu d'outils planifié en contient déjà 7 (`glob@10.5.0`, `minimatch@9.0.9/10.2.6`, `qs@6.15.1` ; `max_severity` 6,3 à 6,9) [VERIFIED: scan du lockfile du bac à sable]. Seuil « high/critical » = `max_severity >= 7.0` calculé par le runner ; exceptions documentées via `osv-scanner.toml` (protégé).

### Pitfall 4 : faux survivants Stryker (#6335)
**What goes wrong:** `vitest-runner` démarre Vitest avec `bail: 1` ; la course entre l'annulation et le résultat fait scorer **Survived** un mutant tué. Le score est faussé **uniquement vers le bas** (4 exécutions sur 12 ont affiché 1 survivant sur 8 dans le rapport de l'issue). Avec `thresholds.break: 80` sur un petit fichier, le gate peut échouer au hasard. **How to avoid:** (a) `disableBail: true` (option cœur documentée par `stryker run --help` : « Force the test runner to keep running tests, even when a mutant is already killed ») — **efficacité sur ce bug non prouvée**, à mesurer en Wave 0 par 20 exécutions du canari ; (b) en dernier recours, une relance unique du check mutation ne rejouant que les survivants (via `--mutate file:L1-L2` issu de `mutation.json`) avant de conclure. Le sens du biais est sûr pour l'auto-test « test faible » (un faux survivant ne peut pas masquer un vrai).

### Pitfall 5 : `--since` n'existe pas dans StrykerJS
CLAUDE.md §10 écrit `--since origin/main`. `stryker run --help` (10.1.1) ne propose que `--mutate`, `--incremental`, `--incrementalFile`, `--force`, `--testFiles`, `--dryRunOnly`… [VERIFIED: sortie de `--help`]. **How to avoid:** le runner calcule `git diff --name-only --diff-filter=ACMR origin/<base>...HEAD`, filtre sur les globs de mutation (hors `*.test.ts`) et passe `--mutate a.ts,b.ts` ; liste vide = check `passed` avec note, pas `skipped`. **Ne jamais** committer le fichier incrémental (#6004 ; ajouter `reports/` et `*.stryker-incremental.json` au `.gitignore`) et ne pas utiliser `--incremental` en CI.

### Pitfall 6 : `Migrator` introuvable
`import { Migrator } from 'kysely'` → `TypeError: Migrator is not a constructor` avec Kysely 0.29.9 : l'export racine ne contient plus que des `*ConnectionProvider` ; `package.json` exporte `./migration` [VERIFIED: exécution + `exports` du paquet]. Importer `Migrator`, `FileMigrationProvider`, types `Migration`/`MigrationProvider` depuis `kysely/migration`. `sql.raw` (nécessaire pour exécuter un fichier SQL) est interdit par la règle de domaine : l'autoriser **par un override de config ESLint ciblé sur le seul fichier fournisseur** (pas un commentaire `eslint-disable`).

### Pitfall 7 : contournements locaux de l'agent
Prouvés : `LEFTHOOK=0 git commit` passe (le script de hook généré contient `if [ "$LEFTHOOK" = "0" ]; then exit 0`) [VERIFIED: lecture du hook généré + commit réussi]. Autres vecteurs à refuser dans le hook : `--no-verify`, `-n` de `git commit`, `git -c core.hooksPath=…`, `git config core.hooksPath`, `lefthook uninstall`, `GATE_CHANGE_APPROVED=` (une variable d'autorisation posée par l'agent lui-même est triviale : refuser toute commande qui la contient), `disableAllHooks`, écriture dans `.claude/settings*.json`, `gh api` hors GET, `gh auth token`, `curl`/`wget` vers `api.github.com`. Un deny `Bash(...)` « matche au-delà d'une affectation de variable en tête » [CITED: permissions] mais pas `sh -c '…'` : c'est le hook qui lit la chaîne brute.

### Pitfall 8 : l'agent a le jeton de l'humain
`gh` est authentifié en tant que `sebc-dev` (`gh auth status`) ; un `labeled` posé par l'agent aurait `actor.login = sebc-dev` et passerait l'allowlist. Les règles D-03 sont donc **la seule barrière** (pas une défense en profondeur). Étendre le deny : `gh api` en écriture (`-X POST|PUT|PATCH|DELETE`, `--method`), `gh api graphql` avec `addLabelsToLabelable`, `gh auth token`, `gh pr edit*`, `gh issue edit*`, `gh label*`, `gh api*rulesets*`, `gh api*actions/permissions*`. Résiduel assumé : `sh -c`, binaire par chemin absolu ; atténuation durable = jeton distinct sans droit d'écriture de labels (idée différée) ou commit signé.

### Pitfall 9 : le ruleset `Main` existant bloque tout
`GET /repos/sebc-dev/prosperity/rulesets/17645569` : règles `deletion`, `non_fast_forward`, `required_status_checks` avec `{"context":"ci-required","integration_id":15368}`, `bypass_actors: []`, cible `~DEFAULT_BRANCH`, `enforcement: active` [VERIFIED: gh api]. Aucune exigence de PR. Le plan de verrou doit **remplacer** `ci-required` par `quality` (même `integration_id` 15368 = GitHub Actions, pour qu'une autre application ne puisse pas usurper le check) et ajouter une règle `pull_request`. Cette action est humaine (deny agent sur `gh api*rulesets*`).

### Pitfall 10 : `required check` jamais rapporté
Un workflow filtré par `paths:` ou un job renommé laisse `quality` en attente éternelle. Le workflow `quality.yml` n'a **aucun** filtre `paths`, un seul job nommé exactement `quality`, et les jobs optionnels sont des **steps conditionnels** du même job (pas des jobs séparés requis).

### Pitfall 11 : auto-référence du compteur d'échappatoires
`quality/escape-hatches.ts` contient les chaînes `@ts-ignore`, `eslint-disable`, `vi.mock(` ; les patchs d'auto-test aussi. Compter seulement `src/**`, `test/**` et les configs racine, en excluant `quality/**`, `semgrep/**`, `.planning/**`, `.claude/**`. Lister via `git ls-files -co --exclude-standard` (couvre les fichiers non commités du worktree d'auto-test, que `git grep` seul manquerait).

### Pitfall 12 : knip et API publique du canari
Les exports de `src/shared/money` ne sont utilisés que par des tests. Avec la config knip par défaut (fichiers de test = entrées), ils sont considérés utilisés [VERIFIED partiellement : knip signale bien les fichiers/exports/dépendances orphelins, y compris `kysely`, `pg`, `fast-check`, `jscpd`… tant qu'aucun usage n'existe]. Un run `--production` signalerait ces exports : à ne pas activer en phase 1 (Q6). Les binaires (`biome`, `jscpd`, `depcruise`) sont vus comme utilisés seulement s'ils apparaissent dans `package.json` `scripts` ou dans un fichier d'entrée : les invoquer depuis `quality/checks/*.ts` (entrée knip) et les déclarer dans `scripts`.

### Pitfall 13 : le premier PR contre l'ancien `main`
Base = `origin/main` contient le code Python hérité (`.github/workflows/push.yml`, `.pre-commit-config.yaml`…). `jscpd --baseline-from-ref`, la diff de dépendances, la liste Stryker et l'intégrité comparent à cette base : prévoir le mode « amorçage » (baseline absente → label d'approbation une fois ; jscpd sur `--format typescript` ne voit pas le Python). Vérifier aussi les workflows hérités qui se déclencheraient sur la PR.

### Pitfall 14 : `.claude/CLAUDE.md` protégé vs GSD
GSD réécrit des sections de `.claude/CLAUDE.md` (profil développeur, sections générées). `Edit(/.claude/CLAUDE.md)` en deny bloquera ces mises à jour par l'agent : accepter la friction (l'humain lève temporairement) ou protéger seulement en CI. À trancher au plan de verrou (Q8).

## Code Examples

Tous les extraits marqués **exécutés** ont tourné dans le bac à sable (pnpm 12.21.0, Node 26.13.0, TS 6.0.3) ; les autres sont des squelettes de conception.

### `mise.toml` (exécuté : install de 10 outils aux versions exactes ; `mise lock` OK)
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
Générer et committer `mise.lock` (+ `.mise/locks/**`) avec `mise lock --platform linux-x64` ; en CI `jdx/mise-action` ajoute `--locked`. Note : `mise exec` ne trouve les outils que dans un répertoire qui contient (ou hérite de) un `mise.toml` approuvé (`mise trust`).

### `pnpm-workspace.yaml` (exécuté)
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
[CITED: pnpm.io/settings/dependency-resolution, /settings/build] : tous ces réglages vivent dans `pnpm-workspace.yaml` (« Only auth, registry, TLS, proxy, and `local-address` settings are read from `.npmrc` files ») ; défaut `minimumReleaseAge` = 1440 min ; `strictDepBuilds` et `blockExoticSubdeps` activés par défaut ; `trustLockfile` à `false` par défaut (chaque entrée du lockfile est revérifiée à l'installation, y compris avec `--frozen-lockfile` : « ✓ Lockfile passes supply-chain policies »). Ne pas mettre `.npmrc` pour ces réglages.

### `tsconfig.json` (exécuté ; `Temporal.PlainDate` compile)
```json
{
  "compilerOptions": {
    "target": "ES2025", "lib": ["ES2025", "ESNext.Temporal"],
    "module": "NodeNext", "moduleResolution": "NodeNext", "types": ["node"],
    "strict": true, "noUncheckedIndexedAccess": true, "exactOptionalPropertyTypes": true,
    "noImplicitOverride": true, "noFallthroughCasesInSwitch": true,
    "noUnusedLocals": true, "noUnusedParameters": true, "noPropertyAccessFromIndexSignature": true,
    "verbatimModuleSyntax": true, "erasableSyntaxOnly": true, "allowImportingTsExtensions": true,
    "isolatedModules": true, "skipLibCheck": true, "noEmit": true
  },
  "include": ["src", "test", "quality", "*.ts", "*.mjs"]
}
```
`lib.esnext.temporal.d.ts` existe dans `typescript@6.0.3` [VERIFIED: `tsc --listFilesOnly`] ; violation `noUncheckedIndexedAccess` → `error TS2322: Type 'number | undefined' …`, exit 2. Imports relatifs avec extension `.ts`.

### `eslint.config.mjs` (exécuté : règles et identifiants vérifiés)
```js
import tseslint from 'typescript-eslint';
import sonarjs from 'eslint-plugin-sonarjs';
import comments from '@eslint-community/eslint-plugin-eslint-comments/configs';
import vitest from '@vitest/eslint-plugin';

export default tseslint.config(
  { ignores: ['reports/**', 'coverage/**', '.stryker-tmp/**', 'node_modules/**'] },
  {
    files: ['**/*.ts'],
    extends: [tseslint.configs.strictTypeChecked, tseslint.configs.stylisticTypeChecked,
              sonarjs.configs.recommended, comments.recommended],
    languageOptions: { parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname } },
    linterOptions: { reportUnusedDisableDirectives: 'error' },
    rules: {
      '@typescript-eslint/consistent-type-assertions': ['error', { assertionStyle: 'never' }],
      '@typescript-eslint/no-non-null-assertion': 'error',
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/ban-ts-comment': 'error',
      '@typescript-eslint/switch-exhaustiveness-check': 'error',
      '@typescript-eslint/strict-boolean-expressions': 'error',
      'sonarjs/cognitive-complexity': ['error', 10],
      'max-lines-per-function': ['error', { max: 60, skipBlankLines: true, skipComments: true }],
      'max-depth': ['error', 3], 'max-params': ['error', 4],
      'max-lines': ['error', { max: 300, skipBlankLines: true, skipComments: true }],
      '@eslint-community/eslint-comments/require-description': 'error',
      'no-restricted-syntax': ['error',
        { selector: "CallExpression[callee.name='parseFloat']", message: 'parseFloat interdit' },
        { selector: "MemberExpression[object.name='Math'][property.name='round']", message: 'Math.round interdit dans le domaine' }],
    },
  },
  { files: ['**/*.test.ts'], ...vitest.configs.recommended,
    rules: { ...vitest.configs.recommended.rules, 'vitest/expect-expect': 'error',
             'vitest/no-disabled-tests': 'error', 'vitest/no-conditional-expect': 'error' } },
);
```
Comportements vérifiés : `as const` reste autorisé avec `assertionStyle: 'never'` ; violations rendues avec `ruleId` `@typescript-eslint/consistent-type-assertions`, `@typescript-eslint/no-explicit-any`, `no-restricted-syntax`, `sonarjs/cognitive-complexity`, `max-depth`, `@eslint-community/eslint-comments/require-description`, `@typescript-eslint/ban-ts-comment`, `vitest/expect-expect`, `vitest/no-disabled-tests`, `sonarjs/no-skipped-tests`, `sonarjs/assertions-in-tests` ; une directive `eslint-disable` inutile sort avec **`ruleId: null`**. Les règles de domaine (`no-restricted-syntax` ciblées `domain/**`, `Date`, `process.env`, `console`, `sql.raw`) vont dans des blocs `files:` séparés ; l'exception `sql.raw` du fournisseur de migrations est un bloc `files: ['src/db/sql-migration-provider.ts']`.

### `.dependency-cruiser.cjs` (exécuté : 5 règles déclenchées sur 5 violations ; cycle détecté)
```js
module.exports = {
  forbidden: [
    { name: 'no-circular', severity: 'error', from: {}, to: { circular: true } },
    { name: 'not-to-unresolvable', severity: 'error', from: {}, to: { couldNotResolve: true } },
    { name: 'domain-is-pure', severity: 'error',
      from: { path: '^src/(shared|modules/[^/]+/domain)/' },
      to: { pathNot: '^src/(shared|modules/[^/]+/domain)/', dependencyTypesNot: ['type-only'] } },
    { name: 'mcp-tools-no-db', severity: 'error',
      from: { path: '^src/mcp/' }, to: { path: '^src/modules/[^/]+/adapters/' } },
    { name: 'cross-module-public-only', severity: 'error',
      from: { path: '^src/modules/([^/]+)/' },
      to: { path: '^src/modules/([^/]+)/', pathNot: ['^src/modules/$1/', '^src/modules/[^/]+/public\\.ts$'] } },
  ],
  options: { tsConfig: { fileName: 'tsconfig.json' }, doNotFollow: { path: 'node_modules' },
             exclude: { path: '\\.test\\.ts$' } },
};
```
Exécution : `depcruise src --config .dependency-cruiser.cjs --output-type json` puis lire `summary.violations[].rule.name`/`summary.error` (exit 0 même en échec). `domain-is-pure` rejette aussi les imports `npm`/`core` (`node:url`, `pg`, `fs`) hors `dependencyTypesNot`. À étendre dans le même diff que tout nouveau dossier de module (règle ARCHITECTURE.md). Règles `adapters/db` ↔ `src/db/` (seuls `modules/*/adapters/db`, `composition`, `worker` importent `src/db`) à ajouter.

### `stryker.config.json` (exécuté : score 100 % → exit 0 ; test faible → 40 % → exit 1)
```json
{
  "plugins": ["@stryker-mutator/vitest-runner", "@stryker-mutator/typescript-checker"],
  "testRunner": "vitest", "checkers": ["typescript"], "tsconfigFile": "tsconfig.json",
  "mutate": ["src/shared/**/*.ts", "src/modules/*/{domain,application}/**/*.ts", "!**/*.test.ts"],
  "coverageAnalysis": "perTest", "reporters": ["json", "clear-text"], "incremental": false,
  "thresholds": { "high": 90, "low": 80, "break": 80 }
}
```
Appel diff-scopé : `stryker run --mutate <fichiers du diff>` (la ligne CLI remplace `mutate`). `# errors` du tableau = erreurs de compilation de mutants (`CompileError`), pas des échecs. Rapport : `reports/mutation/mutation.json` (`schemaVersion: "1.0"`).

### `vitest.config.ts` (exécuté : projets, shuffle, seuils par glob, seed loguée)
```ts
import { defineConfig } from 'vitest/config';
export default defineConfig({
  test: {
    passWithNoTests: false, allowOnly: false,
    sequence: { shuffle: { files: true, tests: true } },
    projects: [
      { extends: true, test: { name: 'unit', include: ['src/**/*.test.ts'] } },
      { extends: true, test: { name: 'integration', include: ['test/**/*.int.test.ts'],
          testTimeout: 120_000, hookTimeout: 120_000 } },
    ],
    coverage: { provider: 'v8', include: ['src/**/*.ts'], exclude: ['src/**/*.test.ts'],
      reporter: ['text', 'json-summary'],
      thresholds: { 'src/shared/**': { lines: 100, branches: 100, functions: 100, statements: 100 } } },
  },
});
```
Vitest 5.1 imprime `Running tests with seed "1795270039556"` ; relecture : `--sequence.seed=<n>`. Le plancher global (85/80) et le cliquet « jamais inférieur à `main` » sont comparés par `integrity.ts` à `quality/baseline.json` lu depuis la base. Couverture mesurée sur le projet `unit` seulement (`--project unit --coverage`).

### Intégration PG : fournisseur SQL + test (exécuté sur `postgres:18.7-trixie`)
```ts
// src/db/sql-migration-provider.ts
import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { sql, type Kysely } from 'kysely';
import type { Migration, MigrationProvider } from 'kysely/migration';

export class SqlFileMigrationProvider implements MigrationProvider {
  readonly #dir: string;
  constructor(dir: string) { this.#dir = dir; }
  async getMigrations(): Promise<Record<string, Migration>> {
    const files = (await readdir(this.#dir)).filter((f) => f.endsWith('.sql')).sort();
    const out: Record<string, Migration> = {};
    for (const f of files) {
      const text = await readFile(join(this.#dir, f), 'utf8');
      out[f.replace(/\.sql$/, '')] = { up: async (db: Kysely<unknown>) => { await sql.raw(text).execute(db); } };
    }
    return out;   // forward-only : pas de `down`
  }
}
```
```sql
-- db/migrations/0001_foundation.sql (exécuté)
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'prosperity_app') THEN
    CREATE ROLE prosperity_app NOLOGIN NOINHERIT NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
END $$;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA IF NOT EXISTS prosperity;
GRANT USAGE ON SCHEMA prosperity TO prosperity_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA prosperity GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO prosperity_app;
```
Test vérifié : conteneur `postgres:18.7-trixie@sha256:eb63372c1e05c755f55fa30cbd07aecc443676fc6c0fa90b9002d01537841e1a` ; `CREATE DATABASE tpl` → migration → `CREATE DATABASE t_w1_f1 TEMPLATE tpl` (le template ne doit avoir **aucune connexion ouverte**, d'où `db.destroy()` avant) ; `SHOW server_version` ~ `^18\.7` ; `SELECT uuidv7()` renvoie un UUID ; `SET ROLE prosperity_app` puis `CREATE TABLE prosperity.x` **et** `public.x` → erreur SQLSTATE `42501`. Les rôles sont **globaux au cluster** (non copiés par `TEMPLATE`, mais présents). Le rôle est créé `NOLOGIN` en migration ; le mot de passe/`LOGIN` est posé hors git au provisioning (OPS). Prévoir un `globalSetup` Vitest qui démarre **un** conteneur, crée/migre le template et `provide()` l'URI ; chaque fichier de test crée sa base `TEMPLATE`. Digest d'image à pinner (Renovate/PR labellisée).

### Règles Semgrep du projet (exécuté : 7 détections sur 7, aucun faux positif sur le fichier conforme)
```yaml
rules:
  - id: prosperity.tool-handler-without-principal
    languages: [typescript]
    severity: ERROR
    message: "Un handler d'outil MCP doit recevoir un Principal en premier parametre (defineTool)."
    paths: { include: ["src/mcp/tools/**"] }
    patterns:
      - pattern-either:
          - pattern: "defineTool($NAME, $CFG, async ($ARG: $T) => { ... })"
          - pattern: "defineTool($NAME, $CFG, async ($ARG) => { ... })"
          - pattern: "defineTool($NAME, $CFG, async () => { ... })"
      - pattern-not: "defineTool($NAME, $CFG, async ($P: Principal, ...) => { ... })"
  - id: prosperity.raw-registertool      # registerTool direct interdit hors define-tool.ts
    languages: [typescript]
    severity: ERROR
    message: "registerTool direct interdit, passer par defineTool"
    paths: { include: ["src/**"], exclude: ["src/mcp/define-tool.ts"] }
    pattern: "$S.registerTool(...)"
  - id: prosperity.sql-concatenation
    languages: [typescript]
    severity: ERROR
    message: "SQL construit par concatenation ou interpolation"
    pattern-either:
      - pattern: "sql.raw($A + ...)"
      - pattern: "sql.raw(`...${$X}...`)"
      - pattern: "$DB.query($A + ...)"
      - pattern: "$DB.query(`...${$X}...`)"
  - id: prosperity.insecure-random-token
    languages: [typescript]
    severity: ERROR
    message: "Math.random interdit pour un jeton ou secret"
    pattern: "Math.random()"
  - id: prosperity.non-constant-time-secret-compare
    languages: [typescript]
    severity: ERROR
    message: "Comparaison non constante d'un secret : utiliser timingSafeEqual"
    pattern-either:
      - pattern: "$A.token === $B"
      - pattern: "$A.secret === $B"
      - pattern: "$A.signature === $B"
```
**Piège YAML :** les patterns contenant `: ` (annotation de type) doivent être entre guillemets (échec « mapping values are not allowed here » vérifié). La convention `defineTool` (fabrique du projet, premier paramètre `Principal`) est **à créer en phase 2** ; en phase 1 la règle est prouvée par le patch d'auto-test qui ajoute `src/mcp/tools/bad.ts` (Semgrep est syntaxique, `Principal` n'a pas besoin d'exister). Les packs registre (`p/typescript`, `p/nodejs`, `p/jwt`, `p/owasp-top-ten`) se chargent sans compte avec `--metrics=off` [VERIFIED: exécution], mais leur contenu **dérive dans le temps** : voir Q4.

### `lefthook.yml` (syntaxe `jobs`, `glob`, `stage_fixed` et blocage par variable exécutés ; les jobs `mise exec` supposent `mise` sur le PATH)
```yaml
min_version: 2.2.2
output: [failure, summary]
pre-commit:
  parallel: false
  jobs:
    - name: gitleaks-staged
      run: mise exec -- gitleaks git --staged --redact --no-banner
    - name: protected-paths
      run: mise exec -- node quality/agent-guard/precommit-protected.ts   # refuse sans autorisation humaine
    - name: format
      glob: "*.ts"
      run: mise exec -- pnpm exec biome format --write {staged_files}
      stage_fixed: true
pre-push:
  jobs:
    - name: quality-push
      run: mise exec -- pnpm quality --profile push
```
`mise` doit être sur le `PATH` des hooks git (client graphique : attention). Le script de hook généré embarque le chemin absolu du binaire lefthook installé par mise.

### Workflow `quality.yml` (squelette ; SHA vérifiés)
```yaml
name: quality
on:
  pull_request:
    types: [opened, synchronize, reopened, labeled, unlabeled]
permissions: {}
jobs:
  quality:
    name: quality                      # nom exact du check requis ; aucun filtre `paths`
    runs-on: ubuntu-24.04              # image explicite (ubuntu-latest = 24.04 aujourd'hui)
    permissions: { contents: read, pull-requests: read, actions: read }
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with: { fetch-depth: 0, persist-credentials: false }
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1  (ref de base → ../base)
        with: { ref: "${{ github.base_ref }}", path: base, persist-credentials: false }
      - uses: jdx/mise-action@90f833d396d0cc3674b631d2d225e306476c303a # v5.2.10
        with: { version: 2026.11.12, github_token: "${{ secrets.GITHUB_TOKEN }}" }
      - run: pnpm install --frozen-lockfile
      - run: pnpm quality
      - uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        if: always()
        with: { name: gate, path: reports/gate.json }
```
SHA : checkout v7.0.1 `3d3c42e5…`, upload-artifact v7.0.2 `cf430e03…`, cache v6.1.0 `55cc8345863c7cc4c66a329aec7e433d2d1c52a9` (inutile : mise-action met en cache) [VERIFIED: `gh api repos/<r>/git/ref/tags/<tag>`, type `commit`]. `actions/github-script` v9.0.0 est un tag **annoté** (type `tag`, SHA à déréférencer) : l'éviter, utiliser `gh api` depuis les scripts (`gh` préinstallé sur les runners hébergés [ASSUMED]). Ne jamais interpoler `${{ github.event.* }}` dans un `run:` (zizmor `template-injection`, vérifié). `zizmor` sans `--offline` en CI (audits en ligne nécessitent `GH_TOKEN`).

### Rapport `gate.json` (conception, schéma fixé + champs additifs)
```json
{ "profile": "full", "commit": "<sha>", "base": "<sha>", "generated_at": "2026-11-21T14:00:00Z",
  "checks": [
    { "check": "lint", "tool": "eslint", "version": "10.15.0", "severity": "blocking",
      "passed": false, "status": "failed", "issues": [{ "rule": "no-restricted-syntax", "file": "src/x.ts", "line": 4 }] },
    { "check": "mutation", "tool": "stryker", "version": "10.1.1", "severity": "blocking",
      "passed": false, "status": "skipped", "skipped_reason": "ci-only", "issues": [] } ] }
```
Le profil `full` interprète tout `skipped` bloquant comme un échec ; le profil `push` l'accepte seulement avec `skipped_reason: "ci-only"`.

### Règles `.claude/settings.json` (syntaxe vérifiée dans la doc ; liste à compléter)
```json
{
  "permissions": {
    "deny": [
      "Edit(/quality/**)", "Edit(/semgrep/**)", "Edit(/.github/**)", "Edit(/deploy/**)",
      "Edit(/.claude/settings*.json)", "Edit(/.claude/CLAUDE.md)", "Edit(/CLAUDE.md)", "Edit(/AGENTS.md)",
      "Edit(/mise.toml)", "Edit(/mise.lock)", "Edit(/.mise/locks/**)", "Edit(/pnpm-workspace.yaml)", "Edit(/pnpm-lock.yaml)",
      "Edit(/package.json)", "Edit(/lefthook.yml)", "Edit(/Containerfile)",
      "Edit(**/eslint.config.*)", "Edit(**/tsconfig*.json)", "Edit(**/vitest.config.*)", "Edit(**/stryker.config.*)",
      "Edit(/.dependency-cruiser.*)", "Edit(/knip.json)", "Edit(/.jscpd.json)", "Edit(/.gitleaks.toml)", "Edit(**/CODEOWNERS)",
      "Bash(git commit*--no-verify*)", "Bash(git push*--force*)", "Bash(git push*-f *)",
      "Bash(gh pr edit*)", "Bash(gh issue edit*)", "Bash(gh label*)", "Bash(gh api*labels*)", "Bash(gh api*rulesets*)",
      "Bash(gh auth token*)"
    ]
  },
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash",
        "hooks": [{ "type": "command",
                    "command": "node \"$CLAUDE_PROJECT_DIR\"/quality/agent-guard/bash-guard.ts", "timeout": 10 }] }
    ]
  }
}
```
Le hook lit le JSON sur stdin (`tool_input.command`), et bloque par **exit 2 + message stderr** ou par `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"…"}}` [CITED: code.claude.com/docs/en/hooks]. Une décision de hook ne contourne **pas** les règles deny. Un hook mal rédigé qui plante ne doit pas bloquer silencieusement tout Bash : il retourne 0 (« pas de décision ») sur erreur d'analyse et laisse la CI juger. `package.json` entier en deny empêche l'agent d'éditer les scripts/dépendances ; `pnpm add` passe par Bash, d'où le hook, le pré-commit et `deps-guard`.

### Ruleset de `main` (corps de requête, à exécuter par l'humain)
Modèle tiré du ruleset existant (`GET` vérifié) ; remplacer `ci-required` par `quality` :
```json
{ "name": "Main", "target": "branch", "enforcement": "active", "bypass_actors": [],
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "rules": [
    { "type": "deletion" }, { "type": "non_fast_forward" },
    { "type": "required_status_checks",
      "parameters": { "required_status_checks": [{ "context": "quality", "integration_id": 15368 }],
                      "strict_required_status_checks_policy": true, "do_not_enforce_on_create": false } },
    { "type": "pull_request", "parameters": { "required_approving_review_count": 0 } } ] }
```
La règle `pull_request` et ses paramètres exacts sont **[ASSUMED]** (non rejouée) : valider contre `PUT /repos/{o}/{r}/rulesets/{id}` au plan de verrou. Durcissements complémentaires disponibles (réglages repo lus en `GET`, valeurs actuelles) : `actions/permissions` → `sha_pinning_required` (actuellement `false`) à passer à `true` ; `actions/permissions/fork-pr-contributor-approval` → `approval_policy` actuellement `first_time_contributors`, passer à `all_external_contributors` ; `default_workflow_permissions` déjà `read`.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `kysely` : `import { Migrator } from 'kysely'` | `import { Migrator } from 'kysely/migration'` | Kysely 0.29 | Les exemples antérieurs échouent à l'exécution |
| `onlyBuiltDependencies`/`neverBuiltDependencies` | `allowBuilds` (map) | pnpm 11 | Anciennes clés supprimées |
| `.npmrc` pour la politique pnpm | `pnpm-workspace.yaml` | pnpm 11/12 | Seuls auth/registry/TLS/proxy restent dans `.npmrc` |
| Vitest `workspace` | `test.projects` | Vitest ≥ 3.2 | Vérifié sur 5.1 |
| `gitleaks protect --staged` | `gitleaks git --staged` | gitleaks 8.19+ | `--pre-commit`/`--staged` sur la sous-commande `git` (vérifié 8.30.1) |
| Compteur d'échappatoires par `grep` | ESLint + compteur à cliquet | — | Voir Pitfall 11 |
| TS exécuté via `tsx`/`ts-node` | `node fichier.ts` (type stripping) | Node ≥ 23.6/24 ; vérifié 26.13 | Scripts de gate sans transpileur ; `erasableSyntaxOnly` |

**Deprecated/outdated:** `eslint-plugin-vitest` (plafonné ESLint ≤ 9) → `@vitest/eslint-plugin` ; Trivy non épinglé (incident de mars 2026) → osv-scanner ; GitHub Action par tag mobile → SHA complet.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `disableBail: true` atténue les faux survivants de l'issue #6335 | Pitfall 4 | Le gate mutation reste aléatoire ; prévoir la relance des survivants |
| A2 | Paramètres exacts de la règle `pull_request` d'un ruleset (`required_approving_review_count`, etc.) et charge `PUT` | Code Examples (ruleset) | Requête rejetée à l'exécution ; rattrapable (action humaine) |
| A3 | `sha_pinning_required` s'active via `PUT /repos/{o}/{r}/actions/permissions` (champ vu en `GET`) | Code Examples (ruleset) | Réglage à faire à la main dans l'UI |
| A4 | `gh` est préinstallé et utilisable avec `GH_TOKEN` sur `ubuntu-24.04` | Code Examples (workflow) | Installer via mise (`gh`) |
| A5 | `package.json` `packageManager: "pnpm@12.21.0"` cohabite sans conflit avec le pnpm de mise (non testé : l'essai a été interrompu) | Standard Stack | Divergence de version pnpm ; ajouter un test de cohérence |
| A6 | Un `quality` renvoyé par le job nommé exactement `quality` satisfait le contexte requis (nom de job = contexte) | Pitfall 10 | Check en attente éternelle ; tester sur la PR de démonstration |
| A7 | Les packs registre Semgrep dérivent dans le temps (pas de versionnage de pack) | Q4 | Si stables, les garder en blocking tels quels |
| A8 | `mise` reste sur le `PATH` des hooks git du poste (client en ligne de commande) | lefthook | Hooks en 127 ; documenter `PATH` ou chemin absolu |
| A9 | Le seuil `max_severity >= 7.0` correspond à « high/critical » pour osv-scanner | Pitfall 3 | Seuil trop laxiste/strict ; ajustable dans le runner |
| A10 | Le mode « Required workflows » d'organisation n'est pas disponible (compte utilisateur) | Pattern 2 | Sans objet depuis la révision : le juge hors PR (`workflow_run` + application dédiée) ferme ce trou sans organisation |

## Open Questions (RESOLVED)

Chaque question porte le défaut retenu par les plans, la tâche qui l'applique et, quand un humain doit le confirmer, le point de contrôle qui le confirme (les checkpoints restent des confirmations d'un défaut déjà planifié, pas des questions ouvertes).

1. **Q1 : pins de CLAUDE.md vs `minimumReleaseAge`** — RESOLVED : option (a), pins de repli de « Standard Stack » pour toute version publiée depuis moins de 7 jours à la date d'exécution, montée vers les pins cibles par PR labellisée `deps-approved` ; aucune exclusion d'âge. La table de CLAUDE.md §3/§4 est la cible, pas le premier état. Appliqué : plan 01-02 tâche 1 (table des versions retenues), confirmé par l'humain au même checkpoint `blocking-human` (réponse `wait` possible jusqu'au 2026-11-27).
2. **Q2 : mitigation de #6335** — RESOLVED : `disableBail: true` par défaut ; si les 10 exécutions avec `disableBail` ne sont pas stables, une relance unique limitée aux survivants avant de conclure ; seuil `break` jamais baissé. Appliqué et mesuré : plan 01-03 tâche 3 (20 exécutions consignées).
3. **Q3 : ruleset `ci-required` → `quality`** — RESOLVED (révisé) : bascule humaine en deux temps au verrou, après le premier vert. Ruleset transitoire `gate` (GitHub Actions, 15368) pour fusionner la seule PR de bootstrap, protégée par la relecture D-01 ; puis ruleset final : unique check requis `quality`, statut publié par le juge hors PR (workflow `quality-verdict`, application dédiée) avec cette application comme source. Appliqué : plan 01-13 tâche 3, étapes 5 et 7 ; mécanisme du juge : plan 01-07 tâche 3.
4. **Q4 : Semgrep « déterministe »** — RESOLVED : défaut `packs-advisory` (règles du projet `semgrep/` bloquantes, packs du registre joués en advisory en profil full et au nightly). Appliqué : plan 01-04 tâches 1 et 3 ; confirmé par l'humain au checkpoint de décision du plan 01-04 tâche 1 (écart à CLAUDE.md §10.2, décision réversible).
5. **Q5 : layout `src/`** — RESOLVED : défaut A (globs `src/shared/**`, `src/modules/*/{domain,application}/**`) dans le fichier unique `quality/layout.json`. Appliqué : plan 01-02 tâche 3 ; confirmé au point de relecture D-01, plan 01-13 tâche 1.
6. **Q6 : knip en mode `--production`** — RESOLVED : non activé en phase 1 (les exports du canari ne sont utilisés que par des tests) ; introduit en phase 2 avec `src/index.ts`. Appliqué : plan 01-08 tâche 2 ; consigné comme décision réversible dans `docs/quality-gate.md` (plan 01-12 tâche 2).
7. **Q7 : jeton de l'agent** — RESOLVED : aucun second compte ni jeton en phase 1 (idée différée de CONTEXT.md). La limite est documentée (`docs/quality-gate.md`, « Limites connues », plan 01-12 tâche 2) et réduite par les règles deny et le garde Bash sur labels, fusion, réglages et API en écriture (plans 01-06 tâche 3 et 01-13 tâche 2), l'auto-fusion désactivée et le juge hors PR (plan 01-07 tâche 3) ; le résiduel est porté au registre de menaces (T-01-49).
8. **Q8 : `.claude/CLAUDE.md` et GSD** — RESOLVED : défaut `approve`, D-05 appliqué tel quel (protégé par le deny, le garde, le pré-commit et l'intégrité) ; variante `approve-claude-md-ci-only` disponible. Appliqué : plan 01-06 tâche 2 (liste) et plan 01-13 tâche 2 (`agentExempt`) ; confirmé au point de relecture D-01, plan 01-13 tâche 1.
9. **Q9 : hadolint sans Containerfile** — RESOLVED : `passed` avec la note « non applicable : aucun Containerfile suivi », jamais `skipped`. Appliqué : plan 01-04 tâche 2 ; consigné dans `docs/quality-gate.md` (plan 01-12).
10. **Q10 : Renovate** — RESOLVED : différé, hors QUAL-01..09 ; les montées de version passent par des PR labellisées et l'auto-test les juge (D-08). Hors périmètre de la phase 1 (SKELETON « Out of Scope »).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | tout | ✓ | v26.13.0 | — (égal au pin mise) |
| pnpm | install, scripts | ✓ (shim corepack qui télécharge 12.21.0 à la demande) | 12.21.0 (cible) | pnpm fourni par mise |
| mise | D-11 | ✗ | — (binaire 2026.11.12 téléchargé et testé en bac à sable) | installer (binaire unique) ; l'action en CI |
| lefthook | hooks | ✗ | — | via mise |
| gitleaks, semgrep, actionlint, zizmor, hadolint, trufflehog | checks | ✗ | — | via mise (installés et exécutés en bac à sable) |
| osv-scanner | CVE | ✓ | 2.7.1 (= pin) | — |
| uv | semgrep via mise | ✓ (0.12.1 local) | 0.12.1 < 0.12.10 requis pour verrouiller le graphe | épingler `uv = "0.13.9"` dans `mise.toml` |
| Docker | Testcontainers | ✓ | 29.6.2 (Podman ✗) | Podman rootless non requis en phase 1 |
| gh | approbation, ruleset | ✓ | 2.96.0, connecté `sebc-dev` | — |
| git | tout | ✓ | 2.53.0 | — |
| jq | scripts d'inspection | ✓ | 1.8.1 | — |
| Réseau (npm, GitHub, registry Semgrep, deps.dev/osv.dev) | installs, osv, semgrep packs | ✓ | — | osv-scanner `--offline` avec base téléchargée |

**Missing dependencies with no fallback:** aucune.
**Missing dependencies with fallback:** mise, lefthook et les 6 binaires de gate (installables par `mise install`, validé) ; uv ≥ 0.12.10 (à épingler).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Vitest 5.1.x (projets `unit` + `integration`), fast-check 4.10.x, StrykerJS 10.1.1 |
| Config file | `vitest.config.ts`, `stryker.config.json` (à créer, Wave 0) |
| Quick run command | `pnpm quality --profile push` (≤ 60 s) ; `pnpm vitest run --project unit` |
| Full suite command | `pnpm quality` (profil `full`) ; `pnpm quality --only selftest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| QUAL-01 | Même runner/versions en push et en CI ; `gate.json` écrit ; `skipped` jamais silencieux | unit + e2e | `pnpm vitest run quality/run.test.ts` ; PR réelle (D-07b) | ❌ Wave 0 |
| QUAL-02 | Cas `as`, `any`, complexité, `!`, `parseFloat`, directive inutile rejetés | selftest | `pnpm quality --only selftest --case lint-*` | ❌ Wave 0 |
| QUAL-03 | Cas outil MCP → `adapters/db`, cycle, export mort, bloc dupliqué | selftest | `… --case arch-*,deadcode-*,dup-*` | ❌ Wave 0 |
| QUAL-04 | Cas secret, SQL concaténé, handler sans `Principal`, action non épinglée, CVE≥7 | selftest | `… --case sec-*` | ❌ Wave 0 |
| QUAL-05 | Canari : couverture 100 %, Stryker ≥ 80, propriétés fast-check ; cas test faible (mutation + couverture) | unit + selftest | `pnpm vitest run --project unit --coverage` ; `pnpm stryker run` | ❌ Wave 0 |
| QUAL-06 | Cas hausse du compteur, seuil baissé, assertion retirée, chemin protégé modifié | selftest | `… --case integrity-*` | ❌ Wave 0 |
| QUAL-07 | Édition d'un fichier de gate par l'agent refusée (deny + hook) ; ruleset `quality` | manuel guidé + e2e | tentative d'édition dans une session agent ; `gh api …/rulesets` en lecture | ❌ Wave 0 |
| QUAL-08 | PG 18.x réel, `uuidv7()`, rôle app sans DDL, ordre aléatoire, seed loguée, méta-test RLS (à vide) + cas « table sans RLS » | integration + selftest | `pnpm vitest run --project integration` | ❌ Wave 0 |
| QUAL-09 | Dépendance sans `deps-approved` ou trop récente rejetée | selftest + PR réelle | `… --case deps-*` ; PR manuelle | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pnpm quality --profile push`
- **Per wave merge:** `pnpm quality` + `pnpm quality --only selftest`
- **Phase gate:** gate complète verte en CI sur une vraie PR, passage manuel D-07b (4-5 PR), vérificateur de phase lit QUAL-01 selon D-12.

### Wave 0 Gaps
- [ ] `quality/` (runner, registre, rapport, intégrité, approbations, deps-guard, compteur) et `quality/selftest/` (cas + runner worktree)
- [ ] `vitest.config.ts`, `stryker.config.json`, `eslint.config.mjs`, `tsconfig.json`, `.dependency-cruiser.cjs`, `knip.json`, `.jscpd.json`, `.gitleaks.toml`, `biome.json`, `lefthook.yml`
- [ ] `test/` : `globalSetup` Testcontainers, méta-tests (RLS `owner_member_id`, rôle app sans DDL)
- [ ] `src/shared/money/` + tests (exemples + propriétés), `src/db/` (fournisseur SQL, runner), `db/migrations/0001_foundation.sql`
- [ ] Installation du framework : `mise install` puis `pnpm install --frozen-lockfile` (voir pins de repli)
- [ ] Mesure de stabilité Stryker (Q2) : 20 exécutions du canari

## Security Domain

`security_enforcement` actif (config.json : `security_asvs_level: 1`, `security_block_on: high`). La phase n'expose aucun service : les catégories applicables sont la chaîne d'approvisionnement, la configuration CI et le contrôle d'accès à la gate.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | (phase 2) |
| V3 Session Management | no | (phase 2) |
| V4 Access Control | yes (accès aux chemins protégés et aux labels) | deny Claude Code + hook + allowlist d'acteur + ruleset sans bypass |
| V5 Input Validation | yes (parse de montants ; entrées de workflow) | parseur `bigint` maison testé fast-check ; aucune interpolation `${{ }}` dans `run:` (zizmor) |
| V6 Cryptography | partiel (pas de crypto ; interdiction de `Math.random`, comparaison non constante) | règles Semgrep ; `crypto.timingSafeEqual`/`randomBytes` à venir |
| V10 Malicious code / supply chain | yes | pnpm `minimumReleaseAge`, `trustPolicy`, `blockExoticSubdeps`, `allowBuilds` ; `mise.lock` (checksums, attestations) ; actions par SHA ; osv-scanner |
| V14 Configuration | yes | permissions de workflow minimales, `persist-credentials: false`, runners hébergés, `pull_request` seul |

### Known Threat Patterns for ce stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Injection de commande via contexte de workflow (`${{ github.event.pull_request.title }}`) | Tampering/EoP | zizmor `template-injection` (vérifié) ; variables d'environnement intermédiaires |
| Usurpation d'approbation (label posé par bot ou par l'agent) | Spoofing/EoP | allowlist d'acteur + horodatage serveur ; deny `gh`; limite documentée (jeton partagé) |
| Date de commit antidatée pour contourner « label après dernier commit » | Tampering | ancre = `created_at` des runs Actions pour le SHA |
| PR qui réécrit baseline, scripts d'intégrité ou liste des chemins | Tampering | exécution depuis la ref de base ; fusion humaine unique |
| Secrets exposés aux PR de fork | Info disclosure | `pull_request` (pas de secrets, jeton en lecture seule) ; approbation des contributeurs externes |
| Dépendance malveillante/typosquattée ajoutée par un agent | Tampering | âge minimal, existence/âge npm, label `deps-approved`, `allowBuilds` explicite |
| Binaire d'outil compromis (cf. incident Trivy) | Tampering | `mise.lock` avec checksum + attestation ; versions épinglées ; osv-scanner |
| Désarmement local de la gate (`LEFTHOOK=0`, `disableAllHooks`, `--no-verify`) | Repudiation/EoP | deny + hook ; CI = seul juge |
| Faux secret littéral dans un patch d'auto-test | Info disclosure (faux positif) | secret généré à l'application |

## Project Constraints (from CLAUDE.md)

Directives de `.claude/CLAUDE.md` à respecter (source projet, tag `[CITED: .claude/CLAUDE.md]`) :
- **Interface** : aucune UI propre ; hors périmètre de la phase (aucun outil MCP en phase 1).
- **Stack figée** : Node 26.13.x, TypeScript **6.0.3 épinglé exact**, pnpm 12.21.0, Vitest 5.1.1, fast-check 4.10.3, Stryker 10.1.1, ESLint 10.15.0 + typescript-eslint 8.73.0, Biome 2.6.8 **formateur seul**, dependency-cruiser 18.8.0, knip 6.47.0, jscpd 5.4.3, lefthook 2.2.2, Kysely 0.29.9, `pg` 8.23.1, Testcontainers 12.2.2, PostgreSQL **18.7** image épinglée par digest. (Voir Q1 : l'ordre d'installation passe par des pins de repli.)
- **Montants** : `bigint` de centimes, jamais `parseFloat`/`Number()`, aucune lib décimale ; répartition au plus grand reste, Σ parts = total testée par fast-check ; dates `Temporal.PlainDate` ; horloge injectée (`Date`/`Date.now` hors `Clock` interdits).
- **Gate** : tableau §10.2 (sévérités, seuils), `pnpm quality` unique, CI juge, **pas de path-scoping**, un seul check requis `quality` ; pré-commit ≤ 10 s, pré-push ≤ 60 s, CI ≤ 8-10 min ; seuils Stryker `break` 80, couverture domaine 100 %, global 85/80 avec cliquet ; compteur d'échappatoires à cliquet (budget initial 0) ; `--max-warnings 0` ; `reportUnusedDisableDirectives` ; dérogations avec description obligatoire.
- **Anti-patterns** : Trivy non épinglé, TypeScript 7.x, PGlite, Redis/Caddy, DCR ouvert, agent qui édite sa gate.
- **GSD** : modifications de fichiers via une commande GSD (`/gsd-execute-phase`, etc.).
- **Écart signalé** : `--since origin/main` (§10.2, Stryker) n'existe pas dans StrykerJS 10.1.1 (voir Pitfall 5).

## Sources

### Primary (HIGH confidence)
- Exécutions dans un bac à sable (Node 26.13.0, pnpm 12.21.0, mise 2026.11.12, Docker 29.6.2) : installation et exécution de tsc/ESLint/dependency-cruiser/knip/jscpd/Vitest/Stryker/Testcontainers/gitleaks/Semgrep/zizmor/osv-scanner/lefthook aux versions épinglées ; `pnpm install` avec `minimumReleaseAge` ; `mise install`/`lock`.
- Registre npm (`npm view <pkg> time --json`, 2026-11-21) ; seam `package-legitimacy check`.
- GitHub API (`gh api`) : `repos/sebc-dev/prosperity` (public, branche `main`), `rulesets/17645569`, `actions/permissions` (+ `workflow`, `fork-pr-contributor-approval`), `issues/{n}/events` et `actions/runs?head_sha=` sur une PR publique, SHA de tags d'actions et de `jdx/mise-action`.
- pnpm : `pnpm.io/supply-chain-security`, `/settings`, `/settings/dependency-resolution`, `/settings/build`.
- Claude Code : `code.claude.com/docs/en/permissions` (syntaxe Edit/Bash, redirections, précédence deny, limites des règles Bash), `/hooks` (PreToolUse stdin/stdout, exit 2, fusion multi-fichiers, `disableAllHooks`).
- GitHub Docs : `events-that-trigger-workflows` (jeton en lecture seule pour les forks, types d'activité), `secure-use`.
- mise : `mise.jdx.dev/dev-tools/mise-lock.html` ; `jdx/mise-action` README (entrées, `--locked`).
- `stryker run --help` (10.1.1) ; issues Stryker #6004, #6272, #6335 (`gh api`).
- Fichiers du dépôt lus : `01-CONTEXT.md`, `REQUIREMENTS.md`, `STATE.md`, `SUMMARY.md`, `ARCHITECTURE.md` (§ structure, graphe), `.planning/config.json`, `.claude/settings.local.json`.

### Secondary (MEDIUM confidence)
- `.claude/CLAUDE.md` §3, §4, §10, §11 (cité, non rouvert) et `PITFALLS.md` (C16) ; recoupés par exécution quand possible.

### Tertiary (LOW confidence)
- Paramètres du ruleset `pull_request`, charge `PUT actions/permissions`, présence de `gh` sur les runners, cohabitation `packageManager`/mise : marqués `[ASSUMED]` (voir Assumptions Log).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH : chaque outil installé et exécuté ; écarts de pins mesurés.
- Architecture (runner, profils, rapport, auto-test, approbation) : MEDIUM : API et formats de sortie vérifiés, mais le code de colle (runner, hook, `approvals.ts`) n'existe pas encore.
- Pitfalls: HIGH pour ceux reproduits (pins/âge, plugins Stryker, exit codes, `Migrator`, `LEFTHOOK=0`) ; MEDIUM pour #6335 (issue ouverte, mitigation non prouvée).
- GitHub/Claude Code (ruleset, permissions, hooks) : MEDIUM-HIGH : docs officielles + `GET` réels ; écritures (`PUT` ruleset) non rejouées.

**Research date:** 2026-11-21
**Valid until:** 2026-11-28 (outillage à versions fraîches : la table de maturité et l'état des issues Stryker changent en quelques jours)
