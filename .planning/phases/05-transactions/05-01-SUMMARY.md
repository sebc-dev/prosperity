---
phase: 05-transactions
plan: 01
subsystem: database
tags: [flyway, jpa, hibernate, postgresql, spring-data, jpql, pagination]

# Dependency graph
requires:
  - phase: 04-categories
    provides: Category entity and categories table for FK references
  - phase: 03-accounts
    provides: Account entity and bank_accounts table for FK references
  - phase: 01-foundation
    provides: Money value object, MoneyConverter, TransactionSource, TransactionState enums, Transaction entity
provides:
  - transaction_splits DDL (V012 Flyway migration)
  - recurring_templates DDL (V013 Flyway migration)
  - TransactionSplit JPA entity
  - TransactionSplitRepository (findByTransactionId, deleteByTransactionId)
  - RecurringTemplate JPA entity
  - RecurringTemplateRepository (findByBankAccountIdAndActiveTrue, findByBankAccountId)
  - RecurrenceFrequency enum (WEEKLY, MONTHLY, YEARLY)
  - RecurringTemplateNotFoundException
  - 7 DTO records: CreateTransactionRequest, UpdateTransactionRequest, TransactionResponse, TransactionSplitRequest, TransactionSplitResponse, TransactionFilterParams, CreateRecurringTemplateRequest, UpdateRecurringTemplateRequest, RecurringTemplateResponse
  - TransactionRepository.findByFilters paginated JPQL with 6 optional filters + separate countQuery
affects:
  - 05-02 (transaction CRUD service depends on these entities and repository)
  - 05-03 (recurring service depends on RecurringTemplate entity)
  - 05-04 (split logic depends on TransactionSplit entity)
  - 05-05 (frontend depends on DTO shapes)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "BigDecimal for amountMin/amountMax in JPQL params (not Money) — Hibernate converter not applied to bind parameters in JPQL WHERE clauses"
    - "Separate countQuery annotation prevents re-executing LEFT JOIN FETCH on count queries (avoids HHH90003004 warning)"
    - "RecurringTemplate constructor sets active=true and createdAt=Instant.now() for invariant enforcement"
    - "clearCategory Boolean flag pattern for PATCH semantics (distinguish null=no-change from true=clear)"

key-files:
  created:
    - backend/src/main/resources/db/migration/V012__create_transaction_splits.sql
    - backend/src/main/resources/db/migration/V013__create_recurring_templates.sql
    - backend/src/main/java/com/prosperity/shared/RecurrenceFrequency.java
    - backend/src/main/java/com/prosperity/transaction/TransactionSplit.java
    - backend/src/main/java/com/prosperity/transaction/TransactionSplitRepository.java
    - backend/src/main/java/com/prosperity/transaction/CreateTransactionRequest.java
    - backend/src/main/java/com/prosperity/transaction/UpdateTransactionRequest.java
    - backend/src/main/java/com/prosperity/transaction/TransactionResponse.java
    - backend/src/main/java/com/prosperity/transaction/TransactionSplitRequest.java
    - backend/src/main/java/com/prosperity/transaction/TransactionSplitResponse.java
    - backend/src/main/java/com/prosperity/transaction/TransactionFilterParams.java
    - backend/src/main/java/com/prosperity/recurring/RecurringTemplate.java
    - backend/src/main/java/com/prosperity/recurring/RecurringTemplateRepository.java
    - backend/src/main/java/com/prosperity/recurring/RecurringTemplateNotFoundException.java
    - backend/src/main/java/com/prosperity/recurring/CreateRecurringTemplateRequest.java
    - backend/src/main/java/com/prosperity/recurring/UpdateRecurringTemplateRequest.java
    - backend/src/main/java/com/prosperity/recurring/RecurringTemplateResponse.java
  modified:
    - backend/src/main/java/com/prosperity/transaction/TransactionRepository.java

key-decisions:
  - "Used BigDecimal (not Money) for amountMin/amountMax JPQL bind parameters — Hibernate's AttributeConverter is not applied to bind parameters in JPQL WHERE clauses, causing type mismatch at runtime"
  - "Separate countQuery in @Query annotation prevents Hibernate warning about FETCH joins in count queries and avoids incorrect page count calculations"
  - "RecurringTemplate placed in new com.prosperity.recurring package following layered-by-feature architecture"

patterns-established:
  - "BigDecimal in JPQL params even when entity field uses Money via converter"
  - "clearCategory Boolean flag for PATCH null-vs-clear distinction (same as UpdateAccountRequest.archived pattern)"
  - "Protected no-arg constructor + domain constructor pattern for JPA entities (from Transaction.java)"

requirements-completed: [TXNS-01, TXNS-04, TXNS-06, TXNS-07, TXNS-08]

# Metrics
duration: 2min
completed: 2026-04-07
---

# Phase 05 Plan 01: Data Layer Foundation Summary

**Flyway DDL for transaction_splits and recurring_templates, two new JPA entities (TransactionSplit, RecurringTemplate), 9 DTO records, RecurrenceFrequency enum, and paginated filtered JPQL query on TransactionRepository with separate countQuery**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-07T03:42:58Z
- **Completed:** 2026-04-07T03:44:58Z
- **Tasks:** 2
- **Files modified:** 18

## Accomplishments
- V012 and V013 Flyway migrations create transaction_splits and recurring_templates tables with proper FK constraints and indexes
- TransactionSplit and RecurringTemplate JPA entities follow exact same patterns as Transaction.java (no Lombok, manual getters/setters, protected no-arg constructor)
- TransactionRepository.findByFilters implements paginated JPQL with 6 optional filters and a separate countQuery to avoid Hibernate HHH90003004 warning
- All 9 DTO records created with proper Jakarta Validation annotations on required fields

## Task Commits

Each task was committed atomically:

1. **Task 1: Flyway migrations + new entities + RecurrenceFrequency enum** - `71b12b4` (feat)
2. **Task 2: DTO records + TransactionRepository paginated query** - `7d922a6` (feat)

**Plan metadata:** (docs commit pending)

## Files Created/Modified
- `backend/src/main/resources/db/migration/V012__create_transaction_splits.sql` - transaction_splits DDL with ON DELETE CASCADE and index
- `backend/src/main/resources/db/migration/V013__create_recurring_templates.sql` - recurring_templates DDL with frequency, day_of_month, next_due_date and two indexes
- `backend/src/main/java/com/prosperity/shared/RecurrenceFrequency.java` - WEEKLY, MONTHLY, YEARLY enum
- `backend/src/main/java/com/prosperity/transaction/TransactionSplit.java` - JPA entity with @Convert(MoneyConverter) and @ManyToOne Transaction/Category
- `backend/src/main/java/com/prosperity/transaction/TransactionSplitRepository.java` - findByTransactionId, deleteByTransactionId
- `backend/src/main/java/com/prosperity/transaction/CreateTransactionRequest.java` - @NotNull amount + transactionDate
- `backend/src/main/java/com/prosperity/transaction/UpdateTransactionRequest.java` - all nullable, clearCategory flag
- `backend/src/main/java/com/prosperity/transaction/TransactionResponse.java` - includes splits list, source, state
- `backend/src/main/java/com/prosperity/transaction/TransactionSplitRequest.java` - @NotNull categoryId + amount
- `backend/src/main/java/com/prosperity/transaction/TransactionSplitResponse.java` - id, categoryId, categoryName, amount, description
- `backend/src/main/java/com/prosperity/transaction/TransactionFilterParams.java` - 6 optional filters record
- `backend/src/main/java/com/prosperity/recurring/RecurringTemplate.java` - JPA entity, active=true + createdAt set in constructor
- `backend/src/main/java/com/prosperity/recurring/RecurringTemplateRepository.java` - findByBankAccountIdAndActiveTrue, findByBankAccountId
- `backend/src/main/java/com/prosperity/recurring/RecurringTemplateNotFoundException.java` - same pattern as TransactionNotFoundException
- `backend/src/main/java/com/prosperity/recurring/CreateRecurringTemplateRequest.java` - @NotNull amount, frequency, nextDueDate
- `backend/src/main/java/com/prosperity/recurring/UpdateRecurringTemplateRequest.java` - all nullable, clearCategory + active flags
- `backend/src/main/java/com/prosperity/recurring/RecurringTemplateResponse.java` - full template DTO including frequency and nextDueDate
- `backend/src/main/java/com/prosperity/transaction/TransactionRepository.java` - added findByFilters with value+countQuery annotations

## Decisions Made
- Used BigDecimal (not Money) for amountMin/amountMax in the JPQL bind parameters. Hibernate's AttributeConverter is only applied to entity field reads/writes, not to bind parameters in JPQL WHERE clauses. Using Money would cause a type mismatch at bind time.
- Separate countQuery in the @Query annotation avoids Hibernate's HHH90003004 warning (FETCH join in count queries produces incorrect results) and ensures accurate page counts.

## Deviations from Plan

None - plan executed exactly as written. The plan itself noted the BigDecimal vs Money tradeoff and recommended BigDecimal if issues arose; BigDecimal was used proactively.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All entities, repositories, and DTOs in place for Plan 05-02 (Transaction CRUD service + controller)
- RecurringTemplate entity ready for Plan 05-03 (Recurring service)
- TransactionSplit entity ready for Plan 05-04 (Split logic)
- TransactionResponse DTO shape established for Plan 05-05 (frontend)

## Self-Check: PASSED

All 18 files verified to exist on disk. Both commits verified in git log.
- 71b12b4: FOUND
- 7d922a6: FOUND

---
*Phase: 05-transactions*
*Completed: 2026-04-07*
