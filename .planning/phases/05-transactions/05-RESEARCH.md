# Phase 5: Transactions - Research

**Researched:** 2026-04-07
**Domain:** Transaction CRUD, pagination, filtering, recurring templates, splits, reconciliation (Spring Data JPA + Angular 21 + PrimeNG)
**Confidence:** HIGH

## Summary

Phase 5 builds on a solid foundation: the `Transaction` entity already exists with all core fields (`amount`, `transactionDate`, `description`, `category`, `bankAccount`, `source`, `state`, `pointed`), and the `TransactionController`/`TransactionService` stubs exist from Phase 4 (category PATCH only). The primary work is: (1) completing CRUD with proper access control mirroring the `AccountService` pattern, (2) adding server-side paginated filtering via Spring Data JPA, (3) new `TransactionSplit` entity + table for split transactions, (4) new `RecurringTemplate` entity + table for recurring transaction templates, and (5) Angular frontend with `p-table` lazy server-side pagination (new pattern for this project).

The security gap identified in CONTEXT.md (D-12) is critical: `TransactionService` currently has zero access control. Every transaction mutation must verify the user has appropriate access to the linked `bankAccount` via `AccountAccessRepository`, following the established 403 vs 404 distinction pattern from `AccountService`.

**Primary recommendation:** Use JPQL with optional filter parameters (not JPA Specifications) for the paginated query since the project already uses JPQL exclusively. New Flyway migrations V012 and V013 for `transaction_splits` and `recurring_templates` tables. Frontend uses `p-table` lazy pagination with external filter form fields.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Transaction entity already complete for CRUD -- no migration for basic CRUD
- D-02: Amounts in centimes (long/NUMERIC) via MoneyConverter -- no float
- D-03: source = TransactionSource.MANUAL for manual transactions
- D-04: New table transaction_splits + entity TransactionSplit required
- D-05: Structure: transaction_splits(id, transaction_id FK, category_id FK, amount NUMERIC, description VARCHAR). Sum of splits must equal parent transaction amount
- D-06: Transaction with active splits has category_id set to null
- D-07: New entity RecurringTemplate + migration V012 required
- D-08: Template fields: account_id, amount, description, category_id, frequency (WEEKLY/MONTHLY/YEARLY), day_of_month (INT), next_due_date (LocalDate), active (boolean)
- D-09: Generate from template creates Transaction with source=RECURRING, updates next_due_date. No automatic batch in Phase 5
- D-10: Access inherits from AccountAccess. CRUD requires WRITE on transaction.bankAccount. Read requires READ
- D-11: TransactionService must integrate AccountAccessRepository with 403 vs 404 pattern from AccountService
- D-12: Current access control in TransactionService is absent -- security gap to fix
- D-13: Spring Data JPA Pageable + JPQL with optional filters, returns Page<Transaction>
- D-14: Filters: accountId (required), dateFrom, dateTo, amountMin, amountMax, categoryId, search (fulltext on description). All optional except accountId
- D-15: Default sort: transactionDate DESC. Default page size: 20
- D-16: Endpoint scoped by account: GET /api/accounts/{accountId}/transactions?page=0&size=20&...
- D-17: Frontend structure: transactions.ts, transaction-dialog.ts, transaction.service.ts, transaction.types.ts
- D-18: CategorySelector reused directly from shared/
- D-19: p-table with server-side pagination [lazy]="true", filters as form fields above table
- D-20: Splits and recurring templates frontend optional if complexity too high -- minimal scope is TXNS-01/02/03/07/08
- D-21: pointed boolean field suffices for manual reconciliation toggle
- D-22: TransactionState.MATCHED used in Phase 7 only. Phase 5 uses MANUAL_UNMATCHED
- D-23: state (Plaid lifecycle) and pointed (bank confirmation) are orthogonal concepts

### Claude's Discretion
- Exact JPQL query structure for filtering (dynamic predicates vs named params)
- Transaction form layout within dialog (field order, date picker format)
- Error messages and form validation UX
- RecurringTemplate API endpoint design (REST resource path)

### Deferred Ideas (OUT OF SCOPE)
- Batch automatique pour templates recurrents -- Phase 7 or backlog
- Suggestion automatique de pointage -- PLAD-09, v2
- Liste cross-comptes des transactions -- Phase 10 (Dashboard)
- Import Plaid et transition pending->posted -- Phase 7
- Regles de categorisation automatique -- CATG-05, v2
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TXNS-01 | Manual transaction creation (amount, date, description, category, account) | Transaction entity exists, CRUD service pattern from AccountService, access control via AccountAccessRepository |
| TXNS-02 | Edit manual transaction | Same CRUD pattern, WRITE access check, partial update via request DTO |
| TXNS-03 | Delete manual transaction | DELETE with WRITE access check, only MANUAL source deletable |
| TXNS-04 | Recurring transaction templates | New RecurringTemplate entity + V012 migration, frequency enum, generate button |
| TXNS-05 | Manual reconciliation (pointage) | Existing pointed boolean field, simple PATCH toggle endpoint |
| TXNS-06 | Split transaction across categories | New TransactionSplit entity + V013 migration, sum validation, category_id null on parent |
| TXNS-07 | Search and filter transactions | JPQL with optional parameters + Pageable, fulltext on description via ILIKE |
| TXNS-08 | Paginated transaction list | Spring Data Page<T>, p-table lazy pagination, server-side sorting |
</phase_requirements>

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Spring Data JPA | 4.0.x (via Boot 4.0.5) | Pageable + Page<T> for pagination, JpaRepository | Already used throughout project |
| Spring Boot Validation | 4.0.x | @Valid on request DTOs | Already used in CategoryController |
| PrimeNG TableModule | 21.x | p-table with lazy server-side pagination | Already used in accounts/categories pages |

### Supporting (already available)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| MoneyConverter | project | BigDecimal <-> Money mapping | All amount fields in DTOs and entities |
| AccountAccessRepository | project | Access control checks | Every transaction mutation and read |
| CategorySelector | project | Category picker component | Transaction create/edit dialog |

### No New Dependencies Required
This phase requires zero new Maven or npm dependencies. Everything needed is already in the project via `spring-boot-starter-data-jpa` (Pageable, Page, @Query) and PrimeNG (TableModule with lazy pagination).

## Architecture Patterns

### Project Structure (additions to existing)
```
backend/src/main/java/com/prosperity/
├── transaction/
│   ├── Transaction.java              # EXISTS - no changes
│   ├── TransactionRepository.java     # EXISTS - add filtered queries
│   ├── TransactionService.java        # EXISTS - complete with CRUD + access control
│   ├── TransactionController.java     # EXISTS - complete with REST endpoints
│   ├── TransactionNotFoundException.java  # EXISTS
│   ├── TransactionSplit.java          # NEW - split entity
│   ├── TransactionSplitRepository.java    # NEW
│   ├── CreateTransactionRequest.java  # NEW - request DTO record
│   ├── UpdateTransactionRequest.java  # NEW - request DTO record
│   ├── TransactionResponse.java       # NEW - response DTO record
│   ├── TransactionSplitRequest.java   # NEW - split DTO record
│   ├── TransactionSplitResponse.java  # NEW - split DTO record
│   ├── TransactionFilterParams.java   # NEW - filter params record
│   └── UpdateTransactionCategoryRequest.java  # EXISTS (Phase 4)
├── recurring/
│   ├── RecurringTemplate.java         # NEW - entity
│   ├── RecurringTemplateRepository.java   # NEW
│   ├── RecurringTemplateService.java  # NEW
│   ├── RecurringTemplateController.java   # NEW
│   ├── CreateRecurringTemplateRequest.java  # NEW
│   ├── UpdateRecurringTemplateRequest.java  # NEW
│   ├── RecurringTemplateResponse.java     # NEW
│   └── RecurringTemplateNotFoundException.java  # NEW
├── shared/
│   ├── TransactionSource.java         # EXISTS - RECURRING value already present
│   ├── TransactionState.java          # EXISTS
│   ├── Money.java                     # EXISTS
│   ├── MoneyConverter.java            # EXISTS
│   └── RecurrenceFrequency.java       # NEW - enum WEEKLY/MONTHLY/YEARLY
frontend/src/app/
├── transactions/
│   ├── transactions.ts                # NEW - page component with p-table lazy
│   ├── transaction-dialog.ts          # NEW - create/edit dialog
│   ├── transaction.service.ts         # NEW - HttpClient + signals
│   ├── transaction.types.ts           # NEW - TypeScript interfaces
│   ├── transactions.spec.ts           # NEW - component tests
│   ├── transaction-dialog.spec.ts     # NEW
│   └── transaction.service.spec.ts    # NEW
```

### Pattern 1: Access-Controlled Transaction CRUD
**What:** Every transaction operation checks user access to the linked bank account via `AccountAccessRepository`
**When to use:** All create/read/update/delete operations on transactions
**Example:**
```java
// Pattern from AccountService — replicate for TransactionService
public TransactionResponse getTransaction(UUID transactionId, String userEmail) {
    User user = resolveUser(userEmail);
    Transaction transaction = transactionRepository.findById(transactionId)
        .orElseThrow(() -> new TransactionNotFoundException("Transaction introuvable : " + transactionId));

    UUID accountId = transaction.getBankAccount().getId();
    if (!accountRepository.hasAccess(accountId, user.getId(), List.of(AccessLevel.READ, AccessLevel.WRITE, AccessLevel.ADMIN))) {
        if (accountRepository.existsById(accountId)) {
            throw new AccountAccessDeniedException("Access denied to account: " + accountId);
        }
        throw new AccountNotFoundException("Account not found: " + accountId);
    }
    return toResponse(transaction);
}
```

### Pattern 2: JPQL Paginated Filtering with Optional Parameters
**What:** Single JPQL query with optional WHERE clauses using null-check pattern
**When to use:** GET /api/accounts/{accountId}/transactions with filters
**Example:**
```java
@Query("""
    SELECT t FROM Transaction t
    LEFT JOIN FETCH t.category
    WHERE t.bankAccount.id = :accountId
    AND (:dateFrom IS NULL OR t.transactionDate >= :dateFrom)
    AND (:dateTo IS NULL OR t.transactionDate <= :dateTo)
    AND (:amountMin IS NULL OR t.amount >= :amountMin)
    AND (:amountMax IS NULL OR t.amount <= :amountMax)
    AND (:categoryId IS NULL OR t.category.id = :categoryId)
    AND (:search IS NULL OR LOWER(t.description) LIKE LOWER(CONCAT('%', :search, '%')))
    """)
Page<Transaction> findByFilters(
    @Param("accountId") UUID accountId,
    @Param("dateFrom") LocalDate dateFrom,
    @Param("dateTo") LocalDate dateTo,
    @Param("amountMin") Money amountMin,
    @Param("amountMax") Money amountMax,
    @Param("categoryId") UUID categoryId,
    @Param("search") String search,
    Pageable pageable);
```
**Confidence:** HIGH -- this is standard Spring Data JPA pattern. The `IS NULL` check makes parameters optional.

**Note on Money filtering:** The `amountMin`/`amountMax` parameters need to be `BigDecimal` (not `Money`) in the JPQL query since the column is `NUMERIC(19,4)`. The converter handles Money-to-BigDecimal for the entity field, but for query parameters, pass raw `BigDecimal` values.

### Pattern 3: p-table Server-Side Lazy Pagination (NEW pattern for project)
**What:** PrimeNG p-table with `[lazy]="true"` triggering server-side loads
**When to use:** Transaction list page
**Example:**
```typescript
// In transactions.ts template
<p-table
  [value]="transactions()"
  [lazy]="true"
  [paginator]="true"
  [rows]="pageSize"
  [totalRecords]="totalRecords()"
  [loading]="loading()"
  (onLazyLoad)="loadTransactions($event)"
  [sortField]="'transactionDate'"
  [sortOrder]="-1"
  styleClass="p-datatable-sm"
>

// In component class
loadTransactions(event: TableLazyLoadEvent): void {
  const page = (event.first ?? 0) / (event.rows ?? 20);
  const size = event.rows ?? 20;
  this.transactionService
    .getTransactions(this.accountId, page, size, this.filters())
    .pipe(takeUntilDestroyed(this.destroyRef))
    .subscribe({
      next: (response) => {
        this.transactionsSignal.set(response.content);
        this.totalRecords.set(response.totalElements);
        this.loading.set(false);
      },
      error: () => { this.loading.set(false); this.error.set('...'); }
    });
}
```

### Pattern 4: Split Transaction Validation
**What:** Service validates that split amounts sum to parent transaction amount
**When to use:** Create/update transaction with splits
**Example:**
```java
private void validateSplits(Transaction transaction, List<TransactionSplitRequest> splits) {
    BigDecimal total = splits.stream()
        .map(s -> s.amount().amount())
        .reduce(BigDecimal.ZERO, BigDecimal::add);
    if (total.compareTo(transaction.getAmount().amount()) != 0) {
        throw new IllegalArgumentException(
            "La somme des splits (" + total + ") ne correspond pas au montant de la transaction (" + transaction.getAmount().amount() + ")");
    }
}
```

### Anti-Patterns to Avoid
- **Fetching all transactions then filtering in Java:** Always filter at the database level with JPQL. Transactions will be the largest table.
- **Using JPA Specification API:** The project uses JPQL exclusively. Don't introduce Specifications for consistency.
- **SecurityContextHolder in Service:** The project passes `userEmail` from controller. Never access SecurityContext in services.
- **Allowing deletion of non-MANUAL transactions:** Only transactions with `source = MANUAL` should be deletable/editable in Phase 5. PLAID and RECURRING-sourced transactions have different lifecycle rules.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Pagination | Custom offset/limit logic | Spring Data `Pageable` + `Page<T>` | Handles page calculation, total count, sorting automatically |
| Money serialization | Custom JSON serializer | Jackson with `BigDecimal` in response DTOs | Money.amount() returns BigDecimal, serialize directly |
| Access control | Custom filter in every query | Reuse `AccountRepository.hasAccess()` | Already tested, handles all access levels |
| Category picker | Build new dropdown | Reuse `CategorySelector` from `shared/` | Already emits UUID, ready to integrate |
| CSRF handling | Manual token management | Spring Security auto-cookie + Angular interceptor | Already configured in Phase 2 |

## Common Pitfalls

### Pitfall 1: Missing Access Control on Transaction Read
**What goes wrong:** Transactions are readable by anyone who knows the UUID, bypassing account permissions
**Why it happens:** TransactionService currently has no access checks (D-12 security gap)
**How to avoid:** Every TransactionService method must resolve the user, get the transaction's bankAccount, and check access via `accountRepository.hasAccess()`
**Warning signs:** Tests pass without setting up AccountAccess entries

### Pitfall 2: Money Type Mismatch in JPQL Filters
**What goes wrong:** JPQL query fails because `Money` value object is used as parameter but the column stores `NUMERIC`
**Why it happens:** The `MoneyConverter` only applies to entity fields, not query parameters
**How to avoid:** Use `BigDecimal` for amount filter parameters in JPQL queries, not `Money`
**Warning signs:** ClassCastException or type mismatch errors in filter queries

### Pitfall 3: N+1 Queries on Category Fetch
**What goes wrong:** Each transaction in a paginated list triggers a separate query to load its category
**Why it happens:** `category` is `FetchType.LAZY` on the Transaction entity
**How to avoid:** Use `LEFT JOIN FETCH t.category` in the paginated query JPQL
**Warning signs:** Hibernate log shows dozens of SELECT statements per page load

### Pitfall 4: Split Sum Validation with BigDecimal
**What goes wrong:** Split sum comparison fails due to scale differences (10.00 != 10.0000)
**Why it happens:** BigDecimal.equals() checks both value AND scale
**How to avoid:** Use `compareTo()` for BigDecimal equality, not `equals()`
**Warning signs:** Valid splits rejected as "sum mismatch"

### Pitfall 5: Pageable Count Query Performance
**What goes wrong:** The count query for pagination re-executes all JOINs including FETCH joins
**Why it happens:** Spring Data auto-generates count query from the main query
**How to avoid:** Add `countQuery` parameter to `@Query` annotation with a simpler count query (no FETCH, no unnecessary JOINs)
**Warning signs:** Slow response times on paginated list endpoint

### Pitfall 6: Frontend Route Scoping
**What goes wrong:** Transaction list route doesn't have access to accountId
**Why it happens:** Route path `/accounts/:accountId/transactions` needs parameter extraction
**How to avoid:** Use `ActivatedRoute` with `params` or `input()` binding from route params. Ensure the route is nested or uses proper parameter passing
**Warning signs:** accountId is undefined in component

### Pitfall 7: CSRF Token on DELETE Requests
**What goes wrong:** DELETE requests return 403 Forbidden
**Why it happens:** Missing CSRF token on mutating requests
**How to avoid:** Angular HttpClient interceptor already handles CSRF via XSRF-TOKEN cookie -- ensure DELETE uses the same interceptor pipeline
**Warning signs:** POST/PUT work but DELETE fails with 403

## Code Examples

### Flyway V012: Transaction Splits Table
```sql
-- V012__create_transaction_splits.sql
CREATE TABLE transaction_splits (
    id UUID PRIMARY KEY,
    transaction_id UUID NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    category_id UUID NOT NULL REFERENCES categories(id),
    amount NUMERIC(19,4) NOT NULL,
    description VARCHAR(500),
    CONSTRAINT fk_split_transaction FOREIGN KEY (transaction_id) REFERENCES transactions(id)
);

CREATE INDEX idx_transaction_splits_transaction_id ON transaction_splits(transaction_id);
```

### Flyway V013: Recurring Templates Table
```sql
-- V013__create_recurring_templates.sql
CREATE TABLE recurring_templates (
    id UUID PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES bank_accounts(id),
    amount NUMERIC(19,4) NOT NULL,
    description VARCHAR(500),
    category_id UUID REFERENCES categories(id),
    frequency VARCHAR(20) NOT NULL,
    day_of_month INT,
    next_due_date DATE NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_recurring_templates_account_id ON recurring_templates(account_id);
CREATE INDEX idx_recurring_templates_next_due_date ON recurring_templates(next_due_date);
```

### Request/Response DTOs (Java Records)
```java
// CreateTransactionRequest.java
public record CreateTransactionRequest(
    @NotNull BigDecimal amount,
    @NotNull LocalDate transactionDate,
    @Size(max = 500) String description,
    UUID categoryId
) {}

// TransactionResponse.java
public record TransactionResponse(
    UUID id,
    UUID accountId,
    BigDecimal amount,
    String description,
    UUID categoryId,
    String categoryName,
    LocalDate transactionDate,
    TransactionSource source,
    TransactionState state,
    boolean pointed,
    Instant createdAt,
    List<TransactionSplitResponse> splits
) {}
```

### Frontend Transaction Service with Pagination
```typescript
// transaction.service.ts
@Injectable({ providedIn: 'root' })
export class TransactionService {
  private readonly http = inject(HttpClient);

  getTransactions(
    accountId: string,
    page: number,
    size: number,
    filters: TransactionFilters,
  ): Observable<Page<TransactionResponse>> {
    let params = new HttpParams()
      .set('page', page)
      .set('size', size);
    if (filters.dateFrom) params = params.set('dateFrom', filters.dateFrom);
    if (filters.dateTo) params = params.set('dateTo', filters.dateTo);
    if (filters.amountMin != null) params = params.set('amountMin', filters.amountMin);
    if (filters.amountMax != null) params = params.set('amountMax', filters.amountMax);
    if (filters.categoryId) params = params.set('categoryId', filters.categoryId);
    if (filters.search) params = params.set('search', filters.search);

    return this.http.get<Page<TransactionResponse>>(
      `/api/accounts/${accountId}/transactions`,
      { params }
    );
  }
}

// Page interface (Spring Data Page JSON structure)
export interface Page<T> {
  content: T[];
  totalElements: number;
  totalPages: number;
  number: number;
  size: number;
}
```

## Discretion Recommendations

### JPQL Query Structure: Optional Parameters with IS NULL
**Recommendation:** Use the `(:param IS NULL OR ...)` pattern in a single JPQL query rather than building dynamic queries with Specifications or Criteria API. This is consistent with the project's JPQL-only approach and avoids introducing a new pattern. The IS NULL trick makes each filter optional -- when null is passed, the clause becomes a no-op.

### RecurringTemplate API Endpoint Path
**Recommendation:** Use `/api/accounts/{accountId}/recurring-templates` (scoped by account) rather than `/api/recurring-templates`. This is consistent with D-16 (transactions scoped by account) and ensures access control is naturally enforced through the accountId path parameter. It also prepares the UI for a per-account view.

### Transaction Form Layout
**Recommendation:** Order fields as: Amount (p-inputnumber, currency mode) > Date (p-datepicker, default today) > Description (text input) > Category (CategorySelector). This follows the natural flow of entering a transaction -- the most important field first.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework (backend) | JUnit 5 + MockMvc + Testcontainers PostgreSQL 17 |
| Framework (frontend) | Vitest + Angular TestBed |
| Config file (backend) | `backend/src/test/java/com/prosperity/TestcontainersConfig.java` |
| Quick run command (backend) | `./mvnw test -pl backend -Dtest=TransactionControllerTest` |
| Quick run command (frontend) | `pnpm test -- --run transactions` |
| Full suite command | `./mvnw verify && pnpm test` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TXNS-01 | Create manual transaction | integration | `./mvnw test -pl backend -Dtest=TransactionControllerTest#create_*` | Wave 0 |
| TXNS-02 | Edit manual transaction | integration | `./mvnw test -pl backend -Dtest=TransactionControllerTest#update_*` | Wave 0 |
| TXNS-03 | Delete manual transaction | integration | `./mvnw test -pl backend -Dtest=TransactionControllerTest#delete_*` | Wave 0 |
| TXNS-04 | Recurring templates CRUD + generate | integration | `./mvnw test -pl backend -Dtest=RecurringTemplateControllerTest` | Wave 0 |
| TXNS-05 | Toggle pointed boolean | integration | `./mvnw test -pl backend -Dtest=TransactionControllerTest#toggle_pointed_*` | Wave 0 |
| TXNS-06 | Split transaction across categories | integration | `./mvnw test -pl backend -Dtest=TransactionControllerTest#split_*` | Wave 0 |
| TXNS-07 | Filter by date/amount/category/description | integration | `./mvnw test -pl backend -Dtest=TransactionControllerTest#filter_*` | Wave 0 |
| TXNS-08 | Paginated list | integration | `./mvnw test -pl backend -Dtest=TransactionControllerTest#list_paginated_*` | Wave 0 |
| TXNS-01/02 | Frontend create/edit dialog | component | `pnpm test -- --run transaction-dialog` | Wave 0 |
| TXNS-07/08 | Frontend paginated table + filters | component | `pnpm test -- --run transactions` | Wave 0 |

### Sampling Rate
- **Per task commit:** `./mvnw test -pl backend -Dtest=TransactionControllerTest && pnpm test -- --run`
- **Per wave merge:** `./mvnw verify && pnpm test`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `backend/src/test/java/com/prosperity/transaction/TransactionControllerTest.java` -- covers TXNS-01/02/03/05/06/07/08
- [ ] `backend/src/test/java/com/prosperity/recurring/RecurringTemplateControllerTest.java` -- covers TXNS-04
- [ ] `frontend/src/app/transactions/transactions.spec.ts` -- covers TXNS-07/08 frontend
- [ ] `frontend/src/app/transactions/transaction-dialog.spec.ts` -- covers TXNS-01/02 frontend
- [ ] `frontend/src/app/transactions/transaction.service.spec.ts` -- covers service layer

## Open Questions

1. **Amount filter with Money converter**
   - What we know: The `amount` column is `NUMERIC(19,4)` and the entity uses `@Convert(converter = MoneyConverter.class)`. JPQL filter parameters should be `BigDecimal`.
   - What's unclear: Whether Hibernate 7 (via Boot 4.0) handles the converter transparently in WHERE clauses with `>=` and `<=` comparisons on converted fields.
   - Recommendation: Test with a simple integration test early. If the converter is not applied to query params, use a native query or explicit BigDecimal conversion in the service layer.

2. **Transaction list endpoint path restructuring**
   - What we know: Current `TransactionController` is at `/api/transactions`. D-16 wants `/api/accounts/{accountId}/transactions`.
   - What's unclear: Whether to create a new controller or update the existing one. The existing PATCH `/api/transactions/{id}/category` (Phase 4) stays at its current path.
   - Recommendation: Keep existing `TransactionController` at `/api/transactions` for single-transaction operations (GET by id, PATCH, DELETE). Add the list/create endpoints on a new path in the same controller using `@GetMapping` and `@PostMapping` at the account-scoped path. Or use a dedicated method with the full path. The controller can have methods mapped to different base paths using method-level `@RequestMapping`.

## Project Constraints (from CLAUDE.md)

- **Open source:** All deps MIT or Apache 2.0 -- no new deps needed for this phase
- **Self-hosted:** No cloud services
- **Java 21 LTS:** Records for DTOs, no Lombok
- **Layered by feature:** Controller/Service/Repository per feature package
- **Money as BigDecimal:** Via MoneyConverter, no floats
- **Connecteur bancaire abstrait:** Not relevant for this phase (manual transactions only)
- **Testing:** Follow testing-principles.md (AAA, DAMP, observable behavior, boundary values)
- **Angular 21:** Signals, OnPush, standalone components, Vitest
- **PrimeNG 21:** p-table, p-dialog, p-inputnumber, p-datepicker

## Sources

### Primary (HIGH confidence)
- Existing codebase: `AccountService.java`, `AccountRepository.java`, `CategoryController.java` -- established patterns
- Existing codebase: `Transaction.java`, `TransactionRepository.java`, `TransactionService.java` -- current state
- Existing codebase: `V005__create_transactions.sql`, `V007__migrate_money_columns_to_numeric.sql` -- DB schema
- CONTEXT.md decisions D-01 through D-23 -- locked implementation decisions
- Spring Data JPA Pageable/Page -- standard API, well-known behavior

### Secondary (MEDIUM confidence)
- JPQL IS NULL pattern for optional filters -- widely used pattern but not yet used in this project
- PrimeNG p-table lazy pagination -- documented in PrimeNG docs, not yet used in this project

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in project, no new dependencies
- Architecture: HIGH -- follows established patterns from Phase 3/4, well-documented in CONTEXT.md
- Pitfalls: HIGH -- based on direct code analysis of existing codebase patterns
- Pagination: MEDIUM -- first use of Pageable/Page in project, JPQL filter pattern needs validation

**Research date:** 2026-04-07
**Valid until:** 2026-05-07 (stable -- no external API or version changes expected)
