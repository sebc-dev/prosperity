---
phase: 01-project-foundation
plan: 04
subsystem: database
tags: [jpa, entity, spring-data, account, access-level, money-converter]

# Dependency graph
requires:
  - phase: 01-project-foundation/01-01
    provides: Maven project with Spring Boot 4.0.5, JPA, Flyway dependencies
  - phase: 01-project-foundation/01-02
    provides: Money, MoneyConverter, AccountType, AccessLevel value objects/enums
  - phase: 01-project-foundation/01-03
    provides: User JPA entity
provides:
  - Account JPA entity with MoneyConverter for balance storage
  - AccountAccess JPA entity linking User to Account with AccessLevel
  - AccountRepository (Spring Data JPA)
  - AccountAccessRepository (Spring Data JPA)
affects: [transaction, envelope, banking, budget]

# Tech tracking
tech-stack:
  added: []
  patterns: [entity-with-manual-getters-setters, money-converter-usage, unique-constraint-on-join-table]

key-files:
  created:
    - backend/src/main/java/com/prosperity/account/Account.java
    - backend/src/main/java/com/prosperity/account/AccountAccess.java
    - backend/src/main/java/com/prosperity/account/AccountRepository.java
    - backend/src/main/java/com/prosperity/account/AccountAccessRepository.java
  modified: []

key-decisions:
  - "Account balance stored as cents via MoneyConverter, consistent with Money value object pattern"

patterns-established:
  - "Entity with MoneyConverter: @Convert(converter = MoneyConverter.class) on Money fields mapped to BIGINT columns"
  - "Access control join entity: unique constraint on (user_id, foreign_key_id) for permission mapping"

requirements-completed: [INFR-07]

# Metrics
duration: 1min
completed: 2026-03-28
---

# Phase 01 Plan 04: Account and AccountAccess Entities Summary

**Account and AccountAccess JPA entities with MoneyConverter balance storage and user-account access level mapping**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-28T21:05:53Z
- **Completed:** 2026-03-28T21:06:51Z
- **Tasks:** 1
- **Files modified:** 4

## Accomplishments
- Account entity with MoneyConverter for balance, AccountType enum, currency default EUR, Plaid account ID
- AccountAccess entity with unique constraint on (user_id, bank_account_id) and ManyToOne to both User and Account
- Spring Data JPA repositories for both entities
- All files pass compile and spotless:check

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Account, AccountAccess entities and repositories** - `f6acc68` (feat)

**Plan metadata:** [pending] (docs: complete plan)

## Files Created/Modified
- `backend/src/main/java/com/prosperity/account/Account.java` - JPA entity for bank accounts with MoneyConverter balance
- `backend/src/main/java/com/prosperity/account/AccountAccess.java` - JPA entity linking User to Account with AccessLevel
- `backend/src/main/java/com/prosperity/account/AccountRepository.java` - Spring Data JPA repository for Account
- `backend/src/main/java/com/prosperity/account/AccountAccessRepository.java` - Spring Data JPA repository for AccountAccess

## Decisions Made
- Account balance stored as cents via MoneyConverter, consistent with Money value object pattern from Plan 02

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Account and AccountAccess entities ready for use by Transaction and Envelope entities
- Repositories available for service layer development

---
*Phase: 01-project-foundation*
*Completed: 2026-03-28*
