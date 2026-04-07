---
phase: 05-transactions
plan: 04
subsystem: api, testing
tags: [integration-tests, testcontainers, postgresql, mockMvc, split-transactions, native-sql]

# Dependency graph
requires:
  - phase: 05-01
    provides: TransactionSplit entity, TransactionSplitRepository, DTO records, TransactionRepository.findByFilters
  - phase: 05-02
    provides: TransactionService CRUD with access control, TransactionController endpoints
  - phase: 05-03
    provides: RecurringTemplateService and RecurringTemplateController with CRUD + generate
provides:
  - Split transaction logic in TransactionService (setSplits, clearSplits, getSplits)
  - Split REST endpoints (PUT/DELETE/GET /api/transactions/{id}/splits)
  - 17 integration tests for TransactionController covering TXNS-01/02/03/05/06/07/08
  - 7 integration tests for RecurringTemplateController covering TXNS-04
  - Native SQL query fix for TransactionRepository.findByFilters (PostgreSQL type cast issue)
affects: [05-06, future-plaid-integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Native SQL with explicit CAST for optional filter parameters in PostgreSQL (avoids Hibernate bytea type inference bug)"
    - "DirtiesContext.AFTER_EACH_TEST_METHOD for integration tests with shared Testcontainers PostgreSQL"
    - "createTransactionViaApi helper pattern: full HTTP stack round-trip in test setup for consistent state"

key-files:
  created:
    - backend/src/test/java/com/prosperity/transaction/TransactionControllerTest.java
    - backend/src/test/java/com/prosperity/recurring/RecurringTemplateControllerTest.java
  modified:
    - backend/src/main/java/com/prosperity/transaction/TransactionService.java
    - backend/src/main/java/com/prosperity/transaction/TransactionController.java
    - backend/src/main/java/com/prosperity/transaction/TransactionRepository.java
    - backend/src/test/java/com/prosperity/transaction/TransactionCategoryTest.java

key-decisions:
  - "Switched TransactionRepository.findByFilters from JPQL to native SQL with explicit PostgreSQL CAST to resolve lower(bytea) type inference bug when null parameters are passed"
  - "Sort property changed to column name (transaction_date) in TransactionController to match native SQL query"
  - "Fixed Phase 4 TransactionCategoryTest to include AccountAccess setup after Phase 5 access control enforcement"

patterns-established:
  - "Native SQL with CAST(:param AS type) IS NULL pattern for optional filter parameters in PostgreSQL"
  - "Integration test helper pattern: createXxxViaApi returns UUID, exercises full HTTP stack"

requirements-completed: [TXNS-01, TXNS-02, TXNS-03, TXNS-04, TXNS-05, TXNS-06, TXNS-07, TXNS-08]

# Metrics
duration: 36min
completed: 2026-04-07
---

# Phase 05 Plan 04: Split Logic and Integration Tests Summary

**Split transaction logic with sum validation (compareTo) and category nullification, plus 24 integration tests covering all 8 TXNS requirements via Testcontainers PostgreSQL**

## Performance

- **Duration:** 36 min
- **Started:** 2026-04-07T04:10:47Z
- **Completed:** 2026-04-07T04:46:47Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Split transaction logic: setSplits validates sum equals parent amount via compareTo, nullifies parent category (D-06), clearSplits removes all splits, getSplits returns split details
- 17 TransactionController integration tests: create (201), access denied (403), not found (404), invalid category (404), pagination, 4 filter types, update, update non-manual (400), delete, delete non-manual (400), pointage toggle, splits valid sum, splits invalid sum (400), clear splits
- 7 RecurringTemplateController integration tests: create (201), list active only, update, delete (204), generate with nextDueDate advance, inactive generate (400), access denied (403)
- Fixed pre-existing JPQL bug: TransactionRepository.findByFilters lower(bytea) error resolved by switching to native SQL with explicit PostgreSQL type casts

## Task Commits

Each task was committed atomically:

1. **Task 1: Split logic + endpoints** - `579782d` (feat) -- committed by prior executor
2. **Task 2: Integration tests + bug fixes** - `5cf8eb3` (test)

## Files Created/Modified

- `backend/src/test/java/com/prosperity/transaction/TransactionControllerTest.java` - 17 integration tests for all transaction endpoints
- `backend/src/test/java/com/prosperity/recurring/RecurringTemplateControllerTest.java` - 7 integration tests for recurring template endpoints
- `backend/src/main/java/com/prosperity/transaction/TransactionService.java` - setSplits, clearSplits, getSplits methods (from Task 1)
- `backend/src/main/java/com/prosperity/transaction/TransactionController.java` - PUT/DELETE/GET splits endpoints + sort fix
- `backend/src/main/java/com/prosperity/transaction/TransactionRepository.java` - JPQL to native SQL with CAST for null-safe filtering
- `backend/src/test/java/com/prosperity/transaction/TransactionCategoryTest.java` - Added AccountAccess setup for access control

## Decisions Made

- Switched findByFilters from JPQL to native SQL: Hibernate sends null parameters as bytea type to PostgreSQL, causing `lower(bytea) does not exist` error. Native SQL with explicit `CAST(:param AS type)` resolves the type ambiguity.
- Sort property uses column name `transaction_date` instead of Java field name `transactionDate` for native query compatibility.
- Fixed Phase 4 TransactionCategoryTest: Phase 5 added access control to updateCategory, breaking 4 tests that lacked AccountAccess setup.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] TransactionRepository lower(bytea) type inference error**
- **Found during:** Task 2 (integration test execution)
- **Issue:** JPQL `LOWER(t.description) LIKE LOWER(CONCAT('%', :search, '%'))` fails when :search is null because Hibernate/PostgreSQL infers null as bytea type
- **Fix:** Switched to native SQL query with explicit `CAST(:search AS text)` for all nullable parameters
- **Files modified:** `backend/src/main/java/com/prosperity/transaction/TransactionRepository.java`
- **Verification:** All 143 tests pass including filter tests
- **Committed in:** 5cf8eb3

**2. [Rule 1 - Bug] TransactionController sort property incompatible with native query**
- **Found during:** Task 2 (integration test execution)
- **Issue:** Sort.by("transactionDate") produced `ORDER BY t.transactionDate` in native SQL, but column name is `transaction_date`
- **Fix:** Changed sort property to `transaction_date`
- **Files modified:** `backend/src/main/java/com/prosperity/transaction/TransactionController.java`
- **Verification:** Pagination tests pass with correct sort order
- **Committed in:** 5cf8eb3

**3. [Rule 1 - Bug] TransactionCategoryTest missing AccountAccess after Phase 5 access control**
- **Found during:** Task 2 (full test suite verification)
- **Issue:** Phase 4 tests for PATCH /transactions/{id}/category returned 403 because Phase 5 added access control to updateCategory
- **Fix:** Added AccountAccess(WRITE) setup in 4 affected test methods
- **Files modified:** `backend/src/test/java/com/prosperity/transaction/TransactionCategoryTest.java`
- **Verification:** All 6 TransactionCategoryTest tests pass
- **Committed in:** 5cf8eb3

---

**Total deviations:** 3 auto-fixed (3 bugs)
**Impact on plan:** All fixes necessary for test suite correctness. The JPQL bug was pre-existing from Plan 05-01 but only manifested during integration testing against real PostgreSQL. No scope creep.

## Issues Encountered

None beyond the auto-fixed bugs above.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None - all endpoints and test methods are fully implemented with real database operations.

## Next Phase Readiness

- All 8 TXNS requirements covered by 24 integration tests
- Full test suite (143 tests) passes green
- Ready for Plan 05-06 (verification/completion)

## Self-Check: PASSED

All files verified on disk. Both commits verified in git log.
- 579782d: FOUND
- 5cf8eb3: FOUND

---
*Phase: 05-transactions*
*Completed: 2026-04-07*
