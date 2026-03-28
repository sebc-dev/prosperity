# Architecture Research

**Domain:** Personal finance management (self-hosted, envelope budgeting, multi-accounts)
**Researched:** 2026-03-28
**Confidence:** HIGH

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        EDGE (Caddy :443)                            │
│  HTTPS auto, HTTP/3, static files, /api/* proxy                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────────────┐    ┌────────────────────────────────┐  │
│  │     Angular SPA/PWA      │    │      Spring Boot API :8080     │  │
│  │                          │    │                                │  │
│  │  core/                   │    │  infrastructure/adapter/in/    │  │
│  │    guards, interceptors  │    │    REST controllers            │  │
│  │    auth service          │    │    security config             │  │
│  │                          │    │                                │  │
│  │  features/               │    │  application/service/          │  │
│  │    dashboard/            │    │    use cases                   │  │
│  │    accounts/             │    │    orchestration               │  │
│  │    transactions/         │    │                                │  │
│  │    envelopes/            │    │  domain/                       │  │
│  │    debts/                │    │    model/ (entities, VOs)      │  │
│  │    admin/                │    │    port/in/ (use case ifaces)  │  │
│  │    auth/                 │    │    port/out/ (repo ifaces)     │  │
│  │                          │    │                                │  │
│  └──────────────────────────┘    │  infrastructure/adapter/out/   │  │
│                                  │    persistence/ (JPA)          │  │
│                                  │    banking/ (Plaid)            │  │
│                                  └──────────┬──────┬─────────────┘  │
│                                             │      │                │
│                                  ┌──────────┴──┐ ┌─┴──────────────┐ │
│                                  │ PostgreSQL  │ │   Plaid API    │ │
│                                  │   :5432     │ │   (external)   │ │
│                                  └─────────────┘ └────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Implementation |
|-----------|----------------|----------------|
| Caddy | TLS termination, static file serving, API proxying | Caddy 2.10.x with Caddyfile |
| Angular SPA | User interface, client-side routing, form validation, charts | Angular 21 standalone components + PrimeNG + ECharts |
| REST Controllers | HTTP mapping, request validation, response shaping | Spring MVC `@RestController` in `adapter/in/rest/` |
| Security Layer | BFF cookie auth, CSRF, session management | Spring Security 7.0.x filter chain |
| Use Case Services | Business orchestration, transaction boundaries | `@UseCase`-annotated classes in `application/service/` |
| Domain Model | Business rules, invariant enforcement, value calculations | POJOs in `domain/model/`, zero framework deps |
| Persistence Adapters | ORM mapping, query execution, data access | Spring Data JPA repos in `adapter/out/persistence/` |
| Banking Adapter | Bank sync, transaction import, connection management | Plaid client in `adapter/out/banking/` behind port interface |
| PostgreSQL | Persistent storage, schema migrations | PostgreSQL 17 + Liquibase 5.0.x |

## Recommended Project Structure

### Backend (Spring Boot)

```
src/main/java/com/prosperity/
├── domain/                          # Pure business logic, ZERO framework deps
│   ├── model/                       # Entities + Value Objects
│   │   ├── account/                 # BankAccount, AccountType, AccountAccess
│   │   ├── transaction/             # Transaction, TransactionSource, Category
│   │   ├── envelope/                # Envelope, EnvelopeAllocation, RolloverPolicy
│   │   ├── debt/                    # Debt, DebtPayment
│   │   └── user/                    # User, Role
│   └── port/
│       ├── in/                      # Use case interfaces (driving ports)
│       │   ├── ManageAccountsUseCase.java
│       │   ├── ImportTransactionsUseCase.java
│       │   ├── ManageEnvelopesUseCase.java
│       │   ├── ManageDebtsUseCase.java
│       │   ├── PointTransactionUseCase.java
│       │   └── SyncBankUseCase.java
│       └── out/                     # Repository/service interfaces (driven ports)
│           ├── AccountRepository.java
│           ├── TransactionRepository.java
│           ├── EnvelopeRepository.java
│           ├── DebtRepository.java
│           ├── UserRepository.java
│           └── BankConnector.java   # Abstract bank sync interface
│
├── application/                     # Use case orchestration
│   └── service/
│       ├── AccountService.java      # Implements ManageAccountsUseCase
│       ├── TransactionService.java  # Implements ImportTransactionsUseCase
│       ├── EnvelopeService.java     # Implements ManageEnvelopesUseCase
│       ├── DebtService.java         # Implements ManageDebtsUseCase
│       ├── PointingService.java     # Implements PointTransactionUseCase
│       └── BankSyncService.java     # Implements SyncBankUseCase
│
└── infrastructure/
    ├── adapter/
    │   ├── in/
    │   │   └── rest/                # REST controllers (driving adapters)
    │   │       ├── AccountController.java
    │   │       ├── TransactionController.java
    │   │       ├── EnvelopeController.java
    │   │       ├── DebtController.java
    │   │       ├── AdminController.java
    │   │       ├── AuthController.java
    │   │       ├── DashboardController.java
    │   │       └── dto/             # Request/response DTOs
    │   └── out/
    │       ├── persistence/         # JPA adapters (driven adapters)
    │       │   ├── entity/          # JPA entities (@Entity)
    │       │   ├── mapper/          # Domain <-> JPA entity mappers
    │       │   └── repository/      # Spring Data JPA repos
    │       └── banking/             # Bank sync adapters
    │           ├── PlaidBankConnector.java
    │           └── plaid/           # Plaid-specific DTOs, client
    └── config/                      # Spring configuration
        ├── SecurityConfig.java
        ├── CorsConfig.java
        ├── JpaConfig.java
        └── PlaidConfig.java
```

### Frontend (Angular)

```
src/app/
├── core/                            # Singleton services, app-wide concerns
│   ├── interceptors/
│   │   ├── auth.interceptor.ts      # Cookie/CSRF handling
│   │   └── error.interceptor.ts     # Global error handling
│   ├── guards/
│   │   ├── auth.guard.ts
│   │   └── admin.guard.ts
│   ├── services/
│   │   ├── auth.service.ts          # Login/logout/session
│   │   └── notification.service.ts  # Toast/alerts
│   └── types/
│       └── api.types.ts             # Shared API response types
│
├── features/                        # Feature-sliced, lazy-loaded
│   ├── auth/
│   │   ├── pages/
│   │   │   ├── login/
│   │   │   └── setup-wizard/
│   │   └── auth.routes.ts
│   ├── dashboard/
│   │   ├── pages/
│   │   │   └── dashboard/
│   │   ├── components/
│   │   │   ├── account-summary/
│   │   │   ├── envelope-chart/
│   │   │   └── recent-transactions/
│   │   └── dashboard.routes.ts
│   ├── accounts/
│   │   ├── pages/
│   │   │   ├── account-list/
│   │   │   └── account-detail/
│   │   ├── services/
│   │   │   └── account.service.ts
│   │   └── accounts.routes.ts
│   ├── transactions/
│   │   ├── pages/
│   │   │   └── transaction-list/
│   │   ├── components/
│   │   │   ├── transaction-form/
│   │   │   └── pointing-dialog/
│   │   ├── services/
│   │   │   └── transaction.service.ts
│   │   └── transactions.routes.ts
│   ├── envelopes/
│   │   ├── pages/
│   │   │   └── envelope-list/
│   │   ├── components/
│   │   │   ├── envelope-card/
│   │   │   └── allocation-form/
│   │   ├── services/
│   │   │   └── envelope.service.ts
│   │   └── envelopes.routes.ts
│   ├── debts/
│   │   ├── pages/
│   │   │   └── debt-overview/
│   │   ├── services/
│   │   │   └── debt.service.ts
│   │   └── debts.routes.ts
│   └── admin/
│       ├── pages/
│       │   ├── user-management/
│       │   ├── plaid-connections/
│       │   └── system-health/
│       └── admin.routes.ts
│
├── app.component.ts
├── app.config.ts
└── app.routes.ts                    # Top-level lazy routes
```

### Structure Rationale

- **domain/model/ grouped by aggregate:** Each subdomain (account, transaction, envelope, debt, user) gets its own package. This prevents a flat pile of 20+ domain classes and makes aggregate boundaries explicit.
- **port/in/ one interface per use case:** Keeps use case contracts granular and testable. A controller depends on specific use case ports, not a monolithic service.
- **port/out/ as domain-shaped interfaces:** Repository interfaces use domain language (`findByAccountAndMonth`), not JPA language. The persistence adapter translates.
- **infrastructure/adapter/out/persistence/ with separate JPA entities:** Domain entities stay clean (no `@Entity`, `@Column`). JPA entities live in infrastructure with mappers between layers. This is the "lightweight hexagonal" trade-off -- more mapping code, but domain stays pure.
- **features/ on Angular side mirrors backend domains:** Each feature is lazy-loaded, self-contained, and maps roughly to a backend domain aggregate. Teams (or future contributors) can work on a feature independently.
- **core/ replaces shared/:** Following Angular 2025 conventions, core contains app-wide singletons (guards, interceptors, services), not reusable UI components. Reusable UI comes from PrimeNG.

## Architectural Patterns

### Pattern 1: Port-per-Use-Case (Backend)

**What:** Each business operation gets its own port interface in `domain/port/in/`. Use case services implement exactly one port.
**When to use:** Always -- this is the core hexagonal pattern.
**Trade-offs:** More interfaces (one per use case) but each is focused and independently testable. Prevents god-service classes.

```java
// domain/port/in/ManageEnvelopesUseCase.java
public interface ManageEnvelopesUseCase {
    Envelope createEnvelope(CreateEnvelopeCommand cmd);
    Envelope updateAllocation(UUID envelopeId, Money amount);
    EnvelopeStatus getStatus(UUID envelopeId, YearMonth month);
}

// application/service/EnvelopeService.java
@UseCase // Custom stereotype, not @Service
@Transactional
public class EnvelopeService implements ManageEnvelopesUseCase {
    private final EnvelopeRepository envelopes; // port/out
    private final TransactionRepository transactions; // port/out

    @Override
    public EnvelopeStatus getStatus(UUID envelopeId, YearMonth month) {
        Envelope envelope = envelopes.findById(envelopeId)
            .orElseThrow(() -> new EnvelopeNotFoundException(envelopeId));
        Money spent = transactions.sumByEnvelopeAndMonth(envelopeId, month);
        return envelope.calculateStatus(spent); // Business logic in domain
    }
}
```

### Pattern 2: Abstract Bank Connector (Backend)

**What:** A `BankConnector` port interface abstracts all bank synchronization. Plaid is just one adapter implementing it. The interface uses domain language, not Plaid-specific concepts.
**When to use:** For any external dependency that might change providers.
**Trade-offs:** Extra abstraction layer, but switching from Plaid to Powens/Salt Edge requires only a new adapter, not business logic changes.

```java
// domain/port/out/BankConnector.java
public interface BankConnector {
    List<BankTransaction> fetchTransactions(BankConnectionId connectionId,
                                            LocalDate from, LocalDate to);
    BankConnectionStatus getConnectionStatus(BankConnectionId connectionId);
    LinkToken createLinkToken(UserId userId);
}

// infrastructure/adapter/out/banking/PlaidBankConnector.java
@Component
@ConditionalOnProperty(name = "prosperity.banking.provider", havingValue = "plaid")
public class PlaidBankConnector implements BankConnector {
    // Plaid SDK calls, DTO mapping to domain objects
}
```

### Pattern 3: Dual Entity Model (Backend)

**What:** Domain entities (`domain/model/`) are pure POJOs. JPA entities (`infrastructure/adapter/out/persistence/entity/`) are separate classes with `@Entity` annotations. Mappers translate between them.
**When to use:** In lightweight hexagonal architecture. This is the key decision that keeps the domain free of framework annotations.
**Trade-offs:** Mapping boilerplate (use MapStruct to mitigate). Extra classes. But domain model can evolve without JPA constraints, and domain logic is testable without a database.

```java
// domain/model/transaction/Transaction.java (pure POJO)
public class Transaction {
    private final TransactionId id;
    private final BankAccountId accountId;
    private final Money amount;
    private final TransactionSource source;
    private boolean pointed;

    public void point() {
        if (this.pointed) throw new AlreadyPointedException(this.id);
        this.pointed = true;
    }
}

// infrastructure/adapter/out/persistence/entity/TransactionJpaEntity.java
@Entity
@Table(name = "transactions")
public class TransactionJpaEntity {
    @Id private UUID id;
    @Column(name = "bank_account_id") private UUID bankAccountId;
    @Column(name = "amount_cents") private Long amountCents;
    // ... JPA annotations
}
```

### Pattern 4: Feature-Sliced Lazy Loading (Frontend)

**What:** Each Angular feature is a standalone route tree, lazy-loaded via `loadChildren`. Features own their components, services, and types.
**When to use:** Always for Angular 21+ applications.
**Trade-offs:** Slight complexity in route configuration, but massive benefits: faster initial load, isolated dependencies, independent development.

```typescript
// app.routes.ts
export const routes: Routes = [
  { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
  { path: 'login', loadChildren: () => import('./features/auth/auth.routes') },
  { path: 'dashboard', loadChildren: () => import('./features/dashboard/dashboard.routes'),
    canActivate: [authGuard] },
  { path: 'accounts', loadChildren: () => import('./features/accounts/accounts.routes'),
    canActivate: [authGuard] },
  { path: 'transactions', loadChildren: () => import('./features/transactions/transactions.routes'),
    canActivate: [authGuard] },
  { path: 'envelopes', loadChildren: () => import('./features/envelopes/envelopes.routes'),
    canActivate: [authGuard] },
  { path: 'admin', loadChildren: () => import('./features/admin/admin.routes'),
    canActivate: [authGuard, adminGuard] },
];
```

### Pattern 5: Smart/Dumb Component Split (Frontend)

**What:** Page components (smart) handle data fetching and state. Display components (dumb) receive data via `@Input()` and emit events via `@Output()`. Dumb components are reusable and testable in isolation.
**When to use:** Whenever a component does both data management and rendering.
**Trade-offs:** More components, but each is simple. Testing is straightforward -- dumb components need no service mocking.

## Data Flow

### Request Flow (Read)

```
User clicks "Envelopes"
    |
[Angular Router] --> lazy load envelopes feature
    |
[EnvelopePage] --> EnvelopeService.getAll(accountId)
    |
[HttpClient] --> GET /api/accounts/{id}/envelopes (cookie auth + XSRF header)
    |
[Caddy :443] --> proxy to :8080
    |
[EnvelopeController] --> validate request, extract user from SecurityContext
    |
[ManageEnvelopesUseCase] --> orchestrate domain logic
    |
[EnvelopeRepository port] --> called by use case
    |
[JpaEnvelopeRepository adapter] --> Spring Data query
    |
[PostgreSQL] --> returns rows
    |
[Mapper] --> JPA entity -> domain entity -> DTO
    |
[JSON response] --> back through Caddy to Angular
    |
[EnvelopePage] --> updates component state, renders EnvelopeCard components
```

### Request Flow (Write -- Transaction Import)

```
Plaid webhook OR manual sync trigger
    |
[SyncBankUseCase.syncAccount(connectionId)]
    |
[BankConnector.fetchTransactions()] --> port/out call
    |
[PlaidBankConnector] --> Plaid API /transactions/sync
    |
[Domain deduplication] --> check plaid_transaction_id uniqueness
    |
[TransactionRepository.saveAll()] --> port/out call
    |
[JPA adapter] --> batch INSERT, domain -> JPA entity mapping
    |
[PostgreSQL] --> persisted
    |
[EnvelopeService.recalculate()] --> triggered post-import
    |
Envelope allocations updated based on categorized transactions
```

### Authentication Flow (BFF Cookie)

```
[Angular LoginPage] --> POST /api/auth/login (email + password)
    |
[Spring Security filter chain]
    |
[AuthController] --> validate credentials
    |
[JWT generated server-side] --> stored in HttpSession (never sent to browser)
    |
[Set-Cookie: SESSION=xxx; HttpOnly; Secure; SameSite=Strict]
[Set-Cookie: XSRF-TOKEN=yyy; SameSite=Strict] (readable by Angular)
    |
[Angular HttpClient] --> subsequent requests include:
    - Cookie: SESSION=xxx (automatic by browser)
    - X-XSRF-TOKEN: yyy (set by Angular's HttpClientXsrfModule)
    |
[Spring Security] --> validates session cookie + CSRF token on every request
```

### Key Data Flows

1. **Envelope budget check:** Transaction categorized -> EnvelopeService checks if category matches an envelope -> updates spent amount -> if overspent, flag on dashboard.
2. **Debt calculation:** Transaction on shared account -> split proportionally -> update Debt aggregate -> record in DebtHistory.
3. **Pointing (reconciliation):** User marks manual transaction as "pointed" against an imported Plaid transaction -> both linked, discrepancies flagged.
4. **Dashboard aggregation:** Dashboard controller aggregates from multiple use cases (account balances, envelope statuses, recent transactions, debt summaries) -> single API call or parallel calls from frontend.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1-5 users (target) | Monolith is perfect. Single Spring Boot instance, single PostgreSQL. No caching needed. |
| 5-50 users | Add database indexes on `transactions(bank_account_id, transaction_date)` and `envelopes(bank_account_id)`. Consider Spring Cache for dashboard aggregations. |
| 50+ users | Unlikely for self-hosted family finance. If needed: read replicas for PostgreSQL, Redis session store, connection pooling tuning. |

### Scaling Priorities

1. **First bottleneck: Transaction queries.** The transactions table grows fastest (thousands of rows/month per account). Index on `(bank_account_id, transaction_date)` is essential from day one. Pagination mandatory.
2. **Second bottleneck: Dashboard aggregation.** Multiple queries for a single dashboard view. Solve with materialized summaries or Spring Cache with monthly invalidation, not premature optimization.

## Anti-Patterns

### Anti-Pattern 1: Domain Model Polluted with JPA Annotations

**What people do:** Use `@Entity` classes directly as domain objects, mixing business logic with persistence concerns.
**Why it's wrong:** Domain logic becomes untestable without a database. JPA proxies and lazy loading leak into business rules. Schema changes force domain changes.
**Do this instead:** Separate domain entities (POJOs) from JPA entities. Use mappers between them. The mapping cost is low compared to the testing and evolution benefits.

### Anti-Pattern 2: Fat Controllers

**What people do:** Put business logic in REST controllers -- validation, calculations, multi-step orchestration.
**Why it's wrong:** Controllers become untestable without HTTP context. Business rules are duplicated if another adapter (CLI, scheduler) needs the same logic. Violates hexagonal architecture's driving adapter principle.
**Do this instead:** Controllers should only map HTTP -> domain command, call use case port, and map domain result -> HTTP response. Three lines of code per endpoint method is the ideal.

### Anti-Pattern 3: Shared "God" Service

**What people do:** Create a single `FinanceService` that handles accounts, transactions, envelopes, and debts.
**Why it's wrong:** Violates SRP. Impossible to test one concern without the others. Merge conflicts in team settings.
**Do this instead:** One use case port per bounded context. `ManageEnvelopesUseCase`, `ImportTransactionsUseCase`, etc.

### Anti-Pattern 4: Money as Double/Float

**What people do:** Store and calculate monetary values using floating-point types.
**Why it's wrong:** Rounding errors accumulate. 0.1 + 0.2 != 0.3 in IEEE 754. Financial calculations must be exact.
**Do this instead:** Store as `BIGINT` (cents) in database. Use a `Money` value object in domain that wraps `long` cents with currency. All arithmetic in cents.

### Anti-Pattern 5: Eager Loading Everything

**What people do:** Use `FetchType.EAGER` on JPA relationships or load full transaction history for dashboard.
**Why it's wrong:** N+1 queries. Memory blowup on accounts with years of transaction history.
**Do this instead:** Lazy loading by default. Explicit fetch joins only when needed. Paginate transaction lists. Dashboard uses aggregation queries, not full entity loads.

### Anti-Pattern 6: Frontend Services Calling Multiple Endpoints for One View

**What people do:** Dashboard component makes 5 separate HTTP calls for account summary, envelope status, recent transactions, etc.
**Why it's wrong:** Waterfall requests, slow page load, complex error handling.
**Do this instead:** Backend `DashboardController` aggregates data server-side into a single `DashboardDTO`. One request, one response. The backend is on the same network as the database -- let it do the aggregation.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Plaid API | Adapter behind `BankConnector` port, batch sync mode | Use webhook for new transaction notifications, batch fetch for actual data. Link tokens for OAuth flow. Rate limits apply. |
| Plaid Link (frontend) | Angular component embeds Plaid Link JS SDK | Link token generated server-side, exchanged for access token server-side. Frontend never sees access tokens. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Angular SPA <-> Spring Boot | REST/JSON over HTTPS | Cookie auth, CSRF token. DTOs designed for frontend needs (not domain shape). |
| REST Controller <-> Use Case | Method call via port interface | Controller depends on port/in interface, not service implementation. |
| Use Case <-> Repository | Method call via port interface | Use case depends on port/out interface, not JPA implementation. |
| Domain <-> JPA | Mapper classes | MapStruct recommended. Bidirectional mapping: domain entity <-> JPA entity. |
| Domain <-> Plaid | Mapper in banking adapter | Plaid DTOs -> domain `BankTransaction`. Domain never imports Plaid SDK types. |

## Build Order Implications

The hexagonal architecture creates clear dependency chains that dictate build order:

### Phase Dependencies

```
1. Domain model (entities, VOs, ports)    # No deps, build first
       |
2. Application services (use cases)       # Depends on domain ports
       |
   +---+---+
   |       |
3a. Persistence adapters     3b. REST controllers     # Both depend on domain + app
   (JPA entities, repos)         (DTOs, mapping)
       |
4. Banking adapter                                     # Depends on domain ports
       |
5. Security layer (BFF auth)                           # Cross-cutting, needs controllers
       |
6. Frontend features                                   # Depends on REST API contracts
```

### Suggested Build Phases

1. **Domain + persistence first:** Define entities, value objects, ports, JPA entities, and mappers. This validates the data model before any UI work.
2. **Auth + security second:** BFF cookie flow must work before any protected endpoint is useful. Setup wizard included here.
3. **Core features (accounts, transactions) third:** These are prerequisites for envelopes and debts.
4. **Envelope budgets fourth:** Depends on transactions being categorized and accounts existing.
5. **Bank sync (Plaid) fifth:** Can work with manual transactions first. Plaid integration adds complexity and external dependency.
6. **Dashboard last:** Aggregates from all other features. Build it when there is data to display.

This ordering minimizes rework: each phase builds on stable foundations from the previous one.

## Sources

- [Hexagonal Architecture with Spring Boot - Arho Huttunen](https://www.arhohuttunen.com/hexagonal-architecture-spring-boot/) (package structure, testing strategy, port patterns)
- [Hexagonal Architecture, DDD, and Spring - Baeldung](https://www.baeldung.com/hexagonal-architecture-ddd-spring) (Spring Boot hexagonal patterns)
- [Hexagonal Architecture Best Practices - Medium (Jan 2026)](https://medium.com/but-it-works-on-my-machine/hexagonal-architecture-best-practices-for-spring-boot-developers-6dd2a60602c3) (current best practices)
- [Angular 2025 Project Structure: Features Approach](https://www.ismaelramos.dev/blog/angular-2025-project-structure-with-the-features-approach/) (features-first structure)
- [Angular Best Practices 2026](https://www.ideas2it.com/blogs/angular-development-best-practices) (standalone components, lazy loading)
- [BFF Pattern with Spring Boot + Angular - Dev Genius](https://blog.devgenius.io/implementing-secure-authentication-with-the-bff-pattern-an-angular-and-spring-boot-guide-8e74cbf667bc) (cookie auth, CSRF)
- [Spring Security CSRF Reference](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) (CookieCsrfTokenRepository)
- [Patterns for Accounting - Martin Fowler](https://martinfowler.com/eaaDev/AccountingNarrative.html) (accounting domain patterns)
- [DDD Accounting Domain Model](https://lorenzo-dee.blogspot.com/2013/06/domain-driven-design-accounting-domain.html) (domain modeling for finance)
- [Firefly III - GitHub](https://github.com/firefly-iii/firefly-iii) (reference self-hosted finance app architecture)

---
*Architecture research for: Personal finance management (self-hosted)*
*Researched: 2026-03-28*
