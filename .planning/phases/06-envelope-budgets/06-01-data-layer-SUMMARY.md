---
phase: 06-envelope-budgets
plan: 01
subsystem: database
tags: [jpa, hibernate, flyway, postgresql, many-to-many, recursive-cte, spring-data]

# Dependency graph
requires:
  - phase: 03-accounts
    provides: AccountAccess entity for access-level filtering via JPQL JOIN
  - phase: 04-categories
    provides: Category entity + parent_id hierarchy for recursive CTE category tree expansion
  - phase: 05-transactions
    provides: transactions + transaction_splits tables (D-06 convention: split parents set category_id = NULL)
provides:
  - envelope_categories junction table (N:N between envelopes and categories, D-01)
  - archived flag on envelopes (D-18 soft-delete)
  - EnvelopeRepository access-filtered queries (list by user+account, list all, includeArchived variant)
  - EnvelopeRepository.existsCategoryLinkOnAccount enforcing D-01 uniqueness
  - EnvelopeRepository.sumConsumedForMonth — native recursive-CTE aggregation with split-parent dedup
  - EnvelopeRepository.findMonthlyConsumptionRange — 12-bucket monthly history via generate_series + LEFT JOIN
  - EnvelopeRepository.hasAnyAllocation — hard-delete vs soft-delete decision helper
  - EnvelopeAllocationRepository month lookup / range / full-list queries
affects: [06-02-dtos, 06-04-service-layer, 06-05-controllers, 06-06-backend-tests]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Native SQL recursive CTE for category-tree expansion (envelope_cat_tree via categories.parent_id)
    - NOT EXISTS defensive dedup across transactions + transaction_splits UNION ALL branches
    - generate_series + LEFT JOIN for calendar-aligned monthly aggregation with zero-fill
    - JPQL JOIN AccountAccess aa ON aa.bankAccount = ba (access inheritance pattern from Phase 3/5)
    - CAST(:param AS uuid) / CAST(:param AS date) for null-safe PostgreSQL parameter binding

key-files:
  created:
    - backend/src/main/resources/db/migration/V014__create_envelope_categories.sql
    - backend/src/main/resources/db/migration/V015__add_archived_to_envelopes.sql
  modified:
    - backend/src/main/java/com/prosperity/envelope/Envelope.java
    - backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java
    - backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRepository.java

key-decisions:
  - "Junction uses composite PK (envelope_id, category_id); no surrogate id"
  - "ON DELETE CASCADE on envelope_id (deleting envelope clears links); ON DELETE RESTRICT on category_id (mirrors CategoryService policy)"
  - "Composite index (bank_account_id, archived) on envelopes to support list-by-account-with-archived-filter"
  - "consumed CTE defensive dedup via NOT EXISTS on transaction_splits — guards against future import drift even though D-06 guarantees split parents have category_id = NULL"
  - "12-month history uses generate_series with CAST(:to AS date) - INTERVAL '1 day' upper bound to yield exactly 12 buckets for [from, to) half-open ranges"
  - "JPQL references entity field monthValue (column name is 'month' in DB, reserved-word avoidance)"
  - "DISTINCT on access-filtered list queries to defend against multiple AccountAccess rows per user"

patterns-established:
  - "Access-filtered envelope query template: JOIN e.bankAccount ba JOIN AccountAccess aa ON aa.bankAccount = ba WHERE aa.user.id = :userId AND e.archived = false AND ba.archived = false"
  - "Split-dedup pattern for consumed aggregation: UNION ALL of (transactions NOT EXISTS in splits) + (splits JOIN transactions) both filtered by envelope_cat_tree"
  - "D-01 uniqueness pattern: COUNT(e) > 0 with optional :envelopeIdToExclude parameter for create vs update semantics"

requirements-completed:
  - ENVL-01
  - ENVL-02
  - ENVL-03
  - ENVL-07

# Metrics
duration: 6min
completed: 2026-04-22
---

# Phase 6 Plan 1: Envelope Budgets Data Layer Summary

**envelope_categories N:N junction + archived soft-delete flag + EnvelopeRepository with recursive-CTE consumed aggregation (split-dedup) and 12-month history — no scope deviations**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-22T11:33:32Z
- **Completed:** 2026-04-22T11:39:30Z
- **Tasks:** 4
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments

- V014 migration creates `envelope_categories(envelope_id, category_id)` junction with composite PK, CASCADE on envelope, RESTRICT on category, and an index on `category_id`.
- V015 migration adds `archived BOOLEAN NOT NULL DEFAULT FALSE` to `envelopes` plus `idx_envelopes_account_archived(bank_account_id, archived)`.
- Envelope entity now exposes `@ManyToMany Set<Category> categories` via `@JoinTable(name = "envelope_categories")` plus `archived` boolean, preserving all existing fields, constructors, getters/setters, and helpers (`isOverspent`, `rollover`).
- EnvelopeRepository provides 7 query methods: 3 access-filtered listing variants, the D-01 `existsCategoryLinkOnAccount`, `sumConsumedForMonth` and `findMonthlyConsumptionRange` with recursive CTEs + `NOT EXISTS` split dedup, and `hasAnyAllocation` for the hard-delete vs soft-delete decision.
- EnvelopeAllocationRepository provides 3 queries: single-month lookup, half-open range, and full-list ordered ascending — all referencing `monthValue` (entity field) rather than `month` (column alias).

## Task Commits

Each task was committed atomically:

1. **Task 1: V014 + V015 Flyway migrations** — `563c5fe` (feat)
2. **Task 2: Enrich Envelope entity (categories ManyToMany + archived)** — `3724342` (feat)
3. **Task 3: Enrich EnvelopeRepository (access-filter, D-01, consumed CTE, 12-month history)** — `3d0b702` (feat)
4. **Task 4: Enrich EnvelopeAllocationRepository (month lookup + range)** — `ee35cfe` (feat)

**Plan metadata:** pending docs commit (SUMMARY + STATE + ROADMAP).

## Files Created/Modified

- `backend/src/main/resources/db/migration/V014__create_envelope_categories.sql` — N:N junction envelope↔category (D-01) with composite PK, CASCADE/RESTRICT FK policy, idx on category_id.
- `backend/src/main/resources/db/migration/V015__add_archived_to_envelopes.sql` — archived BOOLEAN NOT NULL DEFAULT FALSE + composite idx (bank_account_id, archived).
- `backend/src/main/java/com/prosperity/envelope/Envelope.java` — added `categories` (@ManyToMany + @JoinTable envelope_categories) and `archived` flag with accessors; kept entire prior API.
- `backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java` — 7 queries (listing, D-01, consumed, history, allocation-existence).
- `backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRepository.java` — 3 queries (month lookup, month range, all ordered).

## Decisions Made

- **Junction PK uses composite (envelope_id, category_id)**, not a surrogate — D-01 is inherently a pair-uniqueness constraint, and the PK's leading column also indexes envelope_id so only `category_id` needs a separate index.
- **FK policies asymmetric**: `ON DELETE CASCADE` on envelope_id (deleting an envelope clears its links automatically), `ON DELETE RESTRICT` on category_id (keeps CategoryService delete-guard consistent).
- **Composite index `(bank_account_id, archived)`** added alongside `archived` column because the primary access pattern is list-by-account-filtering-by-archived.
- **Defensive split-dedup via `NOT EXISTS`** even though Phase 5 D-06 guarantees split parents have `category_id = NULL`. The plan's Iteration-1 revision made this explicit; the query remains correct if future import code regresses on D-06.
- **JPQL references `ea.monthValue`** (the Java field) not `ea.month` — the entity declares `@Column(name = "month") private LocalDate monthValue`, so JPQL must use the field name.
- **12-month history upper bound** uses `CAST(:to AS date) - INTERVAL '1 day'` inside `generate_series` so that a half-open `[from=2026-04-01, to=2027-04-01)` pair yields exactly 12 month buckets starting at 2026-04-01.

## Deviations from Plan

None — plan executed exactly as written (including the Iteration-1 revision's NOT EXISTS dedup in both native queries).

## Issues Encountered

**Environmental (not code-related):** Full Testcontainers-backed integration tests (e.g., `SecurityConfigTest`) could not execute in this agent's environment because Docker Desktop integration is not activated in WSL2 (`docker info` reports "command not found"). This is not a regression introduced by this plan — the issue is pre-existing and out of scope (scope boundary rule).

The plan's designated verification command — `./mvnw -pl backend test -Dtest=ProsperityApplicationTest` — runs a reflection-only `@SpringBootApplication` annotation check that does NOT boot the Spring context, and it passes cleanly (1/1 green). `./mvnw compile` and `./mvnw test-compile` both succeed, confirming the entity + repository changes compile against the full codebase. The existing `EnvelopeTest` unit suite (7 tests, pure entity logic) also passes, confirming the entity enrichment is backward compatible.

Flyway migrations V014/V015 will be validated during Testcontainers-backed tests added in later plans (06-03 scaffolds, 06-04 service tests, 06-06 repo tests) once Docker is available.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **Plan 06-02 (DTOs & exceptions)** — already executing in parallel; no coupling concerns with this plan (no DTO consumes new repository methods yet).
- **Plan 06-04 (Service layer)** — can now call `EnvelopeRepository.sumConsumedForMonth`, `findMonthlyConsumptionRange`, `existsCategoryLinkOnAccount`, `hasAnyAllocation`, plus the three access-filtered list queries, and can persist envelopes with categories + archived flag.
- **Plan 06-05 (Controllers)** — no blockers, but depends on Plan 06-04 (service layer) before it can wire the new queries into REST endpoints.
- **Plan 06-06 (Backend tests)** — will exercise V014/V015 via Testcontainers; split-dedup NOT EXISTS clause is the highest-value test target (edge case: transaction with both category_id and splits must be counted once, via splits).

**Known limitation in this environment:** Docker Desktop integration must be enabled in WSL2 before any Testcontainers-backed test can run. This is an environmental prerequisite, not a code change this plan needs to address.

## Self-Check

**1. Files exist:**
- [x] `backend/src/main/resources/db/migration/V014__create_envelope_categories.sql` — FOUND
- [x] `backend/src/main/resources/db/migration/V015__add_archived_to_envelopes.sql` — FOUND
- [x] `backend/src/main/java/com/prosperity/envelope/Envelope.java` — FOUND (modified)
- [x] `backend/src/main/java/com/prosperity/envelope/EnvelopeRepository.java` — FOUND (enriched)
- [x] `backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRepository.java` — FOUND (enriched)

**2. Commits exist:**
- [x] `563c5fe` (Task 1)
- [x] `3724342` (Task 2)
- [x] `3d0b702` (Task 3)
- [x] `ee35cfe` (Task 4)

**3. Acceptance criteria:** All grep-based acceptance criteria for Tasks 1–4 validated. Compilation passes. Existing EnvelopeTest (7 tests) remains green.

## Self-Check: PASSED

---
*Phase: 06-envelope-budgets*
*Completed: 2026-04-22*
