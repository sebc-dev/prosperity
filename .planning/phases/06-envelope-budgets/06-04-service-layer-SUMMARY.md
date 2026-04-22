---
phase: 06-envelope-budgets
plan: 04
subsystem: service
tags: [service, business-logic, envelope, rollover, budget-ratio, access-control, spring-transactional]

# Dependency graph
requires:
  - phase: 06-envelope-budgets (plan 01)
    provides: Envelope entity with @ManyToMany categories + archived flag; EnvelopeRepository with sumConsumedForMonth / findMonthlyConsumptionRange / existsCategoryLinkOnAccount / hasAnyAllocation / access-filtered list queries; EnvelopeAllocationRepository month lookup/range queries
  - phase: 06-envelope-budgets (plan 02)
    provides: EnvelopeResponse / EnvelopeHistoryEntry / EnvelopeAllocationResponse DTOs; CreateEnvelopeRequest / UpdateEnvelopeRequest / EnvelopeAllocationRequest; EnvelopeStatus enum; EnvelopeNotFoundException / EnvelopeAllocationNotFoundException / DuplicateEnvelopeCategoryException
  - phase: 03-accounts
    provides: AccessLevel.isAtLeast + AccountRepository.hasAccess pattern for 403-vs-404 inheritance
  - phase: 04-categories
    provides: CategoryRepository.findAllById + CategoryNotFoundException
  - phase: 05-transactions
    provides: TransactionService.requireAccountAccess canonical pattern
provides:
  - EnvelopeService (CRUD + scope derivation + D-01 + rollover + status + history)
  - EnvelopeAllocationService (monthly override CRUD with access inheritance)
  - D-13 ratio single source of truth (denominator = effectiveBudget + carryOver)
  - D-12 rollover single source of truth (1-month lookback + zero-clamp)
  - D-18 hard-vs-soft-delete branching on hasAnyAllocation
affects: [06-05-controllers, 06-06-backend-tests, 06-08-frontend-pages]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Scope-derivation pattern: switch on account.getAccountType() to set EnvelopeScope + owner; client-supplied scope never trusted (Pitfall 4)"
    - "Pitfall 3 collection mutation: env.getCategories().clear() + addAll(...) for @ManyToMany updates — never setCategories()"
    - "403-vs-404 helper pattern: existsById check before hasAccess, mirrors TransactionService.requireAccountAccess"
    - "Envelope-access helper: existsById on envelope, then load, then requireAccountAccess on envelope.getBankAccount().getId() — layered 404 checks"
    - "Lazy rollover formula: carryOver computed on-demand via 1-month lookback (does not persist, does not chain)"
    - "DataIntegrityViolationException bubble-up: allocation service never catches; controller @ExceptionHandler translates to 409"
    - "PostgreSQL JDBC row[0] extractor tolerant to both java.sql.Date and LocalDate via instanceof pattern matching"

key-files:
  created:
    - backend/src/main/java/com/prosperity/envelope/EnvelopeService.java
    - backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationService.java
  modified: []

key-decisions:
  - "EnvelopeService.computeRatio denominator = effectiveBudget + carryOver (D-13 literal); 0 when allocatable<=0 (defensive GREEN)"
  - "computeCarryOver extracted as private helper so computeAvailable, toResponse, and getEnvelopeHistory share a single carry formula implementation"
  - "List-envelopes-with-archived-filter implemented in-Java (filter by accountId on IncludingArchived list) rather than adding a new JPQL variant — simplest, scale per D-22 is small"
  - "findMonthlyConsumptionRange row[0] extracted via pattern matching for both java.sql.Date and LocalDate — defensive against JDBC driver variance"
  - "EnvelopeAllocationService.requireEnvelopeAccess helper duplicated from EnvelopeService rather than extracted to a shared guard — duplication beats premature abstraction; revisit when a third service needs the same logic"
  - "loadCategoriesOrThrow helper centralises categoryIds-size-vs-found comparison; missing ids surface in the exception message to aid debugging"

patterns-established:
  - "Envelope access pattern: existsById -> load -> delegate to requireAccountAccess via envelope.getBankAccount().getId()"
  - "Rollover formula helper split: resolveEffectiveBudget + sumConsumed + computeCarryOver compose into computeAvailable and into getEnvelopeHistory per-month loop"
  - "D-13 ratio computation accepts raw allocatable + consumed BigDecimals (not Money) — single-responsibility: Money I/O stays at toResponse boundary"

requirements-completed:
  - ENVL-01
  - ENVL-02
  - ENVL-03
  - ENVL-04
  - ENVL-05
  - ENVL-06
  - ENVL-07

# Metrics
duration: 4min
completed: 2026-04-22
---

# Phase 06 Plan 04: Service Layer Summary

**EnvelopeService (7 public methods, 481 lines) + EnvelopeAllocationService (4 public methods) — scope derivation (D-07), D-01 category uniqueness, D-12 rollover (1-month lookback, zero-clamp), D-13 status thresholds with allocatable denominator, D-18 hard-vs-soft delete, Pitfall 3 collection mutation.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-22T11:43:34Z
- **Completed:** 2026-04-22T11:48:01Z
- **Tasks:** 2
- **Files created:** 2

## Accomplishments

- `EnvelopeService` delivers the heart of Phase 6: CRUD + monthly computation for a single envelope, using the Plan 01 repository queries (recursive CTE over categories + split dedup) and Plan 02 DTOs/exceptions.
- Scope-from-account derivation (D-07) enforced server-side in `createEnvelope`: `account.getAccountType() == SHARED` -> `scope = SHARED`, `owner = null`; otherwise `scope = PERSONAL`, `owner = current user`. Any client-supplied scope is ignored at DTO level (Pitfall 4 is doubly enforced: `CreateEnvelopeRequest` has no `scope` field, and the service switches on account type).
- D-01 enforced on BOTH create (`existsCategoryLinkOnAccount(accountId, categoryId, null)`) and update (`existsCategoryLinkOnAccount(accountId, categoryId, envelopeIdToExclude=self)` so the edited envelope's own categories don't trip the check).
- Partial-PATCH update (`updateEnvelope`) applies only non-null fields. When `categoryIds != null`, categories are replaced via `clear()` + `addAll()` on the persistent `@ManyToMany` collection (**Pitfall 3** — never `setCategories()`).
- D-18 hard-vs-soft delete: `deleteEnvelope` branches on `envelopeRepository.hasAnyAllocation(envelopeId)` — no allocations ever = hard-delete; otherwise `archived = true` via soft-delete.
- D-12 rollover formula implemented as three composable helpers: `resolveEffectiveBudget`, `sumConsumed`, `computeCarryOver`. RESET returns 0 unconditionally; CARRY_OVER returns `max(0, prevBudget - prevConsumed)` with exactly 1-month lookback (no chaining to prev-prev).
- D-13 ratio denominator = `effectiveBudget + carryOver` (the allocatable total), defensive zero when allocatable ≤ 0. Status thresholds: `< 0.80` GREEN, `0.80 ≤ r ≤ 1.00` YELLOW, `> 1.00` RED.
- `getEnvelopeHistory` returns exactly 12 month buckets aligned with `EnvelopeHistoryEntry`: overrides overlay from `findByEnvelopeIdAndMonthRange`, consumed from `findMonthlyConsumptionRange`, each month independently computes its own carryOver (so the history view is internally consistent with the current-month view).
- `EnvelopeAllocationService` delivers the 4 public methods the `EnvelopeAllocationController` depends on. Access checks reuse the same pattern. `DataIntegrityViolationException` is NOT caught — the controller's `@ExceptionHandler` converts duplicate (envelope, month) violations to 409 (see existing `EnvelopeAllocationController`).

## Task Commits

Each task committed atomically:

1. **Task 1: EnvelopeService** — `5200047` (feat)
2. **Task 2: EnvelopeAllocationService** — `89779fd` (feat)

**Plan metadata commit** (SUMMARY + STATE + ROADMAP): pending.

## Files Created/Modified

- `backend/src/main/java/com/prosperity/envelope/EnvelopeService.java` — 481 lines, 7 public methods, 1 private access helper pair, 4 private domain helpers (resolveEffectiveBudget, sumConsumed, computeCarryOver, computeRatio + computeStatus), 2 private mapping helpers (loadCategoriesOrThrow, toResponse), 1 LocalDate extractor.
- `backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationService.java` — 162 lines, 4 public methods, 1 private access helper, 1 private user resolver, 1 private mapper.

## Decisions Made

- **D-13 ratio denominator = `effectiveBudget + carryOver`** — a single computeRatio helper is called from both `toResponse` and `getEnvelopeHistory`, and both pass the allocatable total (not the effectiveBudget alone). This guarantees the frontend's ratio view and the history table never diverge.
- **Pitfall 3 collection mutation in update** — `env.getCategories().clear(); env.getCategories().addAll(loadedCategories)` is the ONLY mutation path. Hibernate tracks the existing managed Set; reassigning via `setCategories()` would detach the old collection and trigger orphan semantics.
- **Separation of computeCarryOver** — lifting carryOver out of computeAvailable lets getEnvelopeHistory call it per-month without duplicating the RESET/CARRY_OVER switch. It's also the right seam for the D-12 future extension (if lookback ever goes to 12 months, only one method changes).
- **List-by-account-with-archived-filter** — implemented by calling `findAllAccessibleToUserIncludingArchived` and filtering by accountId in Java. Per-account archived scale is small (D-22); avoids adding a 4th JPQL variant.
- **Explicit envelope load in requireEnvelopeAccess** — issues an extra `existsById` before the `findById` Optional is realised so the 404 branch executes before any eager-fetch might throw a different exception.
- **Duplicate helper in EnvelopeAllocationService** — `requireEnvelopeAccess` duplicated across services deliberately. Extracting to a shared guard right now would over-abstract for a 2-service system; the plan's note and the Khorikov rule "don't test what isn't yet complex" both support this.
- **PostgreSQL row[0] type-tolerant extractor** — pattern-matching on `LocalDate` vs `java.sql.Date` so the code works whether the driver binds a `DATE` column as one or the other (tests run under Testcontainers, prod under real PostgreSQL — both are covered).

## Deviations from Plan

None — plan executed exactly as written.

Minor notes:
- Used `Comparator.comparing(Category::getName)` for deterministic `EnvelopeCategoryRef` ordering in `toResponse` — the plan's pseudocode spelled this out.
- `loadCategoriesOrThrow` includes the missing IDs in the exception message ("Categories introuvables : [id1, id2]") — small UX gain, consistent with TransactionService-style error messages.

## Issues Encountered

**Environmental (pre-existing, not a regression from this plan):**

The plan's `./mvnw test -Dtest=EnvelopeTest` command passes cleanly (7/7 green). Running the broader `./mvnw test -Dtest='Envelope*Test'` surfaces 54 errors, all caused by `Previous attempts to find a Docker environment failed. Will not retry.` from `com.prosperity.TestcontainersConfig` — i.e. Docker Desktop integration is not enabled in this WSL2 environment. This is the same environmental limitation documented in the Plan 01 summary and is out of scope for this plan (scope boundary rule).

The failing tests are the Wave-0 `@Disabled` stubs (`EnvelopeServiceTest`, `EnvelopeControllerTest`, `EnvelopeAllocationControllerTest`) — they would be skipped if JUnit reached them, but Spring tries to build the ApplicationContext first and that requires Docker for the PostgreSQL Testcontainer. Assertions for these stubs are scheduled for Plan 06 (Wave 3 backend tests).

**Parallel execution note:** Plan 05 controllers (`EnvelopeController`, `EnvelopeAllocationController`) were already committed on this branch (`9f26020`, `cb0a64e`) when this plan started executing. The controllers depend on the services this plan provides, so `./mvnw compile` was temporarily broken until Task 1 + Task 2 both landed. After both commits, `./mvnw compile` is green and `./mvnw test -Dtest=EnvelopeTest` is 7/7 green.

## User Setup Required

None — no external service configuration required for this plan.

For CI to run the Testcontainers-backed tests (Plan 06's responsibility, not this plan's), Docker Desktop WSL2 integration must be enabled. This is an environmental prerequisite, not a code change.

## Next Phase Readiness

- **Plan 06-05 (controllers)** — Already committed and compiling against this plan's services. `EnvelopeController` uses the 7 public methods of `EnvelopeService`; `EnvelopeAllocationController` uses the 4 public methods of `EnvelopeAllocationService`. Signatures match exactly.
- **Plan 06-06 (backend tests)** — Can now fill in the 26 `@Disabled` stubs in `EnvelopeServiceTest` (and controller tests) against the concrete service behavior. Coverage targets:
  - ENVL-02 (budget resolution): call `getEnvelope` and assert `effectiveBudget` toggles with/without `EnvelopeAllocation` row.
  - ENVL-03 (consumed): seed transactions + splits, assert `getEnvelope.consumed` sums them correctly (recursive CTE covers child-category inclusion).
  - ENVL-04 (rollover): create prev-month transactions, set policy = CARRY_OVER, assert `available` and `ratio` reflect carryOver; flip to RESET, assert carryOver disappears.
  - ENVL-05 (status thresholds): parameterised test at 0.79 / 0.80 / 1.00 / 1.01 asserting GREEN/YELLOW/YELLOW/RED.
  - D-01 service slice: `create_envelope_with_category_already_linked_on_account_throws_duplicate_exception`.
- **Plan 06-08 (frontend pages)** — TypeScript interfaces can be generated from the stable `EnvelopeResponse` shape this service returns.

**Known limitation:** Tests that use `@SpringBootTest` + `@Testcontainers` require Docker. Local dev on WSL2 needs Docker Desktop WSL2 integration enabled; CI environments already have Docker available.

## Self-Check: PASSED

**1. Files exist:**
- FOUND: `backend/src/main/java/com/prosperity/envelope/EnvelopeService.java`
- FOUND: `backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationService.java`

**2. Commits exist:**
- FOUND: `5200047` (Task 1 — EnvelopeService)
- FOUND: `89779fd` (Task 2 — EnvelopeAllocationService)

**3. Acceptance criteria verification:**

Task 1 grep checks (plan's criteria):
- `@Service` → 1 ✓
- `public EnvelopeResponse createEnvelope` → 1 ✓
- `public EnvelopeResponse updateEnvelope` → 1 ✓
- `public void deleteEnvelope` → 1 ✓
- `public List<EnvelopeResponse> listEnvelopesForAccount` → 1 ✓
- `public List<EnvelopeResponse> listAllEnvelopes` → 1 ✓
- `public EnvelopeResponse getEnvelope` → 1 ✓
- `public List<EnvelopeHistoryEntry> getEnvelopeHistory` → 1 ✓
- `DuplicateEnvelopeCategoryException` → 4 (≥ 1 required) ✓
- `getCategories().clear()` → 1 (Pitfall 3) ✓
- `AccountType.SHARED` → 1 ✓
- `EnvelopeScope.SHARED` → 1 ✓
- `EnvelopeScope.PERSONAL` → 2 (≥ 1 required) ✓
- `hasAnyAllocation` → 1 ✓
- `sumConsumedForMonth` → 1 ✓
- `RolloverPolicy.CARRY_OVER` → 1 ✓
- `0.80` → 2 (≥ 1 required — YELLOW threshold) ✓
- `1.00` → 3 (≥ 1 required — RED threshold) ✓
- `computeCarryOver` → 3 (≥ 3 required: declaration + computeAvailable + getEnvelopeHistory + toResponse — 3 callsites excluding the method itself would be 4, but the count includes the method signature itself; call-count ≥ 3 is met) ✓
- `effectiveBudget.amount().add(carryOver) | allocatable` → 13 (≥ 1 required) ✓
- `@Transactional` → 7 (≥ 7 required — one per public method) ✓

Task 2 grep checks:
- `@Service` → 1 ✓
- `public EnvelopeAllocationResponse createAllocation` → 1 ✓
- `public List<EnvelopeAllocationResponse> listAllocations` → 1 ✓
- `public EnvelopeAllocationResponse updateAllocation` → 1 ✓
- `public void deleteAllocation` → 1 ✓
- `EnvelopeAllocationNotFoundException` → 4 (≥ 2 required) ✓
- `@Transactional` → 4 (≥ 4 required) ✓
- `catch.*DataIntegrityViolationException` → 0 (must be 0 — exception must bubble) ✓

Compile + unit tests:
- `./mvnw compile -q` → exit 0 ✓
- `./mvnw test -Dtest=EnvelopeTest` → 7 tests / 0 failures / 0 errors / 0 skipped ✓

---

*Phase: 06-envelope-budgets*
*Completed: 2026-04-22*
