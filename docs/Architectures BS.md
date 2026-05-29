# Architecture — Application Finances Personnelles

> Version post-grilling consolidée
> **Date** : 2026-05-24
> **Statut** : Décisions tranchées, prêt pour implémentation
> **Docs liés** : [`CONTEXT.md`](../CONTEXT.md) (glossaire de domaine), [`docs/adr/`](./adr/) (14 ADRs), [`Sans titre.md`](./Sans%20titre.md) (spec produit), [`Stratégie de tests.md`](./Strat%C3%A9gie%20de%20tests.md)
> **Archive** : [`archive/Architectures BS.md`](./archive/Architectures%20BS.md) (version exploratoire pré-grilling, mai 2026)

---

## 1. Contexte

Application personnelle de gestion de finances pour un foyer (multi-utilisateurs adultes), auto-hébergée, durée de vie cible 5 ans, développée en solo avec assistance Claude Code intensive.

**Stack technique de référence** (figée) :

- **Frontend** : Capacitor 8 + React 19 + TypeScript + Vite 6 + Drizzle ORM + Tailwind + shadcn/ui + PowerSync Web/Capacitor SDK
- **Backend** : FastAPI (Python 3.13) + SQLAlchemy 2 async + Alembic + Pydantic v2 + pwdlib (Argon2id) + APScheduler
- **Données** : PostgreSQL 17 + pgcrypto + PowerSync Service (Open Edition)
- **Infrastructure** : Podman/Quadlet + Caddy + Cloudflare Tunnel + Tailscale + Restic→B2

**Contraintes spécifiques** :

- Domaine financier à invariants stricts (double-entrée, devises, intégrité comptable)
- Dépendance externe risquée (Enable Banking, free tier non garanti contractuellement)
- Solo dev → pas de budget pour de l'architecture cargo-cult
- Workflow Claude Code → la structure des fichiers est elle-même un livrable, et la suite de tests est le filet de sécurité principal face au refactoring assisté

---

## 2. Principe directeur

> **L'architecture suffisante** : ni layered naïf qui finit en god service à 18 mois, ni hexagonal cargo-cult qui coûte trois fois plus à écrire pour les CRUD.
>
> Le coût se paie dans les **mappings entre couches**. On en met là où il y a des invariants à protéger. On n'en met pas ailleurs.

Cet arbitrage est matérialisé par le découpage en modules (§4), la règle d'imports directionnelle (§5, ADR 0005), et la séparation entre intentions utilisateur (écritures côté client) et projections serveur (cf. ADR 0002).

---

## 3. Périmètre fonctionnel

Voir [`Sans titre.md`](./Sans%20titre.md) pour la spec produit complète. Synthèse de la complexité par feature :

| Feature | Complexité métier | Module porteur |
|---|---|---|
| F01 Auth multi-utilisateur + PAT + 2FA + invitation | Moyenne | `auth` (+ `mcp` pour heuristiques PAT) |
| F02 Comptes personnels + communs + quote-parts | Moyenne | `accounts` |
| F03 Droits + admin + audit | Moyenne | `auth` (RBAC) |
| F04 Import OFX + Enable Banking | Moyenne | `banking` |
| F05 Transactions locales | Faible | `transactions` |
| F06 Récurrences | Moyenne | `transactions` (rules) + génération serveur (`sync`/job) |
| F07 Pointage local ↔ bancaire | **Élevée** | `reconciliation` |
| F08 Budgets hiérarchiques | Faible | `budget` |
| F09 Dettes croisées | **Élevée** | `debts` |
| F10 Dettes par overflow budgétaire | **Élevée** | `debts` |
| F11 Dashboard multi-soldes | **Élevée** | `forecasting` (+ lecture transverse) |
| F12 Épargne avec objectifs | Moyenne | `savings` |
| F13 Notifications multi-canal + SSE | Faible (cf. ADR 0012) | `notifications` |
| F14 MCP server (read-only V1, write V2) | **Élevée** | `mcp` |

**Constat** : 5 features en complexité élevée → investissement architectural ciblé sur les modules concernés (`reconciliation`, `debts`, `forecasting`, `mcp`). Les autres restent en CRUD enrichis layered.

---

## 4. Découpage en modules

Modular Monolith avec graphe directionnel acyclique. Chaque module expose une **public surface** (`public.py`) qui ré-exporte les types et fonctions destinés à un usage cross-module ; les internals (`service.py`, `models.py`, `domain.py`, `repository.py`) sont privés.

```
backend/
  shared/
    money.py              # Value object Pydantic (cf. ADR 0008)
    currency.py
    events.py             # mini-bus in-process synchrone (cf. ADR 0005)
  modules/
    auth/                 # users, sessions, JWT, refresh, PAT entity, 2FA TOTP (ADR 0013)
    accounts/             # comptes personnel/commun, quote-parts, household singleton (ADR 0010)
    transactions/         # + domain.py : Transaction aggregate immutable (ADR 0001), splits
    budget/               # CRUD enrichi, hiérarchie catégories
    banking/              # + domain.py : BankingProvider/BankingReader split (ADR 0009)
    reconciliation/       # + domain.py : Reconciliation entité distincte (ADR 0006), MatchScorer
    debts/                # + domain.py : DebtCalculator pur, Settlement multi-line (ADR 0011)
    forecasting/          # + service.py riche : projection multi-soldes, forecast_with_recurrings
    savings/              # + domain.py léger : ProjectionCalculator épargne
    notifications/        # + domain.py : channels Email/Push/InApp/SSE, dispatcher (ADR 0012)
    sync/                 # + write upload handler PowerSync (ADR 0014)
    mcp/                  # + domain.py : PendingAction, ActionLineage, heuristiques (ADR 0004)
  config.py               # pydantic-settings
  alembic/
  tests/
```

> **Note RBAC** : les Depends FastAPI cross-module `require_admin` / `require_member` ne vivent **pas** dans `shared/` mais dans `auth/transports/dependencies.py`, re-exposés via `auth.public` (comme `get_current_user`). Le contrat import-linter #3 interdit `shared → modules.*`, or ces Depends dépendent de `get_current_user` (module `auth`). Cf. E04 §S04.1.

**Règle de modulation** :

| Module | A un `domain.py` riche ? | Justification |
|---|---|---|
| `transactions` | Oui | Aggregate immutable, double-entrée, splits, Money |
| `reconciliation` | Oui | State machine, MatchScorer, algo de matching |
| `debts` | Oui | DebtCalculator pur, Settlement multi-line, invariant zero-sum |
| `forecasting` | Service riche | Projection multi-soldes, calcul à la volée des récurrences |
| `banking` | Protocols + impls | Provider/Reader split, exceptions typées |
| `notifications` | Domain léger | Channels Protocol, dispatcher, matrice préférences |
| `mcp` | Oui | PendingAction immutable, audit lineage, heuristiques compromission |
| `sync` | Léger mais central | Write upload handler avec séquence stricte |
| `auth`, `accounts`, `budget`, `savings` | Non (savings : `ProjectionCalculator` léger) | CRUD enrichis layered, pas d'invariants à protéger |

**Pas de** : `application/` séparé, mappers systématiques DTO↔domain↔ORM, ABC formelles partout, CQRS, event sourcing distribué.

---

## 5. Graphe d'imports directionnel (ADR 0005)

```
                              mcp
                               │
                             sync
        ┌──────────┬──────────┬┴─────────┬────────────┐
        │          │          │          │            │
   reconciliation forecasting debts    notifications
        │          │          │
        ├──────────┴──┬───────┘
        │             │
    banking      transactions ── budget
                     │              │
                     └──── accounts ┘
                              │
                            auth
                              │
                           shared/
```

**Règles d'imports** (vérifiées par `import-linter`, cf. [Stratégie de tests.md §4.3](./Strat%C3%A9gie%20de%20tests.md#43-tests-darchitecture-import-linter)) :

- `shared/` n'importe rien des modules ; tous les modules peuvent l'importer.
- Chaque module n'expose qu'un `public.py` cross-module. Les internals (`service.py`, `models.py`, `domain.py`, `repository.py`) sont interdits à l'import cross-module.
- Un module ne peut importer que des modules **strictement en-dessous** dans le graphe.
- Le mini-bus `shared/events.py` permet à un module en-dessous (ex. `budget`) de publier un `DomainEvent` qu'un module au-dessus (`notifications`) consomme — sans inverser le graphe.
- Cas particulier `banking` : seul `modules/banking/service/polling.py` peut importer `BankingProvider` (le client Enable Banking). Tous les autres consommateurs cross-module passent par `BankingReader` (lecture cache, cf. ADR 0009).

---

## 6. Modèle de données et invariants

### Aggregate immutable (ADR 0001)

`Transaction` est un aggregate root **immutable à `confirmed`**. Les splits et le montant total sont gelés à la confirmation ; toute correction passe par `void` + nouvelle transaction. Seuls quelques champs restent éditables après confirmation : `category_id`, `tags`, `description`, `debt_generation_override`, ajout/retrait de `share_request` — aucun ne peut casser la double-entrée.

Grain de sync PowerSync = transaction entière (splits relationnels mais sync atomique sur même bucket).

### Projection serveur (ADR 0002)

Les **dettes sont une projection serveur** matérialisée par `debts.service` à chaque write de transaction. Table `debts` exposée en lecture seule côté client via PowerSync sync rules. Leviers d'écriture utilisateur : `share_ratio` sur la dette (scalaire LWW-safe via endpoint dédié), `debt_generation_override` sur la transaction source, création d'un `Settlement` (cf. ADR 0011).

### Sync buckets (ADR 0003)

Quatre familles : `user_personal_{user_id}`, `account_shared_{account_id}`, `user_debt_{user_id}`, `household`. Plus des **tables server-only** non sync : `pending_actions`, `audit_logs`, `pat_tokens`, `users` PII, `invitations`, `device_tokens`, `sync_request_log`, `auth_challenges`. **Column-level filter** sur les sync rules pour masquer `source_transaction_id` aux non-propriétaires sur les dettes `personal_share_request`.

### Write upload handler (ADR 0014)

Module `sync` au sommet du graphe sous `mcp`. Séquence stricte de 10 étapes par mutation dans une transaction DB unique : auth & RBAC → idempotence (`client_request_id` UUID v7) → Pydantic validation → domain validation → DB write → matérialisation synchrone projections (dettes) → publication events → commit → log → ack. `WriteResult.error` typé pour erreurs récupérables côté client.

### Money et devise (ADR 0008)

Value object `Money(amount_cents: int, currency: ISO4217)` reste multi-devise au domaine ; usage fonctionnel verrouillé à EUR en V1 via `household.base_currency`. Ouverture post-V1 = suppression du verrou + adaptation des écrans agrégateurs, sans migration de données.

---

## 7. Frontend

Voir [`Sans titre.md`](./Sans%20titre.md) pour les user stories par feature. Structure :

```
client/
  src/
    app/                  router, providers, layout, theme
    pages/                un fichier = une route
    features/             interactions complètes (add-transaction, reconcile-bank,
                          settle-debt, link-bank-account, propose-savings-goal…)
    components/
      business/           TransactionRow, AccountCard, DebtSummary, BalancePanel,
                          PendingActionCard, SavingsGoalCard
      ui/                 shadcn (généré)
    lib/
      powersync/          setup, schema, write upload retry handling
      drizzle/            schema local
      api/                client typé OpenAPI
      sse/                EventSource wrapper avec last-event-id resume
      money.ts            mirror du Money Pydantic
    hooks/                partagés (useUser, usePermissions, usePendingActions, useSSE…)
    types/                générés depuis OpenAPI
  capacitor.config.ts
  vite.config.ts
```

**Pas de** : FSD formelle complète, couche `entities/`, séparation `domain/application/infrastructure/ui`.

---

## 8. Sécurité et authentification

- **Auth** : email + Argon2id (pwdlib) + JWT access (15 min) + refresh (30 j, révocable). 2FA TOTP optionnel V1 avec recovery codes (cf. ADR 0013).
- **PAT** (V1) : token préfixé `pfa_`, hashé en DB, hérite des droits du user, scope `read_only`/`read_write`. Heuristiques de compromission dans `modules/mcp/` (4 signaux Tier 1 V1, V1.5 après baseline).
- **Step-up** : création PAT exige 2FA fresh (ou re-mdp si 2FA off).
- **Invitation** : token aléatoire hashé en DB, durée 7j, pré-attribué email, rôle figé `member`, promotion `admin` séparée (cf. ADR 0010).
- **Bootstrap initial** : flow web `/setup` lock-after-init, fallback env vars.
- **SSE auth** : JWT short-lived (5 min) en query param, scope `sse_subscribe` (cf. ADR 0012).
- **Sync rules** : éviction stricte des données d'un user vers un autre, même pour l'admin (F03 invariant fort).

---

## 9. Tests (vue d'ensemble)

Voir [`Stratégie de tests.md`](./Strat%C3%A9gie%20de%20tests.md) pour le détail. Principes :

- **TDD strict** sur les modules à `domain.py` (`transactions`, `reconciliation`, `debts`, `forecasting`, `mcp`).
- **Property-based (Hypothesis)** sur les invariants : zero-sum splits, antisymétrie matrice dettes, idempotence reconciliation, conservation solde net après settlement, déterminisme matching.
- **Tests d'architecture (import-linter)** : matérialisent le graphe directionnel + interdiction d'import internals cross-module + isolation `shared/`.
- **Tests d'intégration DB** : testcontainers Postgres.
- **Tests de contract Enable Banking** : 3 niveaux (unit mock, fixtures Pydantic, nightly réel).
- **Tests E2E Playwright** : 5 parcours, PWA + Android émulé.

---

## 10. ADRs

Tous tranchés au cours du grilling de mai 2026. Liste dans [`docs/adr/`](./adr/) :

| # | Décision |
|---|---|
| [0001](./adr/0001-transaction-aggregate-immutable.md) | Transaction = aggregate root immutable à `confirmed` |
| [0002](./adr/0002-debts-as-server-projection.md) | Dettes = projection serveur, lecture seule côté client |
| [0003](./adr/0003-powersync-bucket-design.md) | Découpage en buckets PowerSync + tables server-only |
| [0004](./adr/0004-mcp-as-module.md) | MCP comme module à part entière, consommateur unidirectionnel |
| [0005](./adr/0005-directional-import-graph.md) | Graphe d'import directionnel + surface publique par module |
| [0006](./adr/0006-reconciliation-as-distinct-entity.md) | `Reconciliation` comme entité distincte de la transaction |
| [0007](./adr/0007-recurring-generation-server-cron.md) | Génération récurrences : cron serveur, horizon = fin du mois |
| [0008](./adr/0008-mono-currency-v1-via-household-pin.md) | Mono-devise V1 via verrou `household.base_currency` |
| [0009](./adr/0009-banking-provider-reader-split.md) | Banking : séparation `BankingProvider` / `BankingReader` |
| [0010](./adr/0010-household-singleton-and-invitation-flow.md) | Foyer singleton + flow d'invitation token-based |
| [0011](./adr/0011-settlement-as-multi-line-entity.md) | `Settlement` multi-line, pas d'état sur `Debt` |
| [0012](./adr/0012-sse-auth-via-short-lived-query-token.md) | SSE : auth via JWT short-lived en query param |
| [0013](./adr/0013-2fa-totp-and-pat-stepup.md) | 2FA TOTP : step-up sur PAT, pas de reset admin-via-app |
| [0014](./adr/0014-sync-module-and-write-upload-handler.md) | Module `sync` + contrat du write upload handler |

---

## 11. Roadmap (recalibrée)

Voir [`Sans titre.md §6`](./Sans%20titre.md#6-phasing-suggéré) pour le découpage features. Cible recalibrée après inventaire honnête :

- **MVP** : **4-6 mois solo full-time** (initialement 2-3 mois, recalibré pour intégrer l'infra Podman/Caddy/Cloudflare/Tailscale/Restic, le setup PowerSync + sync rules + write upload handler, le scaffolding Capacitor/React/shadcn pour ~15 écrans, le bootstrap test stack et l'application des arbitrages de domaine).
- **V1** : +3 mois (Enable Banking, récurrences, pointage, soldes prévisionnel/projeté, PAT, MCP read-only, épargne, notifications).
- **V2** : +2 mois (MCP write avec confirmation, audit lineage, widgets dashboard, recherche, tags, pièces jointes, export CSV).

---

## 12. Test de validation à 12 mois

> Si une nouvelle feature complexe arrive (ex. "split d'une transaction commune avec règle de répartition dynamique par catégorie"), on doit savoir **immédiatement** dans quel(s) module(s) elle vit. Si oui → l'architecture tient. Si non → signal d'alerte.
