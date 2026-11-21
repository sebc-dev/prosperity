# Walking Skeleton — Prosperity (connecteur Claude)

**Phase:** 1
**Generated:** 2026-11-21

## Capability Proven End-to-End

Un `git push` déclenche, sur le poste puis sur un runner GitHub hébergé, la même commande `pnpm quality` : elle exécute un check réel (actionlint sur le workflow CI lui-même), vérifie la version de l'outil contre `mise.toml`, écrit `reports/gate.json`, et la PR brouillon de bootstrap affiche le check `quality` en vert.

Dans cette phase il n'y a ni UI, ni outil MCP, ni OAuth : le « produit » de la phase 1 est la gate elle-même. Le squelette est donc la gate la plus mince possible, câblée de bout en bout (outil épinglé → runner → rapport → hook pré-push → CI).

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Runtime et outillage | Node 26.13.0, pnpm 12.21.0 et tous les binaires hors npm (gitleaks, semgrep, osv-scanner, actionlint, zizmor, hadolint, trufflehog, lefthook, uv) épinglés dans `mise.toml` + `mise.lock` (checksums, provenance) ; `jdx/mise-action` épinglée par SHA en CI | D-11 : mêmes versions au poste et en CI ; dépôt public, gitleaks doit arrêter un secret en pré-commit dans la même version qu'en CI |
| Point d'entrée de la gate | `pnpm quality` = `node quality/run.ts` (TypeScript exécuté nativement par Node 26, sans `tsx`) ; checks découverts dans `quality/checks/*.ts` (un fichier par check, pas de registre central) ; profils `full` (CI) et `push` (pré-push, ≤ 60 s) | QUAL-01, D-12 : une seule commande, la CI juge ; un fichier par check évite les conflits entre plans parallèles |
| Contrat du rapport | `reports/gate.json` = `{profile, commit, base, generated_at, verdict, checks[]}`, chaque check `{check, tool, version, severity, passed, status, skipped_reason?, note?, issues[], duration_ms}` ; écriture atomique (fichier temporaire + rename) | Schéma `{check, tool, version, severity, passed, issues[]}` fixé par CLAUDE.md §10, champs additifs pour D-12 (`skipped: ci-only` jamais silencieux) |
| Verdict | Profil `full` en CI : tout check bloquant `failed` ou `skipped` = échec. Profil `push` : `skipped` accepté seulement avec `skipped_reason: "ci-only"`. Verdict lu dans la sortie structurée de l'outil, jamais dans son seul code de sortie | D-12 ; RESEARCH Pitfall 3 (depcruise rend 0 en JSON, osv-scanner n'a pas de seuil) |
| CI | GitHub Actions, runner hébergé `ubuntu-24.04`, déclencheur `pull_request` pour la gate (jamais `pull_request_target`), sans filtre `paths`, permissions minimales, `persist-credentials: false`, actions épinglées par SHA complet. Jusqu'au verrou, le job de la PR s'appelle `quality` ; au verrou (plan 01-13), il devient `gate` (non requis) et le seul check requis est le statut `quality` publié par le juge hors PR | D-13 ; RESEARCH Pitfall 10 (check requis jamais rapporté) |
| Scripts de confiance | En CI, `approvals`, `integrity` et `deps` sont exécutés depuis une copie de la **ref de base** avec `--base-dir` explicite (l'allowlist n'est lue que là), jamais depuis la PR ; mode « amorçage » quand la base ne les contient pas encore. Le juge qui fait foi est hors PR : workflow `quality-verdict` (déclencheur `workflow_run`, définition lue sur la branche par défaut), qui rejoue ces juges depuis `main` sur la tête lue comme données et publie le statut `quality` avec le jeton d'une application GitHub dédiée (clé dans l'environnement `gate-verdict` restreint à `main`) | RESEARCH Pattern 2 et sa note de révision : une PR ne se juge pas avec son propre code, ni avec son propre workflow |
| Données | PostgreSQL 18.7 (image épinglée par digest) via Testcontainers en test ; migrations Kysely `Migrator` (import depuis `kysely/migration`) en SQL brut forward-only, jouées sous le rôle `prosperity_migrator` (provisionné hors migration, propriétaire de la base et du schéma, sans SUPERUSER ni BYPASSRLS) ; rôle applicatif `prosperity_app` sans aucun DDL | D-10 ; CLAUDE.md §3.4 ; aucune table métier en phase 1 |
| Auth | Aucune en phase 1 (phase 2 : `oidc-provider` embarqué). Côté gate : « approbation humaine » = label posé par `sebc-dev` après le dernier push, vérifié par le juge hors PR ; fusion réservée à l'humain (deny de l'agent, auto-fusion désactivée) | D-02, D-03 |
| Cible de « déploiement » | Aucun déploiement en phase 1 : la cible est la CI GitHub (check requis `quality` sur `main`). L'historique de `sebc-dev/jiaolong` est sans ancêtre commun avec `main` : il est rattaché par une décision explicite (plan 01-01) avant la première PR | GitHub refuse une PR entre historiques disjoints |
| Directory layout | ARCHITECTURE.md : `src/shared/**` (pur), `src/modules/<m>/{domain,application,adapters/{db,http,aggregator},public.ts}`, `src/mcp/**`, `src/db/**` (infra), `db/migrations/*.sql`, `test/**` (intégration), `quality/**` (gate), `semgrep/**`. Les globs de couche vivent dans **un seul fichier** `quality/layout.json`, lu par ESLint, Vitest, Stryker et dependency-cruiser | Q5 (RESEARCH) : défaut A appliqué ; le fichier unique rend la décision réversible à faible coût tant qu'aucun module n'existe ; confirmation humaine au point de relecture D-01 (plan 01-13) |
| Seuils | Un seul fichier `quality/thresholds.json` (lint, complexité, couverture, mutation, supply-chain) lu par les configs ; le sens « plus strict » de chaque seuil est codé dans `quality/integrity.ts`, exécuté depuis la base | CLAUDE.md §10.2 (seuils à cliquet) ; une PR ne peut pas changer à la fois le seuil et sa règle de comparaison |

## Stack Touched in Phase 1

- [x] Project scaffold : `mise.toml`, `package.json`, `pnpm-workspace.yaml` (politique supply-chain), `tsconfig.json`, ESLint, Biome (formateur seul), Vitest, Stryker
- [ ] Routing : non applicable (aucun serveur HTTP en phase 1 ; `/mcp` arrive en phase 2)
- [x] Database : une migration réelle (`db/migrations/0001_foundation.sql`) appliquée sur un PostgreSQL 18 réel, lue (`server_version`, `uuidv7()`) et écrite (DDL refusé au rôle app) par les tests d'intégration
- [ ] UI : non applicable (Claude est l'unique client ; aucune UI propre)
- [x] Deployment : la CI GitHub exécute `pnpm quality` sur la PR brouillon de bootstrap dès le plan 01-01 ; commande locale complète : `mise exec -- pnpm quality`

## Out of Scope (Deferred to Later Slices)

- Serveur MCP, `/mcp`, OAuth, passkeys, tunnel, Containerfile (phase 2) : le check `container` (hadolint) rend `passed` avec la note « non applicable » tant qu'aucun Containerfile n'existe
- Snapshot `tools/list`, e2e OAuth, conformance MCP (phase 2)
- Tables métier, RLS réelle, `kysely-codegen`, snapshot `pg_dump --schema-only` (phase 3)
- Test de restauration de sauvegarde (phase 3, OPS-02)
- `knip --production` (quand `src/index.ts` existe, phase 2)
- Renovate (Q10, hors QUAL-01..09)
- SBOM `syft` et scan d'image (aucune image publiée en phase 1)
- Commit d'approbation signé, jeton agent distinct, runner auto-hébergé (idées différées de CONTEXT.md)

## Subsequent Slice Plan

Chaque phase ajoute une tranche verticale sans changer ces décisions ; tout nouveau dossier de module entre dans `quality/layout.json` et `.dependency-cruiser.cjs` dans le même diff :

- Phase 2 : connecteur Claude et identité du foyer (serveur MCP, AS embarqué, `whoami`)
- Phase 3 : comptes cloisonnés et catégories (premières tables, RLS réelle, méta-tests mordants)
- Phase 4 : saisie conversationnelle et soldes (consomme `src/shared/money`)
- Phases 5 à 9 : politique d'écriture, budgets, dettes, import, DSP2
