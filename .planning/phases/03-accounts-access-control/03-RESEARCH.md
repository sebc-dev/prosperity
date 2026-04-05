# Phase 3: Accounts & Access Control - Research

**Researched:** 2026-04-05
**Domain:** CRUD bank accounts + row-level access control (JPQL filtering) + Angular 21 account management UI
**Confidence:** HIGH

## Summary

Phase 3 builds CRUD for bank accounts and row-level access control on top of existing JPA entities (`Account`, `AccountAccess`, `AccessLevel`) and Flyway migrations (V002, V003). The entities and schema already exist from Phase 1; this phase adds the service layer, repository queries, REST endpoints, and Angular frontend.

The core technical challenge is access control enforcement at the repository level via JPQL joins on `account_access`, not at the controller level. Every query that returns account data must filter by the current user's ID. The `Account` entity needs an `archived` field (new Flyway migration V009). The frontend is a single `/accounts` page with p-table, two p-dialog instances (create/edit, access management), and sidebar navigation link.

**Primary recommendation:** Build backend layer first (migration, repository queries, service, controller with tests), then frontend (service, account list component, dialogs). Each layer is independently reviewable and testable.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Filtrage par JPQL dans le repository. `findAllAccessibleByUserId(UUID userId)` avec JOIN sur `account_access`. Le Service recupere l'utilisateur courant depuis le `SecurityContext` et passe son id. Pas de `findAll()` global expose.
- **D-02:** `GET /api/accounts/{id}` sans acces -> **403 Forbidden** (pas 404). L'objet existe mais l'acces est refuse -- distinction volontaire pour ne pas masquer une erreur de permission.
- **D-03:** Le controle d'acces s'applique a tous les endpoints de donnees (ACCS-04) : pas d'agregation possible sur un compte non accessible.
- **D-04:** Le createur d'un compte obtient automatiquement le niveau **ADMIN** sur ce compte (une entree `AccountAccess` est creee en meme temps que le compte).
- **D-05:** Pour les comptes **SHARED** : pas d'acces automatique aux autres utilisateurs. L'admin du compte accorde explicitement les permissions via ACCS-03. Coherent avec le modele de permissions -- rien d'implicite.
- **D-06:** La colonne `archived BOOLEAN NOT NULL DEFAULT FALSE` est absente du schema actuel -- migration Flyway a ajouter (V009 ou suivant).
- **D-07:** `GET /api/accounts` exclut les comptes archives par defaut. `GET /api/accounts?includeArchived=true` les inclut. Dans l'UI, un toggle "Afficher les archives".
- **D-08:** Desarchivage possible : `PATCH /api/accounts/{id}` accepte `{"archived": false}`. Pas irreversible en v1.
- **D-09:** Page dediee `/accounts` accessible depuis la sidebar (lien ajoute dans `sidebar.ts`).
- **D-10:** Liste des comptes en **table `p-table` PrimeNG** -- colonnes : Nom, Type, Solde, Statut, Actions. Tri natif.
- **D-11:** Creation et edition via **`p-dialog` PrimeNG** -- formulaire dans une modale, pas de navigation separee.
- **D-12:** Gestion des permissions (ACCS-03) via un **dialog separe** -- bouton "Gerer les acces" ouvre un second dialog.

### Claude's Discretion
- Nommage exact des endpoints REST (pluriel/singulier, verbes)
- Structure exacte des DTOs (records Java)
- Pagination de la liste des comptes (probablement pas necessaire en v1 -- foyer de 2 personnes)
- Validation exacte des champs (longueur max du nom, etc.)
- Styles Tailwind/PrimeNG pour la table et les dialogs

### Deferred Ideas (OUT OF SCOPE)
- Widget dashboard avec les soldes des comptes -- Phase 10
- Invitation d'utilisateurs -- Phase 8 (Administration)
- Connexion Plaid par compte -- Phase 7
- Pagination de la liste des comptes -- backlog (inutile pour un foyer de 2 en v1)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ACCT-01 | Utilisateur peut creer un compte bancaire personnel | Backend: AccountService.createAccount() + AccountController POST. Frontend: create dialog with type PERSONAL. D-04 auto-ADMIN access. |
| ACCT-02 | Utilisateur peut creer un compte bancaire commun | Same flow as ACCT-01 with type SHARED. D-05: no auto-access for others. |
| ACCT-03 | Utilisateur peut voir la liste de ses comptes avec soldes | Backend: AccountRepository.findAllAccessibleByUserId() JPQL query (D-01). Frontend: p-table with Nom/Type/Solde/Statut/Actions. |
| ACCT-04 | Utilisateur peut modifier les informations d'un compte (nom, type) | Backend: AccountService.updateAccount() with WRITE+ access check. Frontend: edit dialog (same as create, pre-filled). |
| ACCT-05 | Utilisateur peut archiver un compte | Backend: V009 migration adds `archived` column. PATCH endpoint (D-08). Frontend: archive button + confirm dialog. |
| ACCS-01 | Chaque compte a des permissions par utilisateur (lecture/ecriture/admin) | Already modeled: `AccountAccess` entity + `AccessLevel` enum. Service enforces level checks. |
| ACCS-02 | Utilisateur ne voit que les comptes auxquels il a acces | JPQL join filtering in repository (D-01). No findAll() exposed. |
| ACCS-03 | Admin peut modifier les permissions d'acces aux comptes pour chaque utilisateur | Backend: AccountAccessService CRUD. Frontend: access management dialog (D-12). Account-ADMIN level required. |
| ACCS-04 | Le controle d'acces s'applique aux requetes d'agregation | D-03: all data endpoints filter by user. Repository pattern ensures no leak. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Java 21 LTS (Temurin) + Spring Boot 4.0.x + Spring Security 7.0.x
- Spring Data JPA 4.0.x + Flyway 11.x
- PostgreSQL 17
- Angular 21 + PrimeNG 21.x + Tailwind CSS v4
- No Lombok -- Java 21 records for DTOs, manual getters/setters for JPA entities
- Constructor injection, no `@Autowired`
- DTOs as Java records with Jakarta Validation annotations
- Frontend: standalone components, OnPush, signals
- Layered by feature architecture
- Testing: AAA structure, FIRST properties, mock only external dependencies
- Open source deps only (MIT/Apache 2.0)

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Spring Data JPA | 4.0.x (via Boot) | Repository JPQL queries for access-filtered account lookups | Already configured, Hibernate 7 under the hood |
| Spring Security | 7.0.x (via Boot) | SecurityContextHolder for current user resolution, endpoint auth | BFF cookie flow already in place from Phase 2 |
| Flyway | 11.x | V009 migration to add `archived` column | Already in use (V001-V008 exist) |
| PrimeNG | 21.x | p-table, p-dialog, p-select, p-tag, p-confirmdialog, p-toggleswitch, p-message | Already installed, Aura theme configured |
| Angular Reactive Forms | 21.x | Form handling for create/edit/access dialogs | Built-in Angular, reactive validation |

### Supporting (already in project)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Jakarta Validation | 3.1 (via Boot) | @NotBlank, @Size on request DTOs | All incoming request validation |
| AssertJ | 3.x (via Boot) | Fluent test assertions | All backend tests |
| Testcontainers | 2.x | PostgreSQL integration tests | AccountController integration tests |
| MockMvc | (via Boot) | Controller endpoint testing | Integration tests with `@AutoConfigureMockMvc` |

**No new dependencies needed.** Everything required is already present in the project from Phases 1-2.

## Architecture Patterns

### Recommended Project Structure

```
backend/src/main/java/com/prosperity/account/
  Account.java              # (existing) JPA entity - add archived field
  AccountAccess.java        # (existing) JPA entity
  AccessLevel.java          # (existing) enum
  AccountType.java          # (existing in shared/) enum
  AccountRepository.java    # (existing) add JPQL queries
  AccountAccessRepository.java  # (existing) add JPQL queries
  AccountService.java       # (new) business logic + access checks
  AccountController.java    # (new) REST endpoints
  CreateAccountRequest.java # (new) DTO record
  UpdateAccountRequest.java # (new) DTO record
  AccountResponse.java      # (new) DTO record
  AccountAccessResponse.java    # (new) DTO record
  SetAccessRequest.java     # (new) DTO record
  AccountNotFoundException.java     # (new) exception
  AccountAccessDeniedException.java # (new) exception

frontend/src/app/accounts/
  accounts.ts               # (new) main page component with p-table
  accounts.spec.ts          # (new) tests
  account-dialog.ts         # (new) create/edit dialog component
  account-dialog.spec.ts    # (new) tests
  access-dialog.ts          # (new) access management dialog component
  access-dialog.spec.ts     # (new) tests
  account.service.ts        # (new) HTTP service
  account.service.spec.ts   # (new) tests
  account.types.ts          # (new) TypeScript interfaces
```

### Pattern 1: JPQL Access-Filtered Repository

**What:** All account queries JOIN on `account_access` to filter by user ID. No unfiltered `findAll()` exposed.
**When to use:** Every repository method that returns account data.
**Example:**
```java
// AccountRepository.java
@Query("""
    SELECT a FROM Account a
    JOIN AccountAccess aa ON aa.bankAccount = a
    WHERE aa.user.id = :userId
    AND a.archived = false
    """)
List<Account> findAllAccessibleByUserId(@Param("userId") UUID userId);

@Query("""
    SELECT a FROM Account a
    JOIN AccountAccess aa ON aa.bankAccount = a
    WHERE aa.user.id = :userId
    """)
List<Account> findAllAccessibleByUserIdIncludingArchived(@Param("userId") UUID userId);

@Query("""
    SELECT CASE WHEN COUNT(aa) > 0 THEN true ELSE false END
    FROM AccountAccess aa
    WHERE aa.bankAccount.id = :accountId
    AND aa.user.id = :userId
    AND aa.accessLevel IN :levels
    """)
boolean hasAccess(@Param("accountId") UUID accountId,
                  @Param("userId") UUID userId,
                  @Param("levels") Collection<AccessLevel> levels);
```

### Pattern 2: Service Layer Access Enforcement

**What:** Service resolves current user from SecurityContext, delegates filtering to repository, checks access level before mutations.
**When to use:** All AccountService methods.
**Example:**
```java
// AccountService.java
@Service
public class AccountService {
    private final AccountRepository accountRepository;
    private final AccountAccessRepository accountAccessRepository;
    private final UserRepository userRepository;

    // Constructor injection

    @Transactional
    public AccountResponse createAccount(CreateAccountRequest request, String userEmail) {
        var user = userRepository.findByEmail(userEmail).orElseThrow();
        var account = new Account(request.name(), request.accountType());
        account = accountRepository.save(account);

        // D-04: creator gets ADMIN
        var access = new AccountAccess(user, account, AccessLevel.ADMIN);
        accountAccessRepository.save(access);

        return toResponse(account);
    }
}
```

### Pattern 3: Controller with @AuthenticationPrincipal

**What:** Controller extracts current user identity via `@AuthenticationPrincipal UserDetails` and passes email to service.
**When to use:** All AccountController endpoints.
**Example:**
```java
@RestController
@RequestMapping("/api/accounts")
public class AccountController {
    private final AccountService accountService;

    @PostMapping
    public ResponseEntity<AccountResponse> create(
            @Valid @RequestBody CreateAccountRequest request,
            @AuthenticationPrincipal UserDetails userDetails) {
        var response = accountService.createAccount(request, userDetails.getUsername());
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/{id}")
    public ResponseEntity<AccountResponse> getById(
            @PathVariable UUID id,
            @AuthenticationPrincipal UserDetails userDetails) {
        // D-02: returns 403 if no access (not 404)
        var response = accountService.getAccount(id, userDetails.getUsername());
        return ResponseEntity.ok(response);
    }
}
```

### Pattern 4: Angular Signal-Based Service

**What:** Frontend service uses Angular signals for reactive state, HttpClient for API calls.
**When to use:** AccountService frontend.
**Example:**
```typescript
@Injectable({ providedIn: 'root' })
export class AccountService {
    private readonly http = inject(HttpClient);
    private accountsSignal = signal<AccountResponse[]>([]);

    readonly accounts = this.accountsSignal.asReadonly();

    loadAccounts(includeArchived = false): Observable<AccountResponse[]> {
        const params = includeArchived ? { includeArchived: 'true' } : {};
        return this.http.get<AccountResponse[]>('/api/accounts', { params }).pipe(
            tap(accounts => this.accountsSignal.set(accounts))
        );
    }
}
```

### Pattern 5: Immediate-Save Access Dialog

**What:** Each access level change in the access management dialog triggers an immediate API call. No bulk save.
**When to use:** Access management dialog (D-12, per UI spec).
**Example:** Row-level loading state using signal per row, API call on p-select change event.

### Anti-Patterns to Avoid
- **Exposing unfiltered findAll():** Never expose `AccountRepository.findAll()` in the service. All queries must filter by user.
- **Access check in controller only:** Access enforcement must be in the service layer. The controller delegates; it does not make access decisions.
- **N+1 queries for access checks:** Use JOIN in JPQL instead of loading account then checking access separately. Batch the check into the query.
- **Mocking SecurityContext in unit tests:** Pass userEmail as a parameter to service methods. The controller resolves the email; the service receives it as a plain string. This keeps service tests clean (no Spring Security mocking needed).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CSRF protection | Custom token management | Spring Security 7 SPA CSRF mode (already configured) | Already working from Phase 2 |
| Form validation | Custom validators | Jakarta Validation annotations on records + Angular reactive form validators | Standard, declarative, testable |
| Confirmation dialogs | Custom modal logic | PrimeNG `p-confirmdialog` + `ConfirmationService` | Built-in, accessible, consistent with UI spec |
| Table sorting | Custom sort comparators | PrimeNG `p-table` `[sortField]` / `[sortOrder]` | Native feature, zero code |
| Access level hierarchy | Custom ordinal comparison | `AccessLevel` enum with ordinal or method `isAtLeast(AccessLevel)` | Simple, explicit, testable |

## Common Pitfalls

### Pitfall 1: Forgetting access check on update/delete/archive
**What goes wrong:** A user without WRITE or ADMIN access can modify an account they can only READ.
**Why it happens:** Developer implements READ access check but forgets to verify higher levels for mutations.
**How to avoid:** Service method checks `hasAccess(accountId, userId, List.of(WRITE, ADMIN))` before any mutation. ADMIN-only operations (like managing access) check `hasAccess(accountId, userId, List.of(ADMIN))`.
**Warning signs:** Tests only verify happy path, no test for insufficient access level.

### Pitfall 2: Access leak through related endpoints
**What goes wrong:** Future endpoints (transactions, envelopes) that reference accounts don't filter by access, leaking data.
**Why it happens:** ACCS-04 requires access control on ALL data queries, including aggregations.
**How to avoid:** Establish the repository pattern now: every query involving account data JOINs on `account_access`. Document this pattern clearly so future phases follow it.
**Warning signs:** A new endpoint uses `accountRepository.findById()` directly without access check.

### Pitfall 3: Creator loses ADMIN when modifying access list
**What goes wrong:** The access management dialog allows removing the last ADMIN from an account, orphaning it.
**Why it happens:** No business rule preventing removal of own ADMIN access.
**How to avoid:** Service enforces: cannot remove the last ADMIN access on an account. UI disables remove button and level change for the current user's own ADMIN row (per UI spec).
**Warning signs:** No test for "cannot remove last admin" scenario.

### Pitfall 4: Archived account still receives new access grants
**What goes wrong:** Admin grants access to an archived account, user sees a ghost account.
**Why it happens:** Archive check not applied to access management operations.
**How to avoid:** Decide if access management should be blocked on archived accounts (recommendation: allow it -- the account can be unarchived, and managing access before unarchiving is a valid use case). Document the decision.

### Pitfall 5: N+1 query on account list with access info
**What goes wrong:** Loading the account list triggers N additional queries to fetch access level per account.
**Why it happens:** Service fetches accounts then checks access level individually.
**How to avoid:** Use a single JPQL query that also returns the current user's access level: `SELECT a, aa.accessLevel FROM Account a JOIN AccountAccess aa ON aa.bankAccount = a WHERE aa.user.id = :userId`.

### Pitfall 6: SecurityContext not available in async/background contexts
**What goes wrong:** If a method is called outside an HTTP request context, `SecurityContextHolder` returns null.
**Why it happens:** Spring Security 7 does not propagate context to child threads by default.
**How to avoid:** Always pass userId/email as a method parameter in the service layer. Never call `SecurityContextHolder` from service code. Only the controller resolves the current user.

## Code Examples

### DTO Records (Java)
```java
// CreateAccountRequest.java
public record CreateAccountRequest(
    @NotBlank @Size(max = 100) String name,
    @NotNull AccountType accountType
) {}

// UpdateAccountRequest.java
public record UpdateAccountRequest(
    @Size(max = 100) String name,
    AccountType accountType,
    Boolean archived
) {}

// AccountResponse.java
public record AccountResponse(
    UUID id,
    String name,
    AccountType accountType,
    BigDecimal balance,
    String currency,
    boolean archived,
    Instant createdAt,
    AccessLevel currentUserAccessLevel
) {}

// AccountAccessResponse.java
public record AccountAccessResponse(
    UUID id,
    UUID userId,
    String userEmail,
    String userDisplayName,
    AccessLevel accessLevel
) {}

// SetAccessRequest.java
public record SetAccessRequest(
    @NotNull UUID userId,
    @NotNull AccessLevel accessLevel
) {}
```

### Flyway Migration V009
```sql
-- V009__add_archived_to_bank_accounts.sql
ALTER TABLE bank_accounts
    ADD COLUMN archived BOOLEAN NOT NULL DEFAULT FALSE;
```

### Account Entity Update
```java
// Add to Account.java
@Column(nullable = false)
private boolean archived = false;

public boolean isArchived() { return archived; }
public void setArchived(boolean archived) { this.archived = archived; }
```

### TypeScript Interfaces
```typescript
// account.types.ts
export type AccountType = 'PERSONAL' | 'SHARED';
export type AccessLevel = 'READ' | 'WRITE' | 'ADMIN';

export interface AccountResponse {
    id: string;
    name: string;
    accountType: AccountType;
    balance: number;
    currency: string;
    archived: boolean;
    createdAt: string;
    currentUserAccessLevel: AccessLevel;
}

export interface CreateAccountRequest {
    name: string;
    accountType: AccountType;
}

export interface UpdateAccountRequest {
    name?: string;
    accountType?: AccountType;
    archived?: boolean;
}

export interface AccountAccessResponse {
    id: string;
    userId: string;
    userEmail: string;
    userDisplayName: string;
    accessLevel: AccessLevel;
}
```

### REST Endpoint Design (Claude's Discretion)
```
POST   /api/accounts                          -- create account
GET    /api/accounts                          -- list accessible accounts (?includeArchived=true)
GET    /api/accounts/{id}                     -- get single account (403 if no access)
PATCH  /api/accounts/{id}                     -- update account (name, type, archived)
GET    /api/accounts/{id}/access              -- list access entries (ADMIN only)
POST   /api/accounts/{id}/access              -- grant access to user (ADMIN only)
PATCH  /api/accounts/{id}/access/{accessId}   -- update access level (ADMIN only)
DELETE /api/accounts/{id}/access/{accessId}   -- revoke access (ADMIN only)
GET    /api/users                             -- list all users (for access dialog dropdown)
```

**Note on `GET /api/users`:** The access management dialog needs a list of all users to populate the "Ajouter un utilisateur" dropdown. This endpoint returns minimal user info (id, email, displayName). It belongs in the `auth` package or a lightweight `user` endpoint. Needed by ACCS-03.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Spring Security `@PreAuthorize` with SpEL | JPQL repository-level filtering | Project decision (D-01) | Filtering at query level is more secure than post-fetch filtering. No data ever loaded into memory without access. |
| Spring Boot 3.x `@AutoConfigureMockMvc` | Spring Boot 4.0.x `@AutoConfigureMockMvc` in `spring-boot-webmvc-test` module | Nov 2025 | Import from `org.springframework.boot.webmvc.test.autoconfigure` (already used in Phase 2) |
| `BehaviorSubject` for state | Angular `signal()` | Angular 16+ | Project convention from Phase 2: signals for all reactive state |

## Open Questions

1. **User list endpoint location**
   - What we know: The access management dialog needs all users to populate the "add user" dropdown.
   - What's unclear: Should this be `GET /api/users` in auth package, or a new lightweight endpoint?
   - Recommendation: Add `GET /api/users` to `AuthController` (it already has `UserRepository`). Return `List<UserResponse>` (id, email, displayName). Keep it simple -- only 2-3 users in a household.

2. **Access level hierarchy enforcement**
   - What we know: READ < WRITE < ADMIN. A WRITE user can do everything a READ user can, plus mutations.
   - What's unclear: Should `AccessLevel` enum encode this ordering?
   - Recommendation: Add a method `isAtLeast(AccessLevel required)` to the enum using ordinal comparison. Keep enum ordering READ(0), WRITE(1), ADMIN(2).

3. **Sidebar navigation pattern**
   - What we know: Current sidebar is a placeholder `p-drawer` with static text. Need to add `/accounts` link.
   - What's unclear: Should sidebar use `routerLink` with `routerLinkActive` for active state?
   - Recommendation: Yes. Refactor sidebar to use `RouterLink` + `RouterLinkActive` directives. Add `pi-wallet` or `pi-credit-card` icon for accounts link. This sets the pattern for future phases.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework (backend) | JUnit 5 + AssertJ + Mockito (via spring-boot-starter-test) |
| Framework (frontend) | Angular unit-test builder (Vitest-based, `@angular/build:unit-test`) |
| Config file (backend) | `backend/pom.xml` (surefire/failsafe plugins) |
| Config file (frontend) | `frontend/angular.json` (architect.test) |
| Quick run command (backend) | `cd backend && ./mvnw test -pl . -Dtest=AccountServiceTest -Dsurefire.failIfNoSpecifiedTests=false` |
| Quick run command (frontend) | `cd frontend && pnpm test -- --reporter=verbose` |
| Full suite command | `cd backend && ./mvnw verify && cd ../frontend && pnpm test` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ACCT-01 | Create personal account + auto ADMIN access | integration | `./mvnw test -Dtest=AccountControllerTest#create_personal_account*` | Wave 0 |
| ACCT-02 | Create shared account (no auto-access for others) | integration | `./mvnw test -Dtest=AccountControllerTest#create_shared_account*` | Wave 0 |
| ACCT-03 | List accounts filtered by user access | integration | `./mvnw test -Dtest=AccountControllerTest#list_accounts*` | Wave 0 |
| ACCT-04 | Update account name/type with WRITE access | integration | `./mvnw test -Dtest=AccountControllerTest#update_account*` | Wave 0 |
| ACCT-05 | Archive/unarchive account | integration | `./mvnw test -Dtest=AccountControllerTest#archive*` | Wave 0 |
| ACCS-01 | Permission levels enforced (READ/WRITE/ADMIN) | unit | `./mvnw test -Dtest=AccountServiceTest#access_level*` | Wave 0 |
| ACCS-02 | User sees only accessible accounts | integration | `./mvnw test -Dtest=AccountControllerTest#list_returns_only*` | Wave 0 |
| ACCS-03 | Admin modifies access on account | integration | `./mvnw test -Dtest=AccountControllerTest#manage_access*` | Wave 0 |
| ACCS-04 | Access control on all data queries | integration | `./mvnw test -Dtest=AccountControllerTest#no_access*` | Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && ./mvnw test -Dtest=AccountServiceTest,AccountControllerTest`
- **Per wave merge:** `cd backend && ./mvnw verify && cd ../frontend && pnpm test`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `backend/src/test/java/com/prosperity/account/AccountServiceTest.java` -- unit tests for service business logic
- [ ] `backend/src/test/java/com/prosperity/account/AccountControllerTest.java` -- integration tests for REST endpoints + access control
- [ ] `frontend/src/app/accounts/account.service.spec.ts` -- HTTP service tests
- [ ] `frontend/src/app/accounts/accounts.spec.ts` -- component tests
- [ ] `frontend/src/app/accounts/account-dialog.spec.ts` -- dialog component tests
- [ ] `frontend/src/app/accounts/access-dialog.spec.ts` -- access dialog component tests

## Sources

### Primary (HIGH confidence)
- Existing codebase: `Account.java`, `AccountAccess.java`, `AccessLevel.java`, `AccountRepository.java`, `AccountAccessRepository.java` -- entities and repos already exist
- Existing codebase: `AuthController.java`, `AuthService.java` -- established patterns for controller/service/DTO
- Existing codebase: `AuthControllerTest.java`, `AuthServiceTest.java` -- established test patterns (MockMvc + Testcontainers, Mockito unit tests)
- Existing codebase: `V002__create_bank_accounts.sql`, `V003__create_account_access.sql` -- current DB schema
- Existing codebase: `SecurityConfig.java` -- current security configuration
- Phase context: `03-CONTEXT.md` -- locked decisions D-01 through D-12
- UI spec: `03-UI-SPEC.md` -- approved component inventory and interaction contract

### Secondary (MEDIUM confidence)
- Spring Data JPA JPQL syntax: based on established Hibernate/JPA patterns, consistent across Spring Boot 4.0.x
- PrimeNG component APIs: based on PrimeNG 21.x documentation and project's existing usage of PrimeNG components

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in the project, no new dependencies
- Architecture: HIGH -- follows established patterns from Phase 2 (Controller/Service/Repository/DTO records)
- Pitfalls: HIGH -- access control pitfalls are well-documented in the domain; project decisions explicitly address main risks
- Frontend: HIGH -- UI spec approved, PrimeNG components already imported

**Research date:** 2026-04-05
**Valid until:** 2026-05-05 (stable -- no external dependency changes expected)
