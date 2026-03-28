---
phase: 01-project-foundation
plan: 08
subsystem: database
tags: [flyway, postgresql, migrations, sql, schema]

# Dependency graph
requires:
  - phase: 01-project-foundation/plan-05
    provides: "Flyway configured in Spring Boot (application.yml + pom.xml)"
  - phase: 01-project-foundation/plan-07
    provides: "JPA entities defining domain model (User, Account, Transaction, etc.)"
provides:
  - "6 Flyway migration files defining complete initial PostgreSQL schema"
  - "Tables: users, bank_accounts, account_access, categories, transactions, envelopes, envelope_allocations"
affects: [integration-tests, plaid-sync, auth, accounts, transactions, envelopes, categories]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Flyway versioned migrations V00N__description.sql", "BIGINT cents for money columns", "UUID primary keys", "TIMESTAMPTZ for all timestamps"]

key-files:
  created:
    - backend/src/main/resources/db/migration/V001__create_users.sql
    - backend/src/main/resources/db/migration/V002__create_bank_accounts.sql
    - backend/src/main/resources/db/migration/V003__create_account_access.sql
    - backend/src/main/resources/db/migration/V004__create_categories.sql
    - backend/src/main/resources/db/migration/V005__create_transactions.sql
    - backend/src/main/resources/db/migration/V006__create_envelopes.sql
  modified: []

key-decisions:
  - "Migration SQL matches JPA entity column definitions exactly"

patterns-established:
  - "Flyway naming: V00N__create_tablename.sql"
  - "Money stored as BIGINT (cents), never DECIMAL"
  - "All timestamps TIMESTAMPTZ with DEFAULT NOW()"
  - "Foreign key order enforced by migration version numbering"

requirements-completed: [INFR-06]

# Metrics
duration: 2min
completed: 2026-03-28
---

# Phase 01 Plan 08: Flyway Migrations Summary

**6 Flyway SQL migrations defining complete initial PostgreSQL schema with UUID keys, BIGINT cents, and TIMESTAMPTZ timestamps**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-28T21:14:12Z
- **Completed:** 2026-03-28T21:16:00Z
- **Tasks:** 1
- **Files modified:** 6

## Accomplishments
- Created 6 versioned Flyway migration files (V001-V006) covering all 7 tables
- Schema matches JPA entity definitions from plans 03-07 exactly
- Foreign key ordering enforced: users (V001) before account_access (V003), bank_accounts (V002) before transactions (V005) and envelopes (V006)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Flyway migration files** - `4dcddfb` (feat)

## Files Created/Modified
- `backend/src/main/resources/db/migration/V001__create_users.sql` - Users table with email unique constraint
- `backend/src/main/resources/db/migration/V002__create_bank_accounts.sql` - Bank accounts with balance_cents BIGINT
- `backend/src/main/resources/db/migration/V003__create_account_access.sql` - Account access with unique(user_id, bank_account_id)
- `backend/src/main/resources/db/migration/V004__create_categories.sql` - Categories with self-referencing parent_id
- `backend/src/main/resources/db/migration/V005__create_transactions.sql` - Transactions with state default MANUAL_UNMATCHED
- `backend/src/main/resources/db/migration/V006__create_envelopes.sql` - Envelopes and envelope_allocations tables

## Decisions Made
- Migration SQL matches JPA entity column definitions exactly -- column names, types, and constraints aligned with entity annotations

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Database schema ready for Flyway to execute on startup
- Integration tests can validate schema against JPA entities
- All foreign key dependencies ordered correctly for sequential migration execution

---
*Phase: 01-project-foundation*
*Completed: 2026-03-28*
