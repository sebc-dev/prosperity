---
phase: 01-project-foundation
plan: 07
subsystem: database
tags: [jpa, entity, category, envelope, budget, spring-data]

requires:
  - phase: 01-02
    provides: Money, MoneyConverter, RolloverPolicy, EnvelopeScope value objects
  - phase: 01-03
    provides: User entity
  - phase: 01-04
    provides: Account entity

provides:
  - Category entity with hierarchical self-referencing parent
  - Envelope entity with budget business methods (isOverspent, rollover)
  - EnvelopeAllocation entity for monthly budget allocations
  - CategoryRepository, EnvelopeRepository, EnvelopeAllocationRepository

affects: [categories, envelopes, transactions, budgets]

tech-stack:
  added: []
  patterns: [self-referencing-manytoone, yearmonth-string-storage, business-methods-on-entity]

key-files:
  created:
    - backend/src/main/java/com/prosperity/category/Category.java
    - backend/src/main/java/com/prosperity/category/CategoryRepository.java
    - backend/src/main/java/com/prosperity/envelope/Envelope.java
    - backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java
    - backend/src/main/java/com/prosperity/envelope/EnvelopeAllocation.java
    - backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRepository.java
  modified: []

key-decisions:
  - "YearMonth stored as String (length 7, format 2026-03) with getter/setter conversion"
  - "Envelope business methods (isOverspent, rollover) on entity, not separate service"

patterns-established:
  - "Self-referencing @ManyToOne for hierarchical data (Category.parent)"
  - "YearMonth mapped as String column for DB portability"
  - "Business logic on entity when closely tied to entity state (Envelope.isOverspent, Envelope.rollover)"

requirements-completed: [INFR-07]

duration: 1min
completed: 2026-03-28
---

# Phase 01 Plan 07: Category, Envelope, EnvelopeAllocation Entities Summary

**Hierarchical Category entity, Envelope with budget overspend/rollover business methods, and monthly EnvelopeAllocation using MoneyConverter**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-28T21:08:26Z
- **Completed:** 2026-03-28T21:09:40Z
- **Tasks:** 1
- **Files modified:** 6

## Accomplishments
- Category entity with self-referencing @ManyToOne parent for hierarchical categories and optional Plaid category ID
- Envelope entity with isOverspent(Money) and rollover(Money) business methods, linked to Account and optionally to User (owner)
- EnvelopeAllocation entity storing YearMonth as String with MoneyConverter for allocated amounts
- Three Spring Data JPA repositories (CategoryRepository, EnvelopeRepository, EnvelopeAllocationRepository)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Category, Envelope, EnvelopeAllocation entities and repositories** - `a36e17c` (feat)

**Plan metadata:** pending

## Files Created/Modified
- `backend/src/main/java/com/prosperity/category/Category.java` - JPA entity with self-referencing parent, plaidCategoryId
- `backend/src/main/java/com/prosperity/category/CategoryRepository.java` - Spring Data JPA repository for Category
- `backend/src/main/java/com/prosperity/envelope/Envelope.java` - JPA entity with isOverspent and rollover business methods
- `backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java` - Spring Data JPA repository for Envelope
- `backend/src/main/java/com/prosperity/envelope/EnvelopeAllocation.java` - Monthly allocation entity with YearMonth stored as String
- `backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRepository.java` - Spring Data JPA repository for EnvelopeAllocation

## Decisions Made
- YearMonth stored as String column (length 7, format "2026-03") with getter/setter conversion rather than a custom JPA converter, keeping it simple and DB-portable
- Business methods (isOverspent, rollover) placed directly on Envelope entity since they depend only on entity state, no external services

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all entities fully wired with proper fields and business logic.

## Next Phase Readiness
- Category, Envelope, and EnvelopeAllocation domain layer complete
- Ready for transaction entities that reference categories
- Ready for envelope budget service layer

---
*Phase: 01-project-foundation*
*Completed: 2026-03-28*
