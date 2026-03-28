---
phase: 01-project-foundation
plan: 02
subsystem: domain
tags: [java-records, value-objects, enums, jpa-converter, banking-abstraction, money]

requires:
  - phase: 01-01
    provides: Maven project structure with Spring Boot 4.0.5, JPA, Flyway
provides:
  - Money value object (BigDecimal precision 2, no floating-point)
  - MoneyConverter JPA AttributeConverter (Money <-> BIGINT cents)
  - Domain enums (TransactionState, AccountType, RolloverPolicy, EnvelopeScope, TransactionSource, AccessLevel)
  - BankConnector interface (abstract bank integration D-03)
  - BankTransaction record (connector abstraction model)
affects: [01-03, 01-04, 01-05, transactions, envelopes, accounts, banking]

tech-stack:
  added: []
  patterns: [java-records-for-value-objects, money-as-bigdecimal-cents, interface-abstraction-for-banking]

key-files:
  created:
    - backend/src/main/java/com/prosperity/shared/Money.java
    - backend/src/main/java/com/prosperity/shared/MoneyConverter.java
    - backend/src/main/java/com/prosperity/shared/TransactionState.java
    - backend/src/main/java/com/prosperity/shared/AccountType.java
    - backend/src/main/java/com/prosperity/shared/RolloverPolicy.java
    - backend/src/main/java/com/prosperity/shared/EnvelopeScope.java
    - backend/src/main/java/com/prosperity/shared/TransactionSource.java
    - backend/src/main/java/com/prosperity/account/AccessLevel.java
    - backend/src/main/java/com/prosperity/banking/BankConnector.java
    - backend/src/main/java/com/prosperity/banking/BankTransaction.java
  modified: []

key-decisions:
  - "Money uses BigDecimal with scale 2, no of(double) factory to prevent floating-point issues"
  - "MoneyConverter set to autoApply=false for explicit @Convert on entities"
  - "BankConnector is a pure interface with fetchTransactions and createLinkToken methods"

patterns-established:
  - "Value objects as Java records in com.prosperity.shared package"
  - "Domain enums in their feature package (AccessLevel in account, rest in shared)"
  - "Banking abstraction in com.prosperity.banking with interface + record pattern"

requirements-completed: [INFR-07]

duration: 1min
completed: 2026-03-28
---

# Phase 01 Plan 02: Domain Value Objects and Banking Abstraction Summary

**Money record with BigDecimal precision 2, MoneyConverter for JPA cents storage, 6 domain enums, and BankConnector interface for abstract bank integration**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-28T20:59:09Z
- **Completed:** 2026-03-28T21:00:25Z
- **Tasks:** 1
- **Files modified:** 10

## Accomplishments
- Money value object enforcing BigDecimal precision 2 with no floating-point factory method
- MoneyConverter JPA AttributeConverter storing Money as BIGINT cents in PostgreSQL
- All 6 domain enums: TransactionState (3 states), AccountType, AccessLevel, RolloverPolicy, EnvelopeScope, TransactionSource
- BankConnector interface enabling Plaid to be swapped for Powens/Salt Edge (D-03 decision)
- BankTransaction record as the common import model for bank connectors

## Task Commits

Each task was committed atomically:

1. **Task 1: Create value objects, enums, and banking abstraction** - `f9f6037` (feat)

**Plan metadata:** [pending final commit] (docs: complete plan)

## Files Created/Modified
- `backend/src/main/java/com/prosperity/shared/Money.java` - Immutable money value object, BigDecimal precision 2
- `backend/src/main/java/com/prosperity/shared/MoneyConverter.java` - JPA converter Money <-> Long cents
- `backend/src/main/java/com/prosperity/shared/TransactionState.java` - Enum: MANUAL_UNMATCHED, IMPORTED_UNMATCHED, MATCHED
- `backend/src/main/java/com/prosperity/shared/AccountType.java` - Enum: PERSONAL, SHARED
- `backend/src/main/java/com/prosperity/shared/RolloverPolicy.java` - Enum: RESET, CARRY_OVER
- `backend/src/main/java/com/prosperity/shared/EnvelopeScope.java` - Enum: PERSONAL, SHARED
- `backend/src/main/java/com/prosperity/shared/TransactionSource.java` - Enum: MANUAL, PLAID, RECURRING
- `backend/src/main/java/com/prosperity/account/AccessLevel.java` - Enum: READ, WRITE, ADMIN
- `backend/src/main/java/com/prosperity/banking/BankConnector.java` - Abstract bank connector interface
- `backend/src/main/java/com/prosperity/banking/BankTransaction.java` - Bank transaction record for connectors

## Decisions Made
- Money uses BigDecimal with scale 2 and no of(double) factory to prevent floating-point precision issues
- MoneyConverter set to autoApply=false so entities explicitly declare @Convert
- BankConnector kept minimal with fetchTransactions and createLinkToken -- additional methods added when Plaid integration phase begins

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All value objects and enums ready for JPA entity definitions (plans 01-03, 01-04, 01-05)
- BankConnector interface ready for Plaid implementation in Phase 7
- MoneyConverter ready for @Convert annotations on entity Money fields

## Self-Check: PASSED

All 10 created files verified present. Task commit f9f6037 verified in git log.

---
*Phase: 01-project-foundation*
*Completed: 2026-03-28*
