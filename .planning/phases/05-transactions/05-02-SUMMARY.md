---
phase: 05-transactions
plan: 02
subsystem: api
tags: [transaction, crud, access-control, pagination, spring-boot, jpa]

# Dependency graph
requires:
  - phase: 05-01
    provides: Transaction entity, TransactionRepository with paginated filter query, DTO records
  - phase: 03-accounts
    provides: AccountRepository.hasAccess, AccountAccessDeniedException, AccountNotFoundException, 403-vs-404 pattern

provides:
  - TransactionService with 7 public methods (createTransaction, getTransactions, getTransaction, updateTransaction, deleteTransaction, togglePointed, updateCategory)
  - TransactionController with 7 REST endpoints scoped by account
  - 403-vs-404 access control pattern replicated from AccountService on all transaction operations

affects: [05-03, 05-04, 05-05, 05-06, future-plaid-integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "requireAccountAccess helper: filters AccessLevel.values() by isAtLeast(minimumLevel) then calls hasAccess; throws 403 if exists, 404 otherwise"
    - "TransactionController uses @RequestMapping('/api') to cover two path patterns: /api/accounts/{accountId}/transactions and /api/transactions/{id}"
    - "Principal.getName() passed through controller to service (not @AuthenticationPrincipal UserDetails)"

key-files:
  created: []
  modified:
    - backend/src/main/java/com/prosperity/transaction/TransactionService.java
    - backend/src/main/java/com/prosperity/transaction/TransactionController.java

key-decisions:
  - "TransactionController uses @RequestMapping('/api') not '/api/transactions' to accommodate two path roots (accounts/{id}/transactions and transactions/{id})"
  - "requireAccountAccess in TransactionService mirrors AccountService pattern with Arrays.stream(AccessLevel.values()).filter(l -> l.isAtLeast(minimumLevel)) to build allowed levels set"
  - "Pointage toggle requires WRITE access per D-21 (not just READ)"
  - "findByFilters called with BigDecimal params directly (not Money) -- TransactionRepository signature uses BigDecimal for amount comparisons"

patterns-established:
  - "requireAccountAccess private helper: reusable 403-vs-404 distinction for any service needing account access checks"
  - "Page<TransactionResponse> via page.map(this::toResponse): clean functional mapping for paginated responses"

requirements-completed: [TXNS-01, TXNS-02, TXNS-03, TXNS-05, TXNS-07, TXNS-08]

# Metrics
duration: 8min
completed: 2026-04-07
---

# Phase 05 Plan 02: TransactionService and TransactionController Summary

**Full transaction CRUD with 403-vs-404 access control, MANUAL-only edit/delete constraint, pointage toggle, and paginated filtered listing across 7 REST endpoints**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-07T05:00:00Z
- **Completed:** 2026-04-07T05:08:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- TransactionService with 7 public methods, all enforcing access control via `requireAccountAccess` helper that replicates AccountService's 403-vs-404 pattern
- TransactionController with 7 REST endpoints: POST returns 201, DELETE returns 204, PATCH /category updated to pass Principal
- MANUAL-only guard on updateTransaction and deleteTransaction throws `IllegalStateException` mapped to 400 by controller

## Task Commits

1. **Task 1: TransactionService** - `eb4e5d3` (feat)
2. **Task 2: TransactionController** - `b98065b` (feat)

## Files Created/Modified

- `backend/src/main/java/com/prosperity/transaction/TransactionService.java` - Full CRUD service with access control, pagination, and pointage toggle
- `backend/src/main/java/com/prosperity/transaction/TransactionController.java` - 7 REST endpoints with exception handlers for 403/404/400

## Decisions Made

- `TransactionController` uses `@RequestMapping("/api")` instead of `/api/transactions` to accommodate two path roots: `/api/accounts/{accountId}/transactions` (list/create) and `/api/transactions/{id}` (single-transaction ops)
- `requireAccountAccess` uses `Arrays.stream(AccessLevel.values()).filter(l -> l.isAtLeast(minimumLevel))` to build the allowed levels collection — same pattern would be reusable for other services
- Pointage toggle requires WRITE access per D-21
- `findByFilters` called with `BigDecimal` params directly (no `Money` conversion needed at service layer — repository signature uses `BigDecimal` for JPQL comparisons)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Controller updated in same pass as service to fix compilation**
- **Found during:** Task 1 compilation verification
- **Issue:** Existing `TransactionController.updateCategory` still called old 2-arg signature; adding `userEmail` to `TransactionService.updateCategory` broke compilation
- **Fix:** Task 2 (TransactionController rewrite) executed immediately during Task 1 verification to unblock compile check. Both tasks were committed separately as planned.
- **Files modified:** `backend/src/main/java/com/prosperity/transaction/TransactionController.java`
- **Verification:** `./mvnw compile -q` exits 0
- **Committed in:** b98065b (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking — compile order)
**Impact on plan:** Controller written in same session as service to resolve compilation dependency. Both committed as separate atomic commits as specified by the plan.

## Issues Encountered

None beyond the compile-order dependency above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- TransactionService and TransactionController fully functional
- Access control enforced on every transaction operation
- Ready for integration tests (05-03) and frontend implementation (05-04+)
- No stubs: all 7 methods wired to real repository calls with real access control checks

---
*Phase: 05-transactions*
*Completed: 2026-04-07*
