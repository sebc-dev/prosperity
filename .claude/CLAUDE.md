<!-- GSD:project-start source:PROJECT.md -->

## Project

**Prosperity — Connecteur Claude**

Prosperity est l'application de finances partagées d'un foyer, repensée en **connecteur pour Claude** : un backend auto-hébergé, exposé comme serveur MCP distant, qui porte toute la logique métier et tous les calculs (transactions, budgets, dettes entre membres, import bancaire, pointage, épargne). Claude est la seule interface. Il récupère les données dont il a besoin, répond aux questions d'analyse et construit des **artefacts** (tableaux de bord, formulaires, écrans de tri) qui se remplissent avec les données du connecteur et permettent aussi la saisie. Les utilisateurs sont les N membres d'un foyer, chacun connecté à Claude avec sa propre identité.

**Core Value:** Chaque membre du foyer peut, en une phrase à Claude, **saisir** une dépense ou **voir** l'état exact et à jour des finances du foyer (soldes, budgets, dettes). Les chiffres viennent d'un backend qui calcule juste et ne montre à chacun que ce qu'il a le droit de voir.

### Constraints

- **Interface** : Claude (claude.ai + artefacts) est l'unique client. Toute fonctionnalité passe par des outils MCP — pas d'UI web propre au backend, hormis les écrans d'auth/OAuth nécessaires
- **Connecteur distant** : un connecteur claude.ai exige une URL HTTPS publique et un flux OAuth conforme à la spec d'autorisation MCP. C'est un prérequis à tout le reste
- **Sécurité / vie privée** : identité par membre de bout en bout. Les outils filtrent selon l'utilisateur authentifié, jamais selon ce que Claude demande. Données financières réelles d'un foyer
- **Exactitude** : les calculs (dettes, budgets, soldes) sont faits côté serveur, de façon déterministe et idempotente. Claude ne calcule rien qui fasse foi
- **Hébergement** : auto-hébergé sur homelab, ressources modestes, déploiement simple et sauvegardable
- **Bancaire** : l'agrégation DSP2 passe par un agrégateur tiers (à choisir : Enable Banking, GoCardless…), avec ses contraintes de consentement (renouvellement à 90/180 jours)

<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->

## Technology Stack

## 1. Verdict

## 2. Contraintes claude.ai qui dictent le stack (toutes HIGH, docs `claude.com/docs/connectors/building/*`)

| Fait vérifié | Conséquence de conception |
|---|---|
| Claude suit les specs d'autorisation **2025-03-26, 2025-06-18, 2025-11-25**. La spec MCP la plus récente est **2026-07-28** (sans état, sans `initialize`, DCR déprécié au profit de CIMD) mais claude.ai ne la liste pas. | Le serveur doit parler le protocole « legacy » 2025. SDK TS v2 : `createMcpHandler` sert le trafic 2025 par défaut (`legacy: 'stateless'`), pas de `Mcp-Session-Id`, pas de sticky session. |
| Transport : **Streamable HTTP** (HTTP+SSE legacy toléré, déprécié). | Une seule route `POST /mcp`. Pas de SSE à maintenir. |
| Auth : **`401` obligatoire** avec `WWW-Authenticate: Bearer resource_metadata="…"` ; un `200` portant l'en-tête est ignoré. Un `isError: true` en `200` ne déclenche pas l'OAuth. | Gate HTTP avant le SDK (middleware `requireBearerAuth`). Jamais de refus d'auth dans un handler d'outil. |
| Claude n'utilise que la **première** entrée de `authorization_servers`. `resource` du PRM doit égaler exactement l'URL saisie dans Claude (chemin inclus). | `resource = https://<hôte>/mcp`, URL canonique figée en config, sans slash final. |
| Enregistrement client : CIMD (« Use Claude's published identity », recommandé), DCR (« Register automatically ») ou **client OAuth pré-enregistré** (« Use your own OAuth client », champ client_id dans le dialogue avancé). CIMD n'est choisi que si les métadonnées AS annoncent `client_id_metadata_document_supported: true` **et** `"none"` dans `token_endpoint_auth_methods_supported`. | Annoncer CIMD, garder un client statique public en filet, **désactiver DCR** (surface publique inutile). |
| Redirect URI : `https://claude.ai/api/mcp/auth_callback` (possible bascule vers `claude.com`) ; Claude Code : loopback sur port éphémère (`localhost` et `127.0.0.1`, match sans port). | Enregistrer les deux hôtes claude.ai/claude.com ; match loopback sans port si Claude Code est utilisé. |
| PKCE **S256** sur chaque autorisation ; `resource` (RFC 8707) dans les requêtes authorize et token ; `code_challenge_methods_supported: ["S256"]` annoncé. | Jetons à audience = URL MCP canonique ; validation d'`aud` côté RS. |
| `/token` : `application/x-www-form-urlencoded`, réponse **< 10 s** (30 s pour refresh), erreur `invalid_grant` pour refresh invalide, **rotation des refresh tokens** pour clients publics. | Refresh rotation activée ; pas de calcul lourd (Argon2) sur le chemin token. |
| Sans `scope` dans le `WWW-Authenticate`, Claude demande **tous** les `scopes_supported` (+ `offline_access` si listé). | Émettre `scope` dans le 401 ; `scopes_supported` minimal. |
| Le hostname doit résoudre vers des IPv4 **globalement routables** (A record public ; pas CGNAT `100.64/10`, pas privé, pas AAAA seul). Pas de redirection 3xx vers un autre hôte (l'en-tête `Authorization` est perdu). Egress Anthropic : `160.79.104.0/21`. WAF/bot-management qui renvoie 403/429 casse le flux. | Contrainte directe sur le choix du tunnel (§ 7). |
| Limites : résultat d'outil ≈ **150 000 caractères** (claude.ai/Desktop), appel d'outil **240 s**. Au-delà, un MCP App reçoit un pointeur de fichier au lieu des données. | Pagination dans tous les outils de lecture ; agrégats prêts à afficher, jamais de dumps. |
| Pas de support de : resource subscriptions, sampling, capacités draft. Roots/Sampling/Logging sont dépréciés dans la spec 2026-07-28. | Ne rien bâtir dessus. Confirmations d'écriture via un outil `confirm_*` explicite (PendingAction), pas via elicitation. |
| Plans : l'ajout d'un connecteur custom par URL marche en Free (1 connecteur), Pro, Max, Ultra, Team, Enterprise. Sur Team/Enterprise un Owner l'ajoute, chaque membre s'authentifie avec son propre compte. | Chaque membre ajoute le connecteur sur son propre compte claude.ai et passe son OAuth : identité par membre native. |
| MCP Apps : supportés en connecteur custom ; `_meta.ui.domain` = 32 premiers hex du SHA-256 de l'URL serveur + `.claudemcpcontent.com` ; badge « Unverified » en custom. | Calculer `ui.domain` en config depuis l'URL canonique (tout changement d'URL ou slash final casse les UI). |

## 3. Recommended Stack

### 3.1 Core

| Technology | Version | Purpose | Why Recommended | Conf. |
|---|---|---|---|---|
| Node.js | **26.13.x LTS « Lithium »** (LTS depuis oct. 2026). Repli : 24.22.x « Krypton » | Runtime | LTS actif jusqu'à fin 2027, `Temporal` activé par défaut depuis Node 26 (dates comptables sans `Date`). Exigences moteur des libs retenues : ≥ 22 (Kysely, Stryker, vitest 5, testcontainers). | HIGH |
| TypeScript | **6.0.3, épinglé exact** (pas 7.x pour l'instant) | Langage | TS 7.0.2 (Go natif, GA 2026-07-08) n'embarque pas encore l'API programmatique JS. `typescript-eslint` 8.73.0 exige `typescript <6.1.0` ; `dependency-cruiser` 18.8.0 déclare `>=2 <7.0.0 \|\| >=7.1.0` ; Stryker ne supporte TS 7 qu'en expérimental. Sur une base de code de foyer, la vitesse de TS 7 n'apporte rien ; la compatibilité de la gate prime. Migration vers 7.1 quand typescript-eslint la déclare. | HIGH |
| pnpm | **12.21.0** | Gestionnaire de paquets | Défauts supply-chain durcis (`minimumReleaseAge`, `blockExoticSubdeps`, `allowBuilds`), indispensable quand les dépendances sont ajoutées par des agents (§ Quality Gate). | MEDIUM (défauts pnpm 11/12 vus via sources secondaires ; vérifier au 1er install) |
| Zod | **4.6.7** | Schémas (I/O MCP, config, import, DTO) | Standard Schema ; peer du SDK MCP (`zod ^4.2`) ; une source de vérité pour `inputSchema`/`outputSchema`. | HIGH |
| Express | **5.3.0** | HTTP | Chemin documenté de bout en bout par le SDK MCP v2 (`@modelcontextprotocol/express`, `requireBearerAuth`, `mcpAuthMetadataRouter`) **et** par `oidc-provider` (`provider.callback()` montable). Le plus connu des agents IA. Hono/Fastify rejetés : aucun gain ici, intégration `oidc-provider` non documentée. | MEDIUM |
| tsdown | 0.23.7 | Build prod (bundle ESM) | Peer `typescript ^5 \|\| ^6 \|\| ^7`. Dev via `tsx` 4.23.15. | MEDIUM |

### 3.2 MCP

| Technology | Version | Purpose | Why | Conf. |
|---|---|---|---|---|
| `@modelcontextprotocol/server` | **2.4.0** | `McpServer`, `registerTool`, `createMcpHandler`, `requireBearerAuth`, `requireScopes` | SDK officiel v2 (stable depuis 2026-07-27) ; Standard Schema ; `outputSchema` + `structuredContent` ; v1 (`@modelcontextprotocol/sdk` 1.32.2) en maintenance seulement. | HIGH |
| `@modelcontextprotocol/express` | 2.0.2 | `createMcpExpressApp` (`allowedHosts` = DNS-rebinding), `mcpAuthMetadataRouter` | Doc v2 : passer `expectedResource` (versions ≥ 2.0.2 requises, 2.0.1 ne le propage pas). | HIGH |
| `@modelcontextprotocol/node` | 2.1.2 | `toNodeHandler(createMcpHandler(...))` | Pont Node http. | HIGH |
| `@modelcontextprotocol/ext-apps` | **2.0.4** | MCP Apps : `registerAppTool`, `registerAppResource`, `RESOURCE_MIME_TYPE`, côté UI `App` / `useApp` | Écrans déterministes servis par le serveur (saisie, tri d'import, tableau de bord) ; `callServerTool` depuis l'UI ; `ui.domain` Claude à calculer. | HIGH |
| `@modelcontextprotocol/client` | 2.4.0 (dev) | Tests de contrat in-process / e2e | Client officiel pour tester les outils sans passer par claude.ai. | HIGH |
| `@modelcontextprotocol/conformance` | 0.1.16 (dev) | Suite de conformité serveur | Très jeune (0.1.x) : advisory uniquement. | LOW |
| `@modelcontextprotocol/inspector` | 2.16.0 (dev) | `--cli` en e2e, validation du flux OAuth | Recommandé par la doc Claude pour tester hors claude.ai. | HIGH |
| Vite 8.3.8 + `vite-plugin-singlefile` 2.3.4 + React 19.3.1 | UI MCP Apps | Bundle HTML unique par écran, servi comme ressource `ui://`. | HIGH (doc ext-apps) |
- Tous les outils de lecture renvoient `content` (texte JSON lisible) **et** `structuredContent` validé par `outputSchema`. Le texte reste le canal que le modèle lit à coup sûr ; `structuredContent` alimente l'UI. (MEDIUM : la doc Claude ne détaille que texte/image pour le modèle.)
- Annotations d'outil (`readOnlyHint`, `destructiveHint`, `idempotentHint`) sur **chaque** outil, vérifiées par un test (les relecteurs du directory les attendent, et ça pilote les approbations côté Claude).
- L'identité vient de `ctx.http?.authInfo` (jeton vérifié), **jamais** d'un argument d'outil. Toute fonction applicative reçoit un `Principal` typé ; aucun handler n'accède directement à la base.
- Écritures : politique par membre et par type d'action = `PendingAction` créée par un outil `propose_*`, appliquée par `confirm_*`. Pas d'elicitation (non supportée par claude.ai).
- Montants en sortie : `amount_minor` (entier sûr) + `display` formaté côté serveur (« 84,00 € »). Claude ne calcule rien qui fasse foi.

### 3.3 Autorisation OAuth (serveur d'autorisation **embarqué**)

| Technology | Version | Purpose | Why | Conf. |
|---|---|---|---|---|
| `oidc-provider` (panva) | **9.15.1** | Serveur d'autorisation OAuth 2.1/OIDC dans le même process | Certifié OpenID ; `resourceIndicators` (RFC 8707, jetons JWT à audience MCP) ; PKCE S256 ; rotation de refresh ; `clientIdMetadataDocument` (CIMD -03) avec `allowFetch`/`allowClient` pour n'autoriser **que** claude.ai/claude.com ; DCR désactivable ; clients statiques via adapter. Dépend de koa 3 et jose. | HIGH (features) / MEDIUM (CIMD « experimental ») |
| `jose` | 6.2.18 | Vérification JWT côté resource server (`aud`, `iss`, `exp`, JWKS local) | Standard ; déjà dépendance d'`oidc-provider`. | HIGH |
| `@simplewebauthn/server` | 14.1.0 | Connexion par passkeys sur les pages d'interaction (login/consent) | Évite mots de passe et TOTP pour des membres non techniques ; enrôlement par lien d'invitation ; récupération = ré-invitation par l'admin. | MEDIUM |
- Issuer = `https://<hôte>` (sans chemin), RS à `https://<hôte>/mcp` ; PRM `/.well-known/oauth-protected-resource/mcp` + variante racine ; AS metadata sur `/.well-known/oauth-authorization-server` **et** `/.well-known/openid-configuration`. Annoncer `code_challenge_methods_supported: ["S256"]`, `token_endpoint_auth_methods_supported` contenant `"none"`, `client_id_metadata_document_supported: true`, `authorization_response_iss_parameter_supported: true` (RFC 9207, exigé côté client par la spec 2026-07-28).
- **DCR désactivé.** CIMD actif avec `allowFetch` limité aux hôtes `claude.ai` / `claude.com` ; en plus, un client statique public « claude-web » (redirect URIs `https://claude.ai/api/mcp/auth_callback` et `https://claude.com/api/mcp/auth_callback`) utilisable via « Use your own OAuth client ». L'URL exacte du CIMD d'Anthropic pour claude.ai n'est pas documentée : ne pas la coder en dur (restreindre par hôte, vérifier dans le spike). (LOW sur ce détail)
- Jetons d'accès JWT (RFC 9068) 10-15 min, `aud` = URL MCP canonique, refresh rotatif, scopes minimaux (`household:read`, `household:write`, `bank:link`, `admin`). `sub` = UUID de membre ; **le foyer, le rôle et les droits sont relus en base à chaque appel**, jamais lus dans le jeton.
- Stockage `oidc-provider` : adapter Postgres (table de payloads, consommation atomique recommandée par la doc).
- Premier admin : jeton d'amorçage à usage unique fourni par variable d'environnement (cf. ancien `runbooks/initial_admin_via_env.md`), invitations ensuite.
- Pages login/consent : HTML serveur minimal (pas de SPA). La consent affiche le **hostname** du `client_id` (pas `client_name`, auto-déclaré).

### 3.4 Base de données

| Technology | Version | Purpose | Why | Conf. |
|---|---|---|---|---|
| PostgreSQL | **18.7** (image `postgres:18.7-trixie`, épinglée par digest) | Base unique (domaine + OAuth + file de jobs + audit) | `uuidv7()` natif ; PostgreSQL 19 vient de sortir (2026-11-19) : ne pas démarrer un projet financier dessus, attendre 19.2+. | HIGH (versions) |
| `pg` | 8.23.1 | Driver | `types.setTypeParser(20, BigInt)` pour `bigint` → `bigint`. | HIGH |
| Kysely | **0.29.9** | Query builder typé SQL-first | Les invariants vivent en SQL (CHECK, triggers) ; le builder ne les masque pas. Pas d'ORM à magie. | MEDIUM |
| `kysely-codegen` | 0.20.0 | Types TS générés depuis le schéma réel | La base est la source de vérité ; le typage ne peut pas diverger des migrations. Généré en CI et diffé (`git diff --exit-code`). | MEDIUM |
| Migrations | `Migrator` de Kysely, **SQL brut, forward-only** | Évolution de schéma | Zéro dépendance supplémentaire ; pas de `down` (inutile en prod, source de bugs). Snapshot `pg_dump --schema-only` comparé en CI. | MEDIUM |
| `pg-boss` | 12.38.2 | File de jobs/cron dans Postgres (sync bancaire, récurrences, alertes budget, rappels de consentement) | Pas de Redis ; transactionnel avec les écritures métier. | MEDIUM |
- Montants : **`bigint` de centimes** (colonnes `bigint`, devise `char(3)` avec `CHECK (currency = 'EUR')` en v1 mais modèle multi-devise). Mélanger `bigint` et `number` lève en JS : un flottant glissé par un agent plante au lieu de corrompre silencieusement. Aucune lib décimale (decimal.js, big.js, dinero.js) : pas nécessaire pour des centimes entiers. Taux/quotes-parts : entiers en points de base ou ppm. Répartition (split 50/50, quotes-parts) : algorithme du plus grand reste, propriété `Σ parts = total` testée par fast-check.
- Parsing de montants (import) : fonction maison string → `bigint`, **jamais** `parseFloat`/`Number()`.
- Dates : `Temporal.PlainDate` (jour comptable, sans fuseau), `Temporal.Instant` pour les horodatages. Vérifier que les types `Temporal` sont présents dans la lib TS 6.0.3 ; sinon `@js-temporal/polyfill` 0.5.1 pour les types seulement (LOW, à vérifier).
- Identifiants : UUIDv7 générés par `uuidv7()` Postgres (ordre total `(date, id)` de la règle F10).

### 3.5 Agrégation bancaire (DSP2/PSD2, particulier en France)

| Option | Statut pour un particulier | Verdict | Conf. |
|---|---|---|---|
| **Enable Banking** | Mode « restricted production » : on enregistre une app *production* dans le Control Panel, on **lie ses propres comptes** (« Activate by linking accounts »), pas de contrat ni de KYB ; usage « individuel non commercial » ; seuls les comptes liés sont retournés ; CGU/politique de confidentialité non vérifiées dans ce mode. Gratuit pour ce mode (la tarification commerciale est au volume, sur devis). | **Retenu.** | HIGH (docs officielles) sur le mode ; MEDIUM sur « gratuit » (non chiffré explicitement) |
| GoCardless Bank Account Data (ex-Nordigen) | Une seule source (blog DEV, juillet 2026) dit que les nouvelles inscriptions sont fermées ; la page officielle `gocardless.com/bank-account-data` ne le confirme pas. | **Ne pas bâtir dessus.** | LOW |
| Powens (ex-Budget Insight) | Sandbox gratuit ; production « sur contrat/devis » ; rien trouvé sur l'accès particulier. | Écarté v1. | MEDIUM |
| Bridge (Bankin') | Production sous contrat ; accès particulier non vérifié. | Écarté. | MEDIUM |
| Tink (Visa), Yapily, Plaid | Entreprise / certificat eIDAS. | Écartés. | MEDIUM |

### 3.6 Import OFX / CSV

| Library | Version | Purpose | Notes | Conf. |
|---|---|---|---|---|
| `ofx-data-extractor` | 1.6.0 | OFX 1.x (SGML) et 2.x (XML), mode lenient avec `getWarnings()` | Actif (release 2026-11-15), MIT. Encodage non documenté : décoder soi-même (en-tête OFX `CHARSET`, UTF-8 strict puis windows-1252) et passer un `Buffer`/chaîne. Montants à traiter en **chaîne**, pas en nombre. | LOW-MEDIUM |
| `ofx-js` | 1.1.2 | Alternative minimaliste, zéro dépendance | Support SGML non confirmé dans la doc lue. | LOW |
| `csv-parse` | 7.0.3 | CSV bancaires | Profils par banque : séparateur `;`, `dd/mm/yyyy`, virgule décimale, ISO-8859-1/windows-1252. | MEDIUM |

### 3.7 Infrastructure et déploiement homelab

| Technology | Version | Purpose | Why | Conf. |
|---|---|---|---|---|
| Podman (rootless) + **Quadlet** | 6.2.0 | Conteneurs sous systemd | `.container`/`.network`/`.volume` versionnés dans le dépôt, redémarrage par systemd, pas de démon root. Images épinglées **par digest** ; mises à jour via Renovate (pas de `:latest` + `auto-update` aveugle). | MEDIUM |
| Conteneur app | Node 26 slim, utilisateur non-root, rootfs en lecture seule, `PublishPort=127.0.0.1:3000:3000` | 1 process : `/mcp`, OAuth, pages login, jobs pg-boss | Monolithe modulaire = 1 conteneur + Postgres. | HIGH |
| Tunnel : **Tailscale Funnel** (recommandé) | client ≥ 1.38.3 | URL publique HTTPS `*.ts.net` | TLS **terminé sur le nœud** : le relais Tailscale « ne peut pas déchiffrer » (doc officielle) ; important pour des données financières. Pas de domaine à acheter, URL stable. Limites : bêta, ports 443/8443/10000, bande passante non configurable (négligeable ici), pas de domaine custom, pas de WAF. | MEDIUM |
| Tunnel : Cloudflare Tunnel (`cloudflared` 2026.11.1) | | Alternative | Domaine custom, WAF/DDoS, conteneurisable. Contre : Cloudflare termine le TLS et voit les données en clair ; bot management/WAF à régler (règle d'exception pour `160.79.104.0/21` sur `/mcp`, `/token`, `/.well-known/*`, sinon 403/429). À prendre si Funnel s'avère instable ou si un domaine propre est voulu. | HIGH (comportement) |
| Reverse proxy (Caddy 2.11.9) | | **Supprimé du plan initial** | Un seul service derrière un tunnel qui termine déjà TLS : Caddy n'ajoute qu'un composant. L'app porte ses propres en-têtes (`helmet` 8.3.0), rate limiting (`express-rate-limit` 8.7.5) et `trust proxy`. À réintroduire si d'autres services partagent l'hôte. | MEDIUM |
| Sauvegardes | `pg_dump` quotidien (timer systemd) → dépôt chiffré hors site (restic/borg) ; **test de restauration** périodique | Données financières réelles | | MEDIUM (non recherché en détail) |

### 3.8 Bibliothèques de support

| Library | Version | Purpose | When to Use |
|---|---|---|---|
| `pino` | 10.4.0 | Logs JSON structurés | Toujours ; rédaction (`redact`) des jetons, IBAN, libellés bancaires. |
| `express-rate-limit` | 8.7.5 | Limitation par IP/jeton | `/token`, `/authorize`, `/mcp`. Mémoire locale suffisante (1 instance). |
| `helmet` | 8.3.0 | En-têtes de sécurité | Pages login/consent ; CSP stricte. |
| `@t3-oss/env-core` | 0.13.11 | Validation d'env au démarrage (zod) | Une seule porte d'entrée pour `process.env`. |
| `ts-pattern` | 5.9.2 | Matching exhaustif sur états/unions | États de transaction, résultats de rapprochement (AI-friendly : oublis détectés à la compilation). |
| `msw` | 3.0.7 | Mock HTTP de l'agrégateur en tests | Enable Banking, CIMD claude.ai. |
| `testcontainers` + `@testcontainers/postgresql` | 12.2.2 | PostgreSQL 18 réel en tests d'intégration | Une base par worker, `CREATE DATABASE … TEMPLATE` par fichier de test. **Pas PGlite** : connexion unique, version PG non confirmée, comportement RLS/triggers à ne pas parier. |

## 4. Development Tools

| Tool | Version | Purpose | Notes |
|---|---|---|---|
| Vitest | 5.1.1 (+ `@vitest/coverage-v8` 5.1.1) | Tests | `passWithNoTests: false`, `allowOnly: false` en CI. |
| fast-check | 4.10.3 (+ `@fast-check/vitest` 0.5.0) | Property-based, model-based | Voir § Quality Gate. |
| ESLint | 10.15.0 | Lint (type-aware) | Avec `typescript-eslint` 8.73.0 + TS 6.0.3. |
| Biome | 2.6.8 | **Formateur uniquement** | Évite le double-lint avec ESLint. |
| lefthook | 2.2.2 | Hooks git (pré-commit/pré-push) | Un binaire, config YAML versionnée. |
| Renovate | 44.257.6 | Mises à jour avec `minimumReleaseAge` | Regroupe les patches, jamais d'auto-merge sur les dépendances de prod. |

## 5. Installation

# Prérequis : Node 26 LTS, pnpm 12, Podman 6, PostgreSQL 18 (conteneur)

# Runtime

# UI MCP Apps (workspace séparé "ui/")

# Dev / qualité (voir § Quality Gate pour la liste complète)

# Binaires hors npm (CI + poste) : gitleaks 8.30.1, osv-scanner 2.7.1, semgrep 1.186.0 (pip/pipx), actionlint 1.7.12,

# zizmor 1.32.0, hadolint 2.15.1

## 6. Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|---|---|---|
| TypeScript + SDK `@modelcontextprotocol/server` 2.4.0 | Python 3.13 + `mcp` 2.3.0 (`MCPServer`) ou FastMCP 4.2.4 | Si OFX/CSV est le risque n°1 et qu'on n'utilise pas MCP Apps. FastMCP 4.2.4 (`fastmcp[apps]`) couvre aussi les UI mais pas le bundle JS. Les deux SDK Python sont resource-server only. |
| `oidc-provider` embarqué | Keycloak 26.6+ (CIMD *expérimental* `--features=cimd`, DCR) | Si le foyer exploite déjà un IdP central. ~1 Go de RAM et un mapping membre↔compte en plus. |
| `oidc-provider` embarqué | Authentik 2026.8 (DCR annoncé ; une source dit réservé à l'édition entreprise, CIMD non implémenté), Zitadel (DCR désactivé par défaut, CIMD en PR #12316), Pocket ID (aucune info DCR/CIMD trouvée) | Seulement avec le mode « Use your own OAuth client » (client pré-enregistré, sans DCR ni CIMD), saisi par chaque membre dans claude.ai. |
| Kysely + SQL | Drizzle ORM 0.45.4 (stable) / 1.0 RC | Drizzle 1.0 est encore RC ; un ORM de plus masque les contraintes SQL qui portent les invariants. Prisma : pas de contraintes avancées/RLS naturelles. |
| Express 5 | Hono 4.13 / Fastify 5.12 | Si le serveur devait tourner en edge/workers (non, c'est un homelab). |
| ESLint 10 + typescript-eslint (TS 6.0.3) | oxlint 1.94 + `oxlint-tsgolint` 7 (TS 7, type-aware stable, 59/61 règles, 12-18x plus rapide) | À la migration TS 7.1 : l'écosystème de plugins ESLint (sonarjs, vitest, comments) y est plus riche aujourd'hui ; les JS plugins d'oxlint sont encore alpha. |
| Tailscale Funnel | Cloudflare Tunnel | Voir § 3.7. |
| Enable Banking | GoCardless BAD, Powens, Bridge | Si un contrat professionnel devient envisageable (Powens/Bridge). |
| pg-boss | BullMQ + Redis, `graphile-worker` 0.18 | Redis inutile ; graphile-worker est un bon second choix. |

## 7. What NOT to Use

| Avoid | Why | Use Instead |
|---|---|---|
| DCR ouvert sur un endpoint public | Chaque connexion Claude enregistre un client ; surface d'abus ; la spec 2026-07-28 déprécie DCR | CIMD restreint aux hôtes claude.ai/claude.com + client statique |
| Spec MCP 2026-07-28 seule (mode stateless modern-only) | claude.ai suit 2025-03-26/06-18/11-25 | `createMcpHandler` en `legacy: 'stateless'` (défaut) |
| Jetons non liés à l'audience / passthrough d'un jeton tiers | Interdit par la spec (« MUST NOT accept or transit any other tokens ») | JWT avec `aud` = URL MCP, `expectedResource` |
| `Number`/flottants pour l'argent, `Date` pour les jours comptables | Erreurs d'arrondi, fuseaux | `bigint` de centimes, `Temporal.PlainDate` |
| PostgreSQL 19.0 | Sorti il y a 2 jours, cycle de bêta chahuté | PostgreSQL 18.7 |
| PGlite pour les tests d'intégration | Connexion unique exclusive, version PG non précisée | Testcontainers PG 18 |
| Trivy non épinglé | Compromission de la supply chain (mars 2026 : tags `trivy-action` réécrits, binaires 0.69.4-0.69.6 malveillants) | `osv-scanner` pour lockfile et images ; si Trivy : version et action épinglées par SHA/digest, advisory |
| `typescript` 7.0.x pour l'instant | Casse typescript-eslint, dependency-cruiser ; Stryker expérimental | TS 6.0.3 puis 7.1+ |
| `ofxparse` / `ofx` (npm 0.5.0, 2020) | Abandonnés | `ofx-data-extractor` derrière un port, ou parseur maison |
| Redis, Caddy, broker de messages, Keycloak | Composants en plus pour un foyer | Postgres + pg-boss, tunnel, `oidc-provider` |
| Agent qui peut éditer sa propre gate | Les agents affaiblissent les tests et les seuils pour passer au vert | § Quality Gate, protection des chemins |

## 8. Stack Patterns by Variant

## 9. Spikes à réaliser avant/pendant la phase 1 (garde-fous de décision)

## 10. Quality Gate pour code écrit par des agents IA

### 10.1 Principes (ce qui change par rapport à l'ancien dépôt)

| Faiblesse ancienne gate | Amélioration prescrite |
|---|---|
| Couverture `advisory` sans seuil ; mutation **hors gate** | Couverture **plancher bloquant** + **mutation bloquante sur le noyau de domaine pur** (rapide car sans I/O) en incrémental sur le diff ; complet en nightly |
| Filet escape-hatches « dans les linters » mais `# noqa: <code>` libre, relu « en review » | Dérogations **avec description obligatoire**, `reportUnusedDisableDirectives`, `as` interdit, **compteur d'échappatoires à cliquet** (ne peut que baisser) |
| Rien ne protégeait tests/CI/config contre l'agent qui les affaiblit | Chemins protégés (CODEOWNERS + deny d'édition agent + job d'intégrité de la gate + seuils à cliquet) |
| `deptry` joué par la gate seule, pas par la CI ; CI path-scopée complexe | Une commande unique `pnpm quality` identique en pré-push et CI ; CI = juge, pas de path-scoping (dépôt mono-stack petit : tout rejouer) |

### 10.2 Tableau de la gate

| Check | Outil | Version | Sévérité | Pourquoi pour du code généré par IA | Où |
|---|---|---|---|---|---|
| Typage strict | `tsc --noEmit` (TypeScript) | 6.0.3 | **Blocking** | Flags : `strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `noImplicitOverride`, `noFallthroughCasesInSwitch`, `noUnusedLocals/Parameters`, `noPropertyAccessFromIndexSignature`, `verbatimModuleSyntax`, `erasableSyntaxOnly`. Les IA « font passer » le typage avec `any`/`as` : tout le reste du tableau ferme ces portes. | PP, CI |
| Lint type-aware | ESLint + typescript-eslint `strictTypeChecked` + `stylisticTypeChecked` (`projectService`) | 10.15.0 / 8.73.0 | **Blocking**, `--max-warnings 0` | `no-floating-promises`, `no-misused-promises`, `no-unsafe-*`, `switch-exhaustiveness-check`, `no-unnecessary-condition`, `strict-boolean-expressions` attrapent les promesses oubliées et les `any` qui fuient (premier défaut des agents). | PC (fichiers stagés, `--cache`), CI |
| Assertions de type interdites | `@typescript-eslint/consistent-type-assertions` `{ assertionStyle: 'never' }` (sauf `as const`) + `no-non-null-assertion` + `no-explicit-any` + `ban-ts-comment` | idem | **Blocking** | Les agents cast au lieu de valider. Forcer `zod.parse`/type guards aux frontières. | PC, CI |
| Formatage | Biome (formatter seul) | 2.6.8 | **Blocking** (`--check`) | Supprime le bruit de diff ; fix automatique en PC. | PC, CI |
| Complexité | `sonarjs/cognitive-complexity` ≤ 10 ; ESLint `max-lines-per-function` 60, `max-depth` 3, `max-params` 4, `max-lines` 300 | eslint-plugin-sonarjs 4.2.2 | **Blocking** | Les agents génèrent des fonctions longues et imbriquées ; seuil dès le jour 1 sur un dépôt vierge (l'ancienne gate avait le cyclomatique ≤ 10 seulement via Ruff C901). | CI |
| Règles domaine sur mesure | ESLint `no-restricted-syntax`/`no-restricted-globals` (via `eslint.config`) : interdire `parseFloat`, `Number(` hors DTO, `Math.round` dans `domain/**`, `Date`/`Date.now` hors `Clock`, `console.*`, `process.env` hors `config/`, `sql.raw` | — | **Blocking** | Encode les invariants du domaine (pas de flottant sur l'argent, pas d'horloge ambiante) que l'agent ignore sinon. | CI |
| Hygiène des directives | `@eslint-community/eslint-plugin-eslint-comments` `require-description`, `no-unlimited-disable`, `no-unused-disable`, `disable-enable-pair` + `reportUnusedDisableDirectives: "error"` | 4.8.1 | **Blocking** | Une désactivation de règle doit se justifier par écrit et ne jamais devenir morte. Remplace `PGH004`/`RUF100` de l'ancienne gate. | CI |
| Check | Outil | Version | Sévérité | Pourquoi pour du code IA | Où |
|---|---|---|---|---|---|
| Contrats d'import (couches, modules, surface publique) | `dependency-cruiser` (parser `tsc`) | 18.8.0 | **Blocking** | Équivalent d'`import-linter`. Règles : `domain` n'importe que `domain`/`shared` ; `application` → `domain` ; `adapters` (db, http, aggregator) → `application` ; module A n'accède à B que par `B/public.ts` ; **les outils MCP n'importent jamais `adapters/db`** (autorisation par construction) ; pas de cycle ; pas de dépendance `dev` dans `src` ; `pg`/`fs`/`fetch` interdits dans `domain`. Les agents prennent le raccourci d'importer ce qui est à portée. | PP, CI |
| Code mort, exports/fichiers/dépendances inutilisés, dépendances non listées | `knip` | 6.47.0 | **Blocking** (config sans `ignore` fourre-tout) | Les agents laissent des fonctions orphelines et des paquets ajoutés puis non utilisés ; knip couvre aussi le rôle de `deptry`/`vulture`. | CI |
| Duplication | `jscpd` (`--baseline-from-ref origin/main --fail-on-new-clones`, hors tests) | 5.4.3 | **Blocking** sur nouveaux clones `src/` ; advisory sur `tests/` | Les agents copient-collent plutôt que d'extraire. | CI |
| Dépendances : paquet nouveau | Script de diff de lockfile : liste les ajouts, vérifie âge (> 30 j) et existence sur npm ; **label humain `deps-approved` requis** (CODEOWNERS sur `package.json`/`pnpm-lock.yaml`) | script maison | **Blocking** | Les LLM hallucinent des noms de paquets (slopsquatting) et ajoutent des deps sans les mesurer. | CI |
| Politique supply-chain | pnpm `minimumReleaseAge` ≥ 7 j, `blockExoticSubdeps`, `allowBuilds` explicite, `trustPolicy: no-downgrade`, `pnpm install --frozen-lockfile` | pnpm 12.21.0 | **Blocking** | Un agent n'installe pas un paquet publié il y a 2 h ni un script `postinstall` non approuvé. | install, CI |
| Check | Outil | Version | Sévérité | Pourquoi pour du code IA | Où |
|---|---|---|---|---|---|
| Secrets | `gitleaks` (stagé en PC, historique complet en CI) | 8.30.1 | **Blocking** | Les agents collent des clés/jetons dans fixtures, `.env.example`, logs. | PC, CI |
| Secrets vérifiés (nightly) | `trufflehog` | 3.100.0 | Advisory | Second avis avec vérification de validité des secrets. | N |
| SAST + règles locales | `semgrep` CE (`p/typescript`, `p/nodejs`, `p/jwt`, `p/owasp-top-ten`) + **règles du projet** : handler d'outil sans `Principal`, concaténation SQL, `sql.raw`, `any` dans `adapters/http`, `Math.random` pour un jeton, comparaison non constante de secrets | 1.186.0 | **Blocking** (sévérité ERROR) ; advisory le reste | Les règles locales encodent « autorisation par construction » : la faille la plus probable d'un agent est un outil qui oublie le filtre de membre. | CI, N (jeu complet) |
| Lint sécurité JS | `eslint-plugin-security` | 4.2.1 | **Advisory** (bruyant) | Signaux faibles (regex, `eval`, objets dynamiques). | CI |
| CVE des dépendances | `osv-scanner` sur `pnpm-lock.yaml` | 2.7.1 | **Blocking** high/critical ; advisory sinon | Les agents figent des versions anciennes de mémoire d'entraînement. Complété par `pnpm audit --prod`. | CI, N |
| Image conteneur | `osv-scanner` (image) ; `hadolint` sur le Containerfile | 2.7.1 / 2.15.1 | hadolint **Blocking** ; scan image **advisory** | Images non épinglées, root, secrets dans les couches. Trivy : seulement épinglé par SHA, advisory. | CI, N |
| Workflows CI | `actionlint` + `zizmor` ; actions épinglées par **SHA complet** | 1.7.12 / 1.32.0 | **Blocking** | Un agent écrit des workflows avec `pull_request_target`, permissions larges ou tags flottants (cf. incident Trivy). | PC (fichiers workflow), CI |
| SBOM | `syft` | 1.57.2 | Advisory | Traçabilité de l'image publiée. | release |
| Check | Outil | Version | Sévérité | Pourquoi pour du code IA | Où |
|---|---|---|---|---|---|
| Tests unitaires/intégration | Vitest | 5.1.1 | **Blocking** | PG 18 **réel** (Testcontainers), pas de mock de la base : un mock de repository écrit par l'agent prouve seulement que l'agent s'est mocké. | PP (`vitest related`), CI |
| Propriétés du domaine | fast-check + `@fast-check/vitest` ; `numRuns` 100 en CI, 1000+ en nightly ; seeds de régression commitées | 4.10.3 / 0.5.0 | **Blocking** | Les agents écrivent des tests par exemples qui épousent l'implémentation. Invariants à tester : Σ parts = total (plus grand reste) ; Σ splits = 0 ; solde de dette = montant − Σ règlements ; `void` + nouvelle transaction = effet net attendu ; ordre total `(date, id)` stable ; import idempotent (même fichier 2× = 0 changement) ; budget restant R borné ; projection incrémentale = rejouée. **Model-based** (`fc.commands`) pour le cycle de vie des transactions et des règlements. | CI, N |
| Invariants en base et cloisonnement | Tests d'intégration auto-générés : trigger zero-sum, immutabilité `confirmed`, **chaque table à `owner_member_id` a RLS actif**, membre B ne lit jamais les données perso de A (même admin) | Vitest + PG | **Blocking** | Le cloisonnement est l'exigence non négociable ; un test méta empêche l'oubli sur une future table. | CI |
| Contrat MCP | Snapshot de `tools/list` (noms, descriptions, `inputSchema`, `outputSchema`, annotations) committé et **relu par un humain** à chaque diff ; chaque outil : annotations présentes, sortie valide son `outputSchema`, refus sans jeton = HTTP 401 | Vitest + `@modelcontextprotocol/client` 2.4.0 | **Blocking** | Les agents changent la surface publique sans le dire ; un renommage d'outil casse les conversations existantes. | CI |
| Flux OAuth e2e | Client scripté rejouant 401 → PRM → AS metadata → CIMD → authorize → token → refresh rotatif → `/mcp`, dans un conteneur construit | Vitest + Inspector 2.16.0 `--cli` | **Blocking** (PR touchant auth/déploiement), sinon N | C'est l'endroit où les erreurs sont silencieuses côté Claude (« Couldn't reach the MCP server »). | CI, N |
| Conformité MCP | `@modelcontextprotocol/conformance` | 0.1.16 | **Advisory** | Très jeune. | N |
| **Mutation testing** | StrykerJS (`vitest-runner`, `typescript-checker`, `coverageAnalysis: perTest`) ; périmètre `src/domain/**` et `src/application/**` purs | 10.1.1 | **Blocking** sur les fichiers modifiés (`--since origin/main`, `thresholds.break` 80) ; **N** complet (seuil 75-80) ; advisory ailleurs | Seul contrôle réel de la force des tests écrits par un agent : couverture à 100 % avec assertions faibles est la norme IA. Coût maîtrisé parce que le noyau pur n'a pas d'I/O. **Ne pas** committer le fichier d'incrémental : bug ouvert #6004 (IDs de tests non déterministes avec vitest-runner). | CI (diff), N |
| Couverture | `@vitest/coverage-v8` : seuils par glob : `src/domain/**` 100 % lignes+branches ; global 85 % lignes / 80 % branches ; **cliquet** : jamais inférieur à `main` | 5.1.1 | **Blocking** | Plancher, pas objectif (un agent gonfle la couverture sans assertions) ; c'est la mutation qui juge la qualité. | CI |
| Qualité des tests (lint) | `@vitest/eslint-plugin` : `expect-expect`, `no-disabled-tests`, `no-focused-tests`, `no-conditional-expect`, `no-conditional-tests`, `valid-expect`, `no-identical-title`, `no-commented-out-tests`, `no-restricted-matchers` (`toBeTruthy`, `toBeDefined`, `toBeFalsy`, `toMatchSnapshot` sur le domaine), `require-to-throw-message` | 1.6.28 | **Blocking** | Détecte tests sans assertion, `.skip`, `.only`, assertions creuses : les 3 façons de « verdir » d'un agent. `no-unsafe-*` **non assouplis** dans les tests. | CI |
| Ordre aléatoire des tests | Vitest `sequence.shuffle` + seed loguée | 5.1.1 | **Blocking** | Révèle les tests dépendants de l'état partagé. | CI |
| Check | Outil | Version | Sévérité | Pourquoi | Où |
|---|---|---|---|---|---|
| Compteur d'échappatoires **à cliquet** | Script : compte `@ts-ignore`, `@ts-expect-error`, `@ts-nocheck`, `eslint-disable`, `biome-ignore`, `as any`, `as unknown as`, `!.`, `.skip`, `.todo`, `vi.mock(` ; compare à `quality/baseline.json` ; ne peut **que baisser** | script maison (+ `git grep`) | **Blocking** | Remplace le grep de `scd-spec-dev` (rouge permanent en brownfield) : ici projet vierge, budget initial 0, tout ajout doit être justifié par un humain. | PC, CI |
| Intégrité de la gate | Job CI qui échoue si le diff touche les chemins protégés (ci-dessous) sans label humain `gate-change-approved` ; vérifie que `quality/baseline.json` n'a que des seuils **plus stricts** et que `coverage.thresholds`, `stryker.thresholds.break`, `--max-warnings` n'ont pas baissé | script maison | **Blocking** | Le réflexe d'un agent bloqué est de baisser un seuil, d'ajouter un `ignore` ou de supprimer un test. | CI |
| Pas de `--no-verify` | Règle de permissions de l'agent (`Bash(git commit --no-verify*)`, `Bash(git push --force*)` refusés) + CI serveur comme seul juge | config Claude Code | **Blocking** (côté agent) | Les hooks locaux sont contournables : la CI est la vérité. | agent |
| Un seul point d'entrée | `pnpm quality` (lint + types + arch + knip + jscpd + tests + gitleaks + semgrep) avec sortie JSON agrégée `reports/gate.json` (`{check, tool, version, severity, passed, issues[]}`) | script maison | **Blocking** | L'agent doit lancer exactement ce que joue la CI ; JSON/SARIF lisible par agent (ESLint `--format json`, depcruise `--output-type json`, knip `--reporter json`, jscpd `json`, Stryker `json`, Semgrep `--sarif`). | PP, CI |

### 10.3 Chemins protégés (agent en lecture seule)

### 10.4 Répartition pré-commit / pré-push / CI / nightly

| Étape | Budget | Contenu |
|---|---|---|
| **Pré-commit** (lefthook, fichiers stagés) | ≤ 10 s | Biome format (écrit), ESLint `--cache` sur stagés, gitleaks stagé, actionlint si workflow, refus d'édition de chemins protégés sans variable d'autorisation, compteur d'échappatoires |
| **Pré-push** | ≤ 60 s | `tsc --noEmit`, dependency-cruiser, knip, `vitest related` |
| **CI pull request** (juge) | ≤ 8-10 min | Tout `pnpm quality` + Stryker sur diff du domaine + gitleaks historique + Semgrep + osv-scanner + hadolint + actionlint/zizmor + e2e OAuth si auth/déploiement touchés. **Pas de path-scoping** (dépôt mono-stack petit : un faux « vert par skip » coûte plus cher que les minutes gagnées). Un seul check requis `quality`. |
| **Nightly** | libre | Stryker complet, fast-check 1000+ runs, Semgrep jeu complet, osv-scanner complet + image, trufflehog, conformance MCP, test de restauration de sauvegarde, e2e flux OAuth sur l'image publiée |

### 10.5 Stratégie de test (ordre de fiabilité décroissante)

## 11. Version Compatibility

| Package A | Compatible With | Notes |
|---|---|---|
| typescript **6.0.3** | typescript-eslint 8.73.0 (`<6.1.0`), dependency-cruiser 18.8.0 (`<7.0.0`), Stryker typescript-checker 10.1.1 (`>=3.6`) | TS 7.0.x exclu par dependency-cruiser et typescript-eslint ; 7.1+ attendu pour la migration |
| ESLint 10.15.0 | typescript-eslint 8.73.0, eslint-plugin-sonarjs 4.2.2, `@vitest/eslint-plugin` 1.6.28, eslint-comments 4.8.1 | `eslint-plugin-vitest` 0.5.4 plafonne à ESLint ≤ 9 : utiliser `@vitest/eslint-plugin` |
| `@modelcontextprotocol/server` 2.4.0 | `@modelcontextprotocol/express` ≥ 2.0.2 (peer `server ^2.3.0`), zod ^4.2 | 2.0.1 ne propage pas `expectedResource` (audience non vérifiée) |
| `@modelcontextprotocol/ext-apps` 2.0.4 | `server`/`client` ^2.0.0, zod ^4.2, React 17-19 | Hash `ui.domain` calculé sur l'URL exacte |
| Vitest 5.1.1 | `@stryker-mutator/vitest-runner` 10.1.1 (`vitest >=2`) | Compat Vitest 5 non confirmée par une source (LOW) : vérifier dans le spike de mutation |
| Node 26 LTS | Vitest 5 (`^22.12 \|\| ^24 \|\| >=26`), Kysely (`>=22`), Stryker (`>=22`), Inspector 2.16 (`>=26.12.1`) | |
| `kysely-codegen` 0.20.0 | `pg` 8.x, Kysely ≥ 0.27 <1 | |
| PostgreSQL 18.7 | `pg` 8.23.1, pg-boss 12.38.2 | pg-boss crée son schéma `pgboss` : l'inclure dans les rôles/RLS |

## 12. Sources

- Spec MCP 2026-07-28 : `modelcontextprotocol.io/specification/2026-07-28/changelog` et `/basic/authorization` — HIGH (officiel, lu en entier)
- Exigences claude.ai : `claude.com/docs/connectors/building/index.md`, `/authentication.md`, `/lazy-authentication.md`, `/testing.md`, `/troubleshooting.md`, `/mcp-apps/getting-started.md`, `/mcp-apps/troubleshooting.md`, `claude.com/docs/connectors/custom/add-unlisted.md`, `claude.com/docs/connectors/mcp-tunnels/oauth.md` — HIGH (officiel, lus en entier)
- SDK TS v2 : `ts.sdk.modelcontextprotocol.io/v2/` (pages `serving/authorization`, `protocol-versions`), registre npm — HIGH ; SDK Python v2 : `py.sdk.modelcontextprotocol.io` (pages `run/authorization`, `protocol-versions`), PyPI — HIGH
- MCP Apps : `apps.extensions.modelcontextprotocol.io/api/documents/Quickstart.html`, `@modelcontextprotocol/ext-apps` 2.0.4 — HIGH
- `oidc-provider` : `docs/README.md` et `CHANGELOG.md` sur GitHub (features `clientIdMetadataDocument`, `registration`, `resourceIndicators`), README (certification) — HIGH
- IdP tiers (Keycloak CIMD expérimental 26.6+, Authentik DCR 2026.8 / conflit entreprise, Zitadel DCR désactivé par défaut) — MEDIUM (recherche web, non recoupée sur les sites officiels) ; Pocket ID — aucune info
- Enable Banking : `enablebanking.com/docs/api/reference/`, `/docs/api/linked-accounts/`, `/docs/faq`, `/docs/api/quick-start/` — HIGH (mode restreint, JWT, consentement, limite 4/jour) ; France/banques du foyer : non confirmé
- GoCardless BAD fermé aux nouveaux comptes : blog DEV Community juillet 2026 — LOW ; Powens/Bridge sur contrat : issue GitHub tierce et annuaires — MEDIUM/LOW
- Tailscale Funnel : `tailscale.com/docs/features/tailscale-funnel` — HIGH ; Cloudflare/WAF : docs de troubleshooting Claude — HIGH
- TypeScript 7 / outillage : `oxc.rs/blog/2026-07-22-type-aware-linting-stable`, `registry.npmjs.org` (`supportedTranspilers` de dependency-cruiser, peers de typescript-eslint), annonce TS 7.0 — HIGH sur les peers, MEDIUM sur le reste
- Stryker : issue #6004 (ouverte, mai 2026), docs vitest-runner — MEDIUM ; Trivy supply-chain (Aqua Security, Snyk, Wiz, mars 2026) — HIGH sur l'existence de l'incident
- pnpm supply-chain (`pnpm.io/supply-chain-security`) — MEDIUM ; PostgreSQL 19 sorti le 2026-11-19 (postgresql.org) — HIGH
- Ancien dépôt : `origin/main:docs/ci.md`, `runbooks/ci.md`, `pyproject.toml`, `.importlinter`, `.pre-commit-config.yaml`, `.claude/quality.json`, `docs/recherches/2026-09-12-quality-gate-sonar-sans-serveur.md` — référence interne

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-fast` for a trivial task inline, with no subagents and no PLAN.md
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
