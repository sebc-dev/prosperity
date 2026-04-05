# Phase 3: Accounts & Access Control - Context

**Gathered:** 2026-04-05
**Status:** Ready for planning

<domain>
## Phase Boundary

CRUD comptes bancaires (personnel + commun) avec permissions par utilisateur (READ/WRITE/ADMIN) appliquées à tous les niveaux — repository, service, endpoints d'agrégation. Invitation d'utilisateurs, gestion des rôles système, et Plaid sont hors scope.

</domain>

<decisions>
## Implementation Decisions

### Enforcement du contrôle d'accès
- **D-01:** Filtrage par JPQL dans le repository. `findAllAccessibleByUserId(UUID userId)` avec JOIN sur `account_access`. Le Service récupère l'utilisateur courant depuis le `SecurityContext` et passe son id. Pas de `findAll()` global exposé.
- **D-02:** `GET /api/accounts/{id}` sans accès → **403 Forbidden** (pas 404). L'objet existe mais l'accès est refusé — distinction volontaire pour ne pas masquer une erreur de permission.
- **D-03:** Le contrôle d'accès s'applique à tous les endpoints de données (ACCS-04) : pas d'agrégation possible sur un compte non accessible.

### Attribution de permissions à la création
- **D-04:** Le créateur d'un compte obtient automatiquement le niveau **ADMIN** sur ce compte (une entrée `AccountAccess` est créée en même temps que le compte).
- **D-05:** Pour les comptes **SHARED** : pas d'accès automatique aux autres utilisateurs. L'admin du compte accorde explicitement les permissions via ACCS-03. Cohérent avec le modèle de permissions — rien d'implicite.

### Archivage
- **D-06:** La colonne `archived BOOLEAN NOT NULL DEFAULT FALSE` est absente du schema actuel — migration Flyway à ajouter (V009 ou suivant).
- **D-07:** `GET /api/accounts` exclut les comptes archivés par défaut. `GET /api/accounts?includeArchived=true` les inclut. Dans l'UI, un toggle "Afficher les archivés".
- **D-08:** Désarchivage possible : `PATCH /api/accounts/{id}` accepte `{"archived": false}`. Pas irréversible en v1.

### Interface de gestion des comptes (Frontend)
- **D-09:** Page dédiée `/accounts` accessible depuis la sidebar (lien ajouté dans `sidebar.ts`). En Phase 10, la vue dashboard intégrera un widget comptes — la page `/accounts` reste pour la gestion détaillée.
- **D-10:** Liste des comptes en **table `p-table` PrimeNG** — colonnes : Nom, Type (Personal/Shared), Solde, Statut (actif/archivé), Actions. Tri natif.
- **D-11:** Création et édition via **`p-dialog` PrimeNG** — formulaire dans une modale, pas de navigation séparée. Champs : nom, type de compte.
- **D-12:** Gestion des permissions (ACCS-03) via un **dialog séparé** — bouton "Gérer les accès" ouvre un second dialog avec la liste des utilisateurs + leur niveau d'accès actuel (READ/WRITE/ADMIN) + action pour modifier.

### Claude's Discretion
- Nommage exact des endpoints REST (pluriel/singulier, verbes)
- Structure exacte des DTOs (records Java)
- Pagination de la liste des comptes (probablement pas nécessaire en v1 — foyer de 2 personnes)
- Validation exacte des champs (longueur max du nom, etc.)
- Styles Tailwind/PrimeNG pour la table et les dialogs

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture & patterns
- `docs/adr/0002-architecture-layered.md` — Layered by feature, package `account/` location
- `docs/agent_docs/architecture.md` — Structure backend, composants, flux de données
- `.planning/phases/02-authentication-setup-wizard/02-CONTEXT.md` — Patterns Controller/Service/DTO établis en Phase 2

### Database schema
- `backend/src/main/resources/db/migration/V002__create_bank_accounts.sql` — Schema actuel `bank_accounts` (sans colonne `archived`)
- `backend/src/main/resources/db/migration/V003__create_account_access.sql` — Schema `account_access`
- `docs/agent_docs/database.md` — Schema complet PostgreSQL, relations

### Requirements
- `.planning/REQUIREMENTS.md` §Comptes Bancaires — ACCT-01 à ACCT-05
- `.planning/REQUIREMENTS.md` §Contrôle d'Accès — ACCS-01 à ACCS-04

### Testing principles
- `.claude/rules/testing-principles.md` — AAA structure, FIRST properties, test doubles rules

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Account` entity (`account/Account.java`) — JPA entity complète : id (UUID), name, accountType (PERSONAL/SHARED), balance (Money), currency, plaidAccountId, createdAt, updatedAt. **Pas de champ `archived`** — à ajouter.
- `AccountAccess` entity (`account/AccountAccess.java`) — user (ManyToOne), bankAccount (ManyToOne), accessLevel (READ/WRITE/ADMIN).
- `AccessLevel` enum (`account/AccessLevel.java`) — READ, WRITE, ADMIN.
- `AccountRepository` (`account/AccountRepository.java`) — JpaRepository vide, à enrichir avec queries JPQL.
- `AccountAccessRepository` (`account/AccountAccessRepository.java`) — JpaRepository vide.
- `AccountType` enum (`shared/AccountType.java`) — PERSONAL, SHARED.
- Pattern auth : `AuthController` + `AuthService` + DTOs records — réplique ce pattern pour `AccountController` + `AccountService`.
- Frontend `AuthService` — signals Angular (`signal`, `computed`), inject pattern — réutiliser pour `AccountService` frontend.
- Layout shell (`layout/layout.ts`) — sidebar vide prête pour ajout de liens.

### Established Patterns
- Controller : `@RestController`, `@RequestMapping("/api/...")`, `ResponseEntity<>`, `@AuthenticationPrincipal UserDetails`
- Service : constructeur injection, pas de `@Autowired`
- DTOs : Java records (`LoginRequest`, `UserResponse`)
- Validation : `@Valid` + annotations Jakarta Validation sur les records
- Frontend : standalone components, `ChangeDetectionStrategy.OnPush`, signals
- Routes : lazy-loaded avec `loadComponent`

### Integration Points
- `SecurityContext` : le Service récupère l'utilisateur courant via `SecurityContextHolder.getContext().getAuthentication()`
- `UserRepository` : `findByEmail(String)` pour récupérer l'entité `User` depuis le principal
- Flyway : prochaine migration = V009 (V008 = spring session tables)
- `sidebar.ts` : ajout du lien `/accounts` dans la navigation
- `app.routes.ts` : ajout de la route `/accounts` dans les children du layout shell

</code_context>

<specifics>
## Specific Ideas

- La page `/accounts` est temporaire — en Phase 10, un widget dashboard affichera les comptes. La page reste pour la gestion détaillée (archivage, permissions).
- Le dialog de gestion des accès doit lister tous les utilisateurs du système avec leur niveau actuel et permettre de le modifier — ACCS-03 concerne les admins de compte, pas seulement les admins système.

</specifics>

<deferred>
## Deferred Ideas

- Widget dashboard avec les soldes des comptes — Phase 10
- Invitation d'utilisateurs — Phase 8 (Administration)
- Connexion Plaid par compte — Phase 7
- Pagination de la liste des comptes — backlog (inutile pour un foyer de 2 en v1)

</deferred>

---

*Phase: 03-accounts-access-control*
*Context gathered: 2026-04-05*
