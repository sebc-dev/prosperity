# Project Research Summary

**Projet :** Prosperity, connecteur Claude (finances partagées d'un foyer)
**Domaine :** serveur MCP distant (Streamable HTTP + OAuth) portant le domaine finances d'un foyer, auto-hébergé derrière un tunnel, consommé comme connecteur custom claude.ai, avec artefacts `mcp` comme interface
**Recherche :** 2026-11-21
**Confiance globale :** MEDIUM-HIGH (protocole, SDK et contraintes claude.ai vérifiés dans les docs officielles ; DSP2, MCP Apps en production et tooling TypeScript 7 restent à valider par spike)

## Executive Summary

Prosperity est un backend de finances de foyer dont la seule interface est Claude : pas d'UI propre, hormis les écrans d'authentification OAuth. Ce type de produit se construit comme un **serveur d'outils déterministe et étroit** : toute la logique (splits zero-sum, budgets, dettes F10, soldes, cloisonnement) vit côté serveur, et le modèle ne fait que demander et afficher. Le domaine métier est déjà mûr dans `origin/main` (CONTEXT.md, ADR) ; le travail nouveau porte sur la surface MCP, l'autorisation, la politique d'écriture et la qualité du code écrit par des agents.

La recommandation de stack est un **monolithe modulaire TypeScript sur Node.js 26 LTS**, avec `@modelcontextprotocol/server` 2.4.0, un serveur d'autorisation embarqué (`oidc-provider` 9.15.1, certifié OpenID, qui gère PKCE, RFC 8707, rotation de refresh et CIMD), Postgres 18.7 avec Kysely et Row-Level Security, et Tailscale Funnel comme tunnel (TLS terminé sur le nœud). Le choix TypeScript plutôt que Python tient à MCP Apps (UI en JS), à la présence d'un AS certifié côté TS et à la maturité du mutation testing (StrykerJS). Python reste viable si le spike OFX échoue et si MCP Apps est abandonné.

Les quatre risques principaux :
1. **Sécurité :** un `confirm_*` appelable par le modèle n'est pas une frontière, car une injection via un libellé bancaire peut le déclencher. Le cloisonnement des comptes personnels doit être garanti par construction (identité issue du jeton, RLS).
2. **Intégration claude.ai :** elle échoue silencieusement (IP, 401, redirections, WAF). Un spike connecteur + OAuth de bout en bout doit précéder tout domaine.
3. **Exactitude financière :** montants en `bigint` de centimes, quotes-parts en points de base, idempotence obligatoire sur toute écriture car les retries d'artefact sont ambigus.
4. **Qualité du code agent :** la gate (mutation, couverture plancher, chemins protégés, compteur d'échappatoires à cliquet) doit exister avant la première ligne de domaine.

## Key Findings

### Recommended Stack

Verdict : TypeScript mono-langage. Versions vérifiées dans les registres le 2026-11-21.

**Core technologies :**
- **Node.js 26.13 LTS** (repli 24.22) : runtime ; `Temporal` activé par défaut.
- **TypeScript 6.0.3 épinglé** (pas 7.x) : TS 7 n'est pas encore compatible avec typescript-eslint 8.73, dependency-cruiser 18.8 ni Stryker.
- **`@modelcontextprotocol/server` 2.4.0** + `express` 2.0.2 + `node` 2.1.2 : SDK officiel v2, `createMcpHandler` en `legacy: 'stateless'` pour les specs 2025 que claude.ai parle.
- **`oidc-provider` 9.15.1** + `jose` 6.2.18 + `@simplewebauthn/server` 14.1.0 : AS embarqué, passkeys sur les pages de login. DCR désactivé, CIMD restreint à claude.ai/claude.com, client statique en filet.
- **Zod 4.6.7** : source de vérité pour `inputSchema`, `outputSchema`, DTO et types UI.
- **PostgreSQL 18.7** (épinglé par digest) : base unique (domaine, OAuth, jobs, audit). PG 19 écarté (sorti le 2026-11-19).
- **Kysely 0.29.9** + `kysely-codegen` + migrations SQL forward-only : SQL-first, invariants en base (CHECK, triggers, RLS).
- **`pg-boss` 12.38.2** : file de jobs dans Postgres, sans Redis.
- **Vitest 5.1.1**, **fast-check 4.10.3**, **StrykerJS 10.1.1**, **Testcontainers PG 18** (pas PGlite), **ESLint 10.15 + typescript-eslint 8.73**, **Biome 2.6.8** (formateur seul), **dependency-cruiser 18.8**, **knip 6.47**, **pnpm 12.21** (défauts supply-chain durcis).
- **Tailscale Funnel** (recommandé) : URL `*.ts.net` stable, TLS terminé sur le nœud. Cloudflare Tunnel en alternative. Caddy supprimé du plan.
- **DSP2 : Enable Banking** en mode « restricted production » (lier ses propres comptes). Appel HTTP avec JWT RS256 via `jose`, sans SDK. GoCardless écarté (fermeture non confirmée officiellement) ; Powens et Bridge écartés (sur contrat).
- **OFX/CSV :** `ofx-data-extractor` 1.6.0 et `csv-parse` 7.0.3, derrière un port `StatementParser` ; parseur maison en repli (spike obligatoire).

**Contraintes claude.ai qui dictent le stack (vérifiées dans les docs Claude) :**
- Specs d'autorisation 2025-03-26 / 2025-06-18 / 2025-11-25 : protocole « legacy », sans `Mcp-Session-Id`.
- Streamable HTTP, une seule route `POST /mcp`.
- `401` obligatoire avec `WWW-Authenticate: Bearer resource_metadata=...` ; un `200` portant l'en-tête est ignoré.
- `resource` du PRM = URL saisie dans Claude, chemin inclus, sans slash final. Claude n'utilise que la première entrée de `authorization_servers`.
- PKCE S256, RFC 8707 `resource` dans authorize et token, rotation des refresh tokens, `/token` en `application/x-www-form-urlencoded`, réponse < 10 s (30 s en refresh).
- Hostname en IPv4 globalement routable (A record, pas de CGNAT, pas d'AAAA seul), pas de 3xx vers un autre hôte, plage `160.79.104.0/21` à ne pas bloquer par WAF.
- Résultat d'outil ≈ 150 000 caractères, appel 240 s. Pas de subscriptions, sampling ni elicitation.
- `_meta.ui.domain` d'une MCP App dérivé de l'URL serveur : toute modification d'URL casse les UI.

**Patterns MCP prescrits :** `content` + `structuredContent` validé par `outputSchema` ; annotations `readOnlyHint` / `destructiveHint` / `idempotentHint` sur chaque outil, vérifiées par test ; identité depuis `ctx.http?.authInfo`, jamais un argument ; montants `amount_minor` + `display` formaté serveur ; `Temporal.PlainDate` pour le jour comptable (types à vérifier dans TS 6.0.3).

### Quality Gate pour code écrit par des agents IA (adaptée à la stack)

Demande explicite du projet. Cette section reprend STACK.md §10 et sert de cahier des charges pour la phase 0.

**Principes :**
1. **Déterministe d'abord** : jamais de relecture LLM comme gate.
2. **La CI serveur est le juge** : les hooks locaux sont un confort, un agent peut passer `--no-verify`.
3. **Toute assertion de test est suspecte** tant que la mutation ne l'a pas validée.
4. **Coût d'un faux positif faible, coût d'un faux négatif financier élevé** : seuils stricts dès le jour 1, sur un dépôt vierge.

**Ce qui change par rapport à l'ancienne gate** (`origin/main:docs/ci.md`) : couverture plancher bloquante et mutation bloquante sur le noyau pur ; dérogations (`# noqa`, `eslint-disable`) avec description obligatoire et compteur à cliquet ; chemins protégés contre l'agent ; une commande unique `pnpm quality` identique en pré-push et en CI, sans path-scoping.

**Checks par famille :**

| Famille | Checks clés (outil, sévérité) |
|---|---|
| A. Statique et types | `tsc --noEmit` avec flags stricts (`noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `noImplicitOverride`, `verbatimModuleSyntax`) : blocking. Lint type-aware `strictTypeChecked` (`no-floating-promises`, `no-unsafe-*`, `switch-exhaustiveness-check`) : blocking, `--max-warnings 0`. Assertions de type interdites (`as` sauf `as const`, `no-non-null-assertion`, `no-explicit-any`) : blocking. Complexité (`sonarjs/cognitive-complexity` ≤ 10, fonctions ≤ 60 lignes, profondeur ≤ 3, paramètres ≤ 4) : blocking dès le jour 1. Règles domaine sur mesure via `no-restricted-syntax` (pas de `parseFloat`, `Number(` hors DTO, `Math.round` dans `domain/**`, `Date.now` hors `Clock`, `process.env` hors `config/`, `sql.raw`) : blocking. Hygiène des directives (`eslint-comments`, `reportUnusedDisableDirectives`) : blocking. Biome `--check` : blocking. |
| B. Architecture et dépendances | `dependency-cruiser` : couches (`domain` n'importe que `domain`/`shared`), cross-module via `public.ts`, **les outils MCP n'importent jamais `adapters/db`**, pas de cycle, `pg`/`fs`/`fetch` interdits dans `domain` : blocking. `knip` (code mort, dépendances non listées) : blocking. `jscpd` (`--fail-on-new-clones` contre `origin/main`) : blocking sur `src/`. Script sur le lockfile : tout paquet ajouté doit avoir plus de 30 jours, exister sur npm, et porter le label humain `deps-approved` : blocking. Politique pnpm (`minimumReleaseAge` ≥ 7 j, `blockExoticSubdeps`, `allowBuilds` explicite, `trustPolicy: no-downgrade`, `--frozen-lockfile`) : blocking. |
| C. Sécurité | `gitleaks` (pré-commit staged, historique complet en CI) : blocking. `semgrep` CE avec **règles du projet** (handler d'outil sans `Principal`, concaténation SQL, `Math.random` pour un jeton, comparaison non constante de secrets) : blocking sur ERROR. `osv-scanner` sur `pnpm-lock.yaml` (high/critical bloquant) et `pnpm audit --prod`. `hadolint` sur le Containerfile : blocking ; scan d'image advisory. `actionlint` + `zizmor`, actions épinglées par SHA : blocking. `eslint-plugin-security` : advisory. `trufflehog` nightly : advisory. `syft` : advisory. |
| D. Tests | Tests sur PG 18 réel (Testcontainers), pas de mock de repository : blocking. Propriétés fast-check (Σ parts = total, Σ splits = 0, solde = montant − Σ règlements, import idempotent, budget restant borné, projection incrémentale = rejouée), model-based (`fc.commands`) pour le cycle de vie : blocking. Tests d'intégration auto-générés : trigger zero-sum, immutabilité `confirmed`, **chaque table à `owner_member_id` a RLS actif**, membre B ne lit jamais les données perso de A, admin inclus : blocking. Snapshot de `tools/list` relu par un humain à chaque diff : blocking. Flux OAuth e2e scripté avec Inspector `--cli` : blocking sur PR touchant auth ou déploiement. **Mutation** (StrykerJS, `vitest-runner`, `coverageAnalysis: perTest`) sur `src/domain/**` et `src/application/**` : blocking sur les fichiers modifiés (`--since origin/main`, seuil 80), complet en nightly. Couverture : `src/domain/**` 100 % lignes et branches, global 85/80, cliquet jamais inférieur à `main`. `@vitest/eslint-plugin` (`expect-expect`, `no-disabled-tests`, `no-conditional-expect`, `no-restricted-matchers` sur `toBeTruthy`/`toBeDefined`) : blocking. Ordre aléatoire (`sequence.shuffle`, seed loguée) : blocking. |
| E. Anti-contournement | Compteur d'échappatoires **à cliquet** (`@ts-ignore`, `eslint-disable`, `as any`, `as unknown as`, `!.`, `.skip`, `vi.mock(`) comparé à `quality/baseline.json`, ne peut que baisser, budget initial 0 : blocking. Job d'intégrité : échoue si les seuils baissent sans label `gate-change-approved`, ou si le nombre d'`expect` d'un fichier de test baisse : blocking. Règle agent refusant `git commit --no-verify` et `git push --force` : blocking côté agent. `pnpm quality` émet `reports/gate.json` lisible par l'agent. |

**Répartition :** pré-commit (≤ 10 s : Biome, ESLint en cache, gitleaks, actionlint, refus d'édition de chemins protégés, compteur) ; pré-push (≤ 60 s : `tsc`, dependency-cruiser, knip, `vitest related`) ; CI pull request (juge, ≤ 8-10 min : tout `pnpm quality`, Stryker sur le diff du domaine, gitleaks historique, Semgrep, osv-scanner, hadolint, e2e OAuth si auth ou déploiement touchés ; un seul check requis `quality`) ; nightly (Stryker complet, fast-check 1000+ runs, Semgrep complet, trufflehog, conformance MCP, test de restauration).

**Chemins protégés (agent en lecture seule) :** `.github/**`, `eslint.config.*`, `tsconfig*.json`, `vitest.config.*`, `stryker.config.*`, `.dependency-cruiser.*`, `knip.json`, `.jscpd.json`, `lefthook.yml`, `quality/**`, `semgrep/**`, `pnpm-workspace.yaml`, `package.json` (scripts et dependencies), `pnpm-lock.yaml`, `Containerfile`, `deploy/**`, `CODEOWNERS`, `.claude/**`, `CLAUDE.md`/`AGENTS.md`. Trois couches : CODEOWNERS, permissions de l'agent, job d'intégrité. Limite : une PR peut modifier son propre workflow ; seul CODEOWNERS sur `.github/**` l'arrête.

**Stratégie de test, par ordre de fiabilité :** (1) noyau pur (exemples, propriétés, mutation) ; (2) intégration PG 18 réel ; (3) contrat MCP (snapshot, schémas, annotations, 401) ; (4) e2e OAuth avec simulation des spécificités claude.ai ; (5) adaptateurs externes (MSW, golden files anonymisés, jamais de réseau en CI). Les oracles financiers (Money, répartition, F10, règlements) sont écrits par un humain à partir des exemples de CONTEXT.md.

**Vigilance :** Stryker avec vitest-runner a un bug ouvert (#6004) : ne pas committer le fichier d'incrémental. Compatibilité Stryker avec Vitest 5 non confirmée. La mutation trouve les tests faibles, **pas les tests faux** : d'où les oracles humains.

### Expected Features

**Must have (v1) :** connecteur MCP + OAuth conforme, identité par membre (aucun `user_id` dans les outils) ; foyer singleton, rôles, bootstrap, invitations (jeton haché, 7 jours, rôle `member`) ; cloisonnement strict y compris vis-à-vis de l'admin ; comptes perso et communs, quotes-parts (défaut 50/50), catégories avec archivage ; transactions à splits zero-sum, états `draft/planned/confirmed/void`, immutabilité à `confirmed` ; `Money` en centimes, verrou EUR ; idempotence et erreurs typées sur toutes les écritures ; saisie conversationnelle (`create_transaction`, résolution par nom avec `needs_clarification`, annulation de la dernière saisie) ; lectures agrégées (`get_household_context`, `get_dashboard`, `get_balances`, listes paginées) ; budgets et alertes 80/100 % **lues** (pas de push) ; dettes F10 et `personal_share_request` avec masquage côté débiteur, règlements multi-lignes ; politique d'écriture `direct` et `propose` par membre × type d'action, PendingAction, planchers, audit consultable ; artefacts dashboard, formulaire de saisie, écran d'actions en attente ; import OFX + dédup + triage `$file` + pointage avec confirmation humaine (jamais d'auto-confirm) ; analyse de base.

**v1.x :** mode `risk_based` ; récurrences et solde projeté (absentes de PROJECT.md Active, présentes dans ADR 0007 : à trancher) ; épargne et projection 90 j ; import CSV ; triage assisté avec mémoire ; revue mensuelle ; double accord sur les règlements ; annulation par lot ; photo de ticket.

**v2+ :** agrégation DSP2 (coût élevé, valeur après un import solide) ; confirmation MCP Apps `visibility: ["app"]` ; notifications hors Claude ; multi-devise ; multi-foyers (hors périmètre).

**Anti-features :** `run_sql` ou `api_request` ; Claude qui calcule splits, dettes ou totaux ; édition de montant d'une transaction `confirmed` ; auto-confirm du pointage ; données financières dans la base de l'artefact ; écriture au chargement ou par `watchTool` ; lien public sur un artefact connecté ; stockage de crédentials bancaires ; admin qui lit les comptes des autres ; reset 2FA par l'admin via un outil.

**Surface MCP :** 25 à 35 outils, étroits, lecture et écriture séparées, chacun avec `title` et annotations. Lectures : `readOnlyHint: true`. Écritures additives : `destructiveHint: false`. Écritures destructives ou engageant un autre membre : `destructiveHint: true`. Ressources et prompts de documentation du contrat. Pas de dépendance aux ressources pour le contexte critique.

**Données importées = `untrusted_text`** : jamais déclencheur d'écriture sans confirmation.

**Politique d'écriture :** modes `direct`, `propose`, `risk_based` ; classes R0 (lecture) à R3 (identité, droits, politique : toujours `propose` hors-bande) ; planchers absolus (`confirm_reconciliation` jamais `direct`). Assouplir en deux temps, durcir immédiatement.

**Import :** le relevé transite par `callTool` avec `$file` (≤ 16 Mio), jamais par le contexte du modèle. Conditionné à `listTools().fileArgs` côté lecteur.

### Architecture Approach

ARCHITECTURE.md est agnostique de la stack ; ses exemples de code et certains passages (ADR, `src/*.py`) sont hérités de l'ancien projet Python et sont à traduire.

**Décisions structurantes :**
1. Monolithe modulaire + Postgres, une image, deux processus (`app`, `worker`). Un déploiement = un foyer.
2. MCP Streamable HTTP sans état serveur : requêtes autoportantes ; handles inter-appels (`import_id`, `pending_action_id`, curseurs) minés par le serveur et passés en arguments.
3. AS intégré (module `oauth`, bibliothèque éprouvée) séparé du resource server par un port `TokenVerifier`.
4. `Principal` extrait du jeton, passé à chaque outil ; aucun outil n'accepte un `member_id`.
5. Cloisonnement en trois couches : `VisibilityScope` applicatif ; repositories qui exigent un scope ; RLS Postgres en filet (`SET LOCAL app.member_id`, rôle applicatif non propriétaire, sans `BYPASSRLS`). **Aucune politique « admin » de lecture.**
6. Politique d'écriture côté serveur, module `agent` transport-agnostique.
7. Pipeline d'écriture unique : authn → idempotence → validation d'un Command typé → politique → exécution ou PendingAction → projections → audit → commit, dans une transaction. Résultat uniforme `applied | pending_confirmation | rejected`.
8. Calculer à la lecture, matérialiser seulement ce qui dépend de l'ordre (dettes F10, ordre `(date, id)`).
9. Contrats d'outils = API publique versionnée (`outputSchema`, évolutions additives, noms figés).
10. Artefacts d'abord, MCP Apps ensuite ; backend agnostique de l'UI.

**Composants :** `oauth` (AS : tokens liés au `resource`, CIMD + DCR, rotation, RFC 9207) ; `mcp` (RS : Streamable HTTP, 401, validation d'audience, registre d'outils) ; `agent` (politique, PendingAction, idempotence, audit, rate limit) ; `identity` ; `accounts` (fournisseur du VisibilityScope) ; `transactions` (aggregate immuable, splits, void) ; `budgets` ; `debts` (projection F10 pure sur scalaires, partages, override, règlements) ; `banking` (import, provider worker seul, reader cache) ; `reconciliation` (machine d'états, pas d'auto-confirm) ; `savings` ; `notifications` (outbox) ; `worker` (jobs SKIP LOCKED).

**Graphe :** `composition` ; adaptateurs `mcp | web | worker | oauth` ; `agent` ; `reconciliation | debts | notifications | savings` ; `banking | budgets` ; `transactions` ; `accounts | categories` ; `identity` ; `shared`. Remontée par `DomainEvent`. Outillé par dependency-cruiser : le worker seul touche `banking.providers`.

**Patterns :** `Principal` explicite ; politique = fonction pure `decide(...)`, le plus strict gagne ; idempotence à deux niveaux (clé obligatoire persistée avec le résultat, dédup métier en repli) ; PendingAction (`pending → confirmed | rejected | expired | superseded`, liaison au membre, `payload_hash`, TTL, CAS, revalidation) ; projections reconstructibles (`verify`, `rebuild`) ; pagination par curseur `(date, id)`, limite 50 (max 200), budget ≈ 100 000 caractères avec `truncated: true`.

**Flux clés :** lecture (Bearer → Principal → queries avec scope et RLS → `structuredContent` + `as_of`) ; écriture (clé → pipeline → `applied` ou `pending`) ; F10 (`TransactionConfirmed` → restant scalaire → `debts.domain` → dettes dans la même transaction) ; DSP2 (worker seul, ≤ 4 par jour et par banque, `last_sync_at` exposé).

**Anti-patterns à interdire par règle :** identifiant de membre en argument ; confirmation par le même agent présentée comme sécurité ; outil fourre-tout ; Claude qui agrège des lignes brutes ; SQL dans les handlers ; passthrough de token ; état de session ; projection hors transaction ; données incrustées dans le HTML d'un artefact.

**Ordre de construction (ARCHITECTURE, étapes 0 à 10) :** 0 squelette, CI, linter de graphe, tunnel, `/healthz` ; 1 identité, OAuth, transport, `whoami` (débloque claude.ai) ; 2 comptes, visibility, RLS et banc de fuite, catégories ; 3 transactions, WritePipeline en `direct`, premier artefact en lecture ; 4 politique complète, pending, confirmation ; 5 budgets, seuils, outbox, worker ; 6 dettes F10 et règlements ; 7 import fichier, tri, réconciliation ; 8 DSP2 ; 9 épargne, récurrences, analyse ; 10 MCP Apps et page d'approbation si requise.

### Critical Pitfalls

PITFALLS.md classe par gravité ; les phases P0 à P8 sont des étiquettes hypothétiques. Tags : [P] primaire, [R] rétrospective du dépôt précédent, [S] secondaire, [I] inférence.

1. **Confirmation illusoire (C9).** Un `confirm_pending_action` visible du modèle peut être exécuté par Claude seul, sur injection ou erreur. Idem pour un outil qui change la politique. **Prévention :** canal de confirmation hors modèle (voir Convergences) ; outils de changement de politique hors modèle ; annotations exactes.
2. **DCR ouvert et redirect URI non épinglés (C1).** Un attaquant peut obtenir le code d'un membre et accéder à ses finances. **Prévention :** liste blanche exacte de redirect URI, pas de wildcard ; CIMD avec protection SSRF (IP privées refusées, timeouts, taille max, pas de redirection) ; rate limit sur `/register` ; consentement avec hostname de redirection.
3. **Audience et identité (C2, C5).** Token sans vérification d'`aud`, paramètre d'identité dans un outil, oracle de non-disclosure (preview d'import, message d'erreur). **Prévention :** `aud` comparé après normalisation à l'URL canonique unique ; acteur = `sub` ; même erreur `not_found` pour inexistant et inaccessible ; matrice outil × rôle × classe de compte, avec ≥ 3 membres dont un admin non-membre.
4. **Connecteur injoignable alors que le serveur tourne (C3, C18, C20).** IPv4 publique, `401` avec `resource_metadata`, pas de 3xx, pas de WAF ou Access sur `/mcp`, `/token`, `/.well-known/*` ; routes d'administration (`/docs`, `/metrics`, `/setup`) hors du hostname public. **Prévention :** diagnostic de bord depuis l'extérieur ; allowlist de routes en CI ; validation par un vrai ajout de connecteur.
5. **Écritures non idempotentes (C8).** `server_unavailable` ou `upstream_error` ne prouve pas que l'outil n'a pas tourné. **Prévention :** clé persistée avec le résultat dans la même transaction ; dédup en repli ; plafond de débit ; pas de retry automatique côté artefact.
6. **Injection via données importées (C6).** Libellés bancaires, mémos, libellés de partage écrits par un autre membre ; combiné à d'autres connecteurs (mail, documents), la combinaison donnée privée + contenu non fiable + canal de sortie est exploitable. **Prévention :** `untrusted_text` tronqué et normalisé ; descriptions statiques ; aucun canal d'exfiltration (pas d'URL ni webhook en sortie) ; tests d'injection en CI.
7. **Claude calcule ou recopie mal (C7, C12, C13).** Flottants, arrondis qui ne conservent pas le total, UUID tronqués, « ce mois-ci » mal résolu. **Prévention :** `bigint` de centimes ; points de base avec plus fort reste et départage déterministe ; zero-sum en domaine et en base ; dates métier en `date` avec fuseau du foyer ; horloge injectée ; références courtes ou `ambiguous`.
8. **Dettes non idempotentes (C14).** DELETE + INSERT d'une dette référencée par un règlement casse les lignes ; un budget modifié réécrit des dettes vues. **Prévention :** identité déterministe `(transaction_source, origine, from, to)` avec upsert ; recalcul sérialisé par budget et période ; événement d'audit à chaque re-matérialisation ; squelette end-to-end dès P3 via les vrais outils.
9. **Dérive d'artefacts et données figées (C10, C11, C15).** Renommage de champ affichant `NaN` ; artefact ouvert par un autre membre avec ses identifiants ; consentement DSP2 expiré invisible. **Prévention :** contrats versionnés et snapshots de `tools/list` ; `watchTool` au chargement, pas de données incrustées ; états d'erreur par code ; `last_sync_at` et `consent_expires_at` dans chaque résultat ; canal proactif pour l'expiration.
10. **Code agent qui contourne la gate (C16).** Tests édités, `noqa`, `.skip`, seuils baissés, tests tautologiques. **Prévention :** voir Quality Gate ; gate en P0.

**Autres :** sauvegardes inutilisables et secrets perdus (C17 : dump chiffré hors machine, test de restauration, clés OAuth et Enable Banking hors git) ; supervision absente (C19 : sonde externe) ; refresh tokens (M2 : grâce, révocation par membre) ; bootstrap du premier admin (M3 : secret à usage unique, verrou transactionnel) ; plans claude.ai des membres (M8 : tester avec un second compte) ; fuseaux et CSV français (M7 : `;`, `,`, `JJ/MM/AAAA`, cp1252) ; confidentialité vis-à-vis du fournisseur du modèle (M10 : décision écrite au foyer).

## Convergences inter-chercheurs

Les quatre fichiers arrivent indépendamment aux mêmes conclusions. Traiter comme contraintes.

1. **Canal de confirmation hors modèle.** Un outil de confirmation appelable par Claude n'est pas une frontière (FEATURES, ARCHITECTURE anti-pattern 2, PITFALLS C9). Seuls deux mécanismes séparent « l'humain a cliqué » de « le modèle a décidé » : MCP Apps `visibility: ["app"]` (non confirmé en pratique) et page d'approbation hors-bande avec session du membre. `destructiveHint` fait demander une approbation, mais « Always allow » l'annule. **Tension à corriger :** STACK §3.2 décrit `propose_*` / `confirm_*` sans préciser le canal.
2. **Idempotency keys obligatoires** sur toute écriture (FEATURES, ARCHITECTURE Pattern 4, PITFALLS C8), avec dédup métier en repli. Nuance : PITFALLS la dit optionnelle ; retenir l'obligation.
3. **`readOnlyHint` précis sur chaque lecture, sans effet de bord.** Le runtime refuse `watchTool` sur un outil non en lecture seule ; test registre avant/après.
4. **Cloisonnement par RLS, pas par discipline.** Test méta sur les tables à `owner_member_id` ; matrice de fuites ; aucune exemption admin. Point ouvert : RLS avec pooling.
5. **Connecteur et OAuth de bout en bout comme premier spike** (STACK spike 1, ARCHITECTURE étape 1, PITFALLS P1).
6. **Quality gate avant le domaine** (STACK §10, ARCHITECTURE étape 0, PITFALLS C16).

Autres : identité depuis le jeton ; Claude ne calcule rien qui fasse foi ; données importées = `untrusted_text` ; montants en `bigint` de centimes ; pas de `run_sql` ni `api_request` ; oracles humains sur le noyau financier ; un seul hostname public.

## Implications for Roadmap

Ordre tiré des dépendances (ARCHITECTURE) et des pitfalls (PITFALLS), avec les contraintes demandées : spike connecteur + OAuth en premier, gate avant le domaine. Numéros indicatifs.

**Phase 0 : Socle et quality gate.** Dépôt TypeScript (Node 26, pnpm 12, TS 6.0.3), image unique, Postgres 18 avec rôle migrations séparé, `pnpm quality` complet, chemins protégés et compteur à cliquet, linter de graphe, `/healthz`, allowlist de routes en test, CI juge. Évite C16, C18, C20.

**Phase 1 : Spike connecteur et OAuth de bout en bout.** `identity` minimal (bootstrap à secret unique, invitations), `oauth` (PRM, AS metadata, PKCE, RFC 8707, CIMD restreint, DCR désactivé, refresh rotatif avec grâce), `mcp/transport` (Streamable HTTP stateless, 401, `expectedResource`, `allowedHosts`), outil `whoami`, tunnel Funnel, diagnostic de bord, test e2e. Ajout du connecteur par un **second compte membre**. **Sortie de phase obligatoire** avant la phase 2. Évite C1, C2, C3, C4, C5, M2, M3, M8.

**Phase 2 : Cloisonnement et fondations financières.** `accounts` (perso et commun, quotes-parts en points de base), `visibility`, RLS avec `SET LOCAL`, test méta, matrice outil × rôle × classe de compte, `categories`, `Money` (bigint, plus fort reste, zero-sum), horloge injectée, fuseau du foyer. Premier backup chiffré et premier test de restauration. Évite C5, C12, C13, C17.

**Phase 3 : Transactions, pipeline d'écriture, premier artefact.** `transactions` (splits, états, immutabilité, void), `WritePipeline` (idempotence, validation, politique `direct` seul, audit), `record_transaction` avec résolution par nom, listes paginées, `get_household_context`, `get_dashboard` minimal, premier artefact en lecture (`watchTool`). Squelette e2e : une dépense saisie et confirmée via les vrais outils. Évite C6, C7, C8, C10, M1, M4, M5.

**Phase 4 : Politique d'écriture et confirmation.** Politique par membre × type d'action, planchers, `pending_actions` (cycle de vie complet), `confirm_pending_action` sur le **canal retenu**, `set_write_policy` hors modèle, rate limit par grant, audit consultable, `void_transaction` en `destructiveHint: true`. Évite C9. **Décision de canal préalable** (voir Spikes).

**Phase 5 : Budgets, alertes, worker.** `budgets` (consommation par requête, restant ≥ 0), seuils 80/100 % lus, `notifications` (outbox), worker minimal, jobs `verify`, expiration, purge. Évite C14 (recalcul sérialisé).

**Phase 6 : Dettes F10 et règlements.** `debts` (domaine pur sur scalaires, identité déterministe, upsert), partages avec masquage débiteur par liste blanche, `share_ratio`, `debt_generation_override`, règlements multi-lignes, `explain_debt`, dry-run `simulate_budget_change` **avant** d'autoriser `direct` sur les budgets. Évite C14, C12, C5.

**Phase 7 : Import fichier, triage, pointage.** Peut démarrer après la phase 3. `upload_bank_file` via `$file` (spike `fileArgs` d'abord), parseurs OFX et CSV derrière `StatementParser`, décodage explicite, dédup multiensemble, commit en `draft`, écran de triage, `reconciliation` sans auto-confirm. Évite C15, C6, M7, C11.

**Phase 8 : Artefacts complets et spike MCP Apps.** Formulaire, dettes et règlements, actions en attente, budgets et épargne, gabarits distribués par ressources, états d'erreur par code, fraîcheur `cache.storedAt`. Spike MCP Apps limité à l'écran d'actions en attente. Évite C11, C10.

**Phase 9 : Agrégation DSP2 (Enable Banking).** `BankingProvider` (worker seul), consentement via callback lié au membre, sync ≤ 4 par jour et par banque, rappels J-14, `last_sync_at` et `consent_expires_at`, canal proactif, dédup fichier ↔ API, repli permanent sur le fichier. Enregistrement de l'application agrégateur à démarrer dès la phase 0. Évite C15, C17.

**Phase 10 : Épargne, récurrences, analyse.** Objectifs et allocations (warnings, pas d'erreur bloquante), projection 90 j, récurrences idempotentes (`ON CONFLICT DO NOTHING`), `simulate_savings`, `analyze_spending`, `compare_periods`, `explain_budget_overrun`, prompt `point_mensuel`.

**Transverse finale : Exploitation et durcissement.** Restauration testée, sonde externe, rotation de secrets, inventaire de routes, nightly complet, runbooks, documentation d'onboarding (même nom de connecteur pour tous ; plans payants pour les artefacts `mcp`). Évite C17, C19, C20, M10.

### Phase Ordering Rationale

- Spike connecteur (1) avant le domaine : sans endpoint joignable, aucun test réel depuis claude.ai.
- Matrice de cloisonnement (2) avant tout outil de données.
- Pipeline d'écriture (3) avant la deuxième écriture : point unique d'idempotence, d'audit et de politique.
- Confirmation (4) avant les outils destructifs.
- Budgets (5) avant dettes (6) : F10 lit le restant R.
- Import (7) après le pipeline, en parallèle de 5-6 ; DSP2 (9) après l'import car il réutilise le modèle et la dédup.
- Artefacts complets (8) après les services.

### Research Flags

**Recherche dédiée avant planification (`/gsd-plan-phase --research-phase`) :**
- **Phase 1 :** AS embarqué (`oidc-provider`, CIMD expérimental) ; URL CIMD d'Anthropic non documentée ; comportement de claude.ai sur `resource` et RFC 9207. Composant le plus risqué.
- **Phase 4 :** canal de confirmation (MCP Apps app-only, page hors-bande, `destructiveHint` et « Always allow »). Preuves surtout secondaires.
- **Phase 7 :** libs TS sur fichiers français réels ; fixtures anonymisées des banques du foyer ; `fileArgs`.
- **Phase 8 :** rendu MCP Apps sur connecteur custom peu fiable (ticket #671) ; `_meta.ui.visibility` non vérifié.
- **Phase 9 :** couverture des banques du foyer, multi-membres en mode restreint, CGU, quotas réels.
- **Phase 2 :** RLS et pool (`SET LOCAL` avec Kysely) à prototyper.

**Patterns connus (pas de recherche de phase) :** phase 0 (gate et CI, reprise de l'ancien dépôt) ; phase 3 (pipeline, double-entrée, ADR 0001, 0014, 0017) ; phase 5 (budgets, worker) ; phase 6 (spécifiée dans CONTEXT.md et ADR 0002, 0011, 0017 : à implémenter, pas à rechercher) ; phase 10.

## Spikes et décisions ouvertes

**Spikes :**
1. Connecteur e2e via Funnel (avant phase 2) : A record IPv4, 401 et PRM, CIMD, refresh rotatif, `ui.domain`, second compte.
2. OFX et CSV sur fixtures réelles (avant phase 7, idéalement dès phase 0) : `ofx-data-extractor` contre parseur maison.
3. Enable Banking (avant phase 9) : `/aspsps?country=FR`, comptes de plusieurs membres, CGU.
4. RLS et pool (phase 2) : `SET LOCAL` par transaction avec Kysely.
5. Temporal dans TS 6.0.3 (phase 2) : types ou polyfill.
6. Mutation testing (phase 0) : Stryker 10.1.1 avec Vitest 5.1.1, bug #6004.
7. `fileArgs` (phase 7) : disponibilité côté lecteurs du foyer.

**Décisions :**
- **Canal de confirmation** (bloque la phase 4 ; au plus tard avant tout outil destructif exposé) : hors-bande vs `destructiveHint` + planchers vs MCP Apps app-only. Recommandation : niveaux 0 et 1 en v1, moteur de politique acceptant un `channel` par décision, niveau hors-bande pour règlement, void et import en masse dès que la page existe. Documenter que « Always allow » annule la garantie.
- **Artefacts `mcp` vs MCP Apps :** artefacts en v1, MCP Apps en spike limité (phase 8).
- **Politique par défaut :** création de transaction en `direct` ; `void`, archivage, règlement, pointage confirmé, import en masse, `share_ratio` en `pending`.
- **Plancher de foyer :** l'admin peut-il imposer un minimum sans voir les comptes personnels ? Décision produit.
- **Récurrences :** absentes de PROJECT.md Active, présentes dans ADR 0007 ; recommandation v1.x.
- **DSP2 en v1 ou v2 ?** PROJECT.md le met dans Active ; FEATURES le met en v2+. À trancher à la définition des exigences.
- **Protocole cible :** tester les specs 2025 que claude.ai parle ; re-vérifier à chaque montée de version.

**Incohérences à corriger avant le roadmap :**
- ARCHITECTURE et PITFALLS contiennent des références Python (`src/*.py`, ruff, pyright, import-linter, mutmut, Hypothesis) : les traduire en équivalents TS retenus.
- STACK §3.2 : `propose_*` / `confirm_*` sans canal précisé.
- STACK « Free = 1 connecteur » vs FEATURES « pas de plan Free pour les artefacts » : compatibles si les artefacts `mcp` sont réservés aux plans payants ; à confirmer.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Protocole, SDK et contraintes claude.ai vérifiés (HIGH). Enable Banking : HIGH sur le mode, MEDIUM sur la gratuité. Parseurs OFX TS : LOW-MEDIUM. TS 7, Stryker avec Vitest 5 : MEDIUM. GoCardless : LOW, écarté. |
| Features | MEDIUM-HIGH | HIGH sur les capacités `mcp` (contrat 0.2.98) et la spec MCP Apps ; concurrence faite de mémoire (MEDIUM) ; rendu MCP Apps sur connecteur custom : MEDIUM-LOW. |
| Architecture | MEDIUM-HIGH | Spec MCP et docs Claude (HIGH) ; politique d'écriture, RLS, jobs : jugement appuyé sur les ADR (MEDIUM). |
| Pitfalls | MEDIUM-HIGH | Sécurité agent (confirmation, injection) surtout [S] et [I] : à valider par spike. |

**Confiance globale : MEDIUM-HIGH.** Incertitudes sur trois composants : AS embarqué (CIMD), canal de confirmation (MCP Apps), agrégation DSP2 (couverture, quotas). Chacun a un spike ou une recherche de phase.

### Gaps à traiter

- URL CIMD de claude.ai non documentée : restreindre par hôte, vérifier au spike phase 1.
- Version de protocole réellement parlée par claude.ai : 2026-07-28 non confirmée.
- `_meta.ui.visibility` non vérifié (avant phase 8).
- Rendu MCP Apps sur connecteur custom : ticket #671 ouvert, sans correctif officiel.
- Step-up `insufficient_scope` dans Claude : non vérifié, ne pas en dépendre.
- `listTools().fileArgs` et noms d'API du runtime (`watchTool`, `callTool`) : types livrés avec le runtime, pas doc publique ; contrat épinglé, à tester.
- Couverture des banques du foyer, multi-membres en mode restreint, quotas DSP2 par banque.
- Temporal dans TS 6.0.3 ; RLS avec pool en mode transaction.
- Mobile : page d'aide incohérente sur les connecteurs interactifs.
- Achats et transactions financières dans les vues de chat : non pris en charge selon Anthropic ; un règlement reste un enregistrement comptable à surveiller.

## Sources

**Primaires (HIGH) :** spec MCP autorisation 2025-11-25 et 2026-07-28 ; spec transports et sécurité ; spec MCP Apps 2026-01-26 ; docs Claude connecteurs (construction, authentification, dépannage, tests, critères de revue, soumission, MCP Apps) ; docs Claude Code sur les artefacts ; contrat runtime des artefacts 0.2.98 (`mcp.d.ts`, fourni par la session) ; SDK TypeScript MCP v2 ; `oidc-provider` 9.15.1 ; Enable Banking (référence, mode restreint, FAQ) ; Tailscale Funnel ; domaine métier `origin/main` (CONTEXT.md, ADR 0001 à 0019, architecture.md, ci.md).

**Secondaires (MEDIUM) :** Keycloak 26.7 (CIMD expérimental) ; pages d'aide Anthropic sur les connecteurs interactifs ; ticket ext-apps #671 ; issue Stryker #6004 ; pnpm supply-chain ; incident Trivy de mars 2026 ; arXiv 2605.08366 et 2609.37143 (tests écrits par agents) ; concurrents (connaissance générale).

**Tertiaires (LOW) :** fermeture de GoCardless BAD (blog et forum, page officielle non concluante) ; tableau Zuplo des IdP (Authentik, Zitadel, Pocket ID : DCR et CIMD non confirmés) ; timeout Cloudflare de 100 s non vérifié ; contournements MCP Apps (rapport unique).

---
*Research completed: 2026-11-21*
*Ready for roadmap: yes, après correction des incohérences de corpus listées dans « Spikes et décisions ouvertes » et validation du canal de confirmation.*
