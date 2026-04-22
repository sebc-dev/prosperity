---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 06-06 backend-tests (54 Testcontainers behavior tests — 26 service + 21 controller + 7 allocation controller)
last_updated: "2026-04-22T12:07:32.228Z"
last_activity: 2026-04-22
progress:
  total_phases: 10
  completed_phases: 5
  total_plans: 48
  completed_plans: 47
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-28)

**Core value:** Un foyer peut suivre ses finances au quotidien (soldes, transactions, budgets enveloppes) sans effort manuel excessif, grace a la synchronisation bancaire automatique et une interface claire.
**Current focus:** Phase 06 — envelope-budgets

## Current Position

Phase: 06 (envelope-budgets) — EXECUTING
Plan: 7 of 8
Status: Ready to execute
Last activity: 2026-04-22

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01 P06 | 3min | 1 tasks | 24 files |
| Phase 01 P12 | 1min | 1 tasks | 3 files |
| Phase 01 P13 | 2min | 1 tasks | 4 files |
| Phase 01 P04 | 1min | 1 tasks | 4 files |
| Phase 01 P05 | 1min | 1 tasks | 2 files |
| Phase 01 P11 | 1min | 1 tasks | 1 files |
| Phase 01 P14 | 1min | 1 tasks | 1 files |
| Phase 02 P01 | 1min | 2 tasks | 3 files |
| Phase 02 P05 | 2min | 3 tasks | 8 files |
| Phase 02 P02 | 1min | 2 tasks | 5 files |
| Phase 02 P06 | 1min | 2 tasks | 2 files |
| Phase 02 P03 | 2min | 2 tasks | 3 files |
| Phase 02 P04 | 11min | 2 tasks | 7 files |
| Phase 03 P01 | 1 | 2 tasks | 3 files |
| Phase 03 P02 | 3 | 2 tasks | 7 files |
| Phase 03 P03 | 1min | 2 tasks | 2 files |
| Phase 03 P04 | 2 | 2 tasks | 1 files |
| Phase 03 P05 | 1 | 2 tasks | 2 files |
| Phase 03 P06 | 14min | 2 tasks | 4 files |
| Phase 03 P07 | 5min | 3 tasks | 7 files |
| Phase 03 P08 | 4 | 2 tasks | 4 files |
| Phase 03 P09 | 40 | 3 tasks | 8 files |
| Phase 04 P01 | 4min | 2 tasks | 9 files |
| Phase 04 P03 | 4min | 1 tasks | 6 files |
| Phase 04 P04 | 5min | 3 tasks | 11 files |
| Phase 05 P03 | 3min | 2 tasks | 2 files |
| Phase 05 P04 | 36min | 2 tasks | 7 files |
| Phase 06 P02 | 3min | 2 tasks | 10 files |
| Phase 06 P03 | 4min | 3 tasks | 4 files |
| Phase 06 P01 | 6min | 4 tasks | 5 files |
| Phase 06 P05 | 2min | 2 tasks | 2 files |
| Phase 06 P04 | 4min | 2 tasks | 2 files |
| Phase 06 P07 | 5min | 4 tasks | 10 files |
| Phase 06 P06 | 10min | 2 tasks | 9 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Flyway 11.x replaces Liquibase 5.0 (FSL license incompatible with open source constraint)
- [Roadmap]: ADMN-03 (Plaid config) grouped with Phase 7 (Plaid Integration), not Phase 8 (Administration)
- [Roadmap]: Categories split into own phase (Phase 4) before Transactions (Phase 5) -- envelopes and transactions both depend on categories
- [Revision]: Quality gates (INFR-04 to INFR-10) added to Phase 1 -- lint, format, static analysis, dead code, coverage thresholds, security scan, pre-commit hooks all enforced from day one
- [Phase 01]: PrimeNG 21 uses CSS-only theming via tailwindcss-primeui, no provider needed
- [Phase 01]: Angular 21 uses simplified naming (app.ts not app.component.ts) and Vitest instead of Karma
- [Phase 01]: Caddy listens on :80 only, HTTPS auto-configured with real domain in production
- [Phase 01]: Lefthook chosen over Husky for pre-commit hooks: language-agnostic, single YAML, parallel execution
- [Phase 01]: Account balance stored as cents via MoneyConverter, consistent with Money value object pattern
- [Phase 01]: TransactionState column added to Transaction entity for reconciliation workflow (not in database.md schema but required by plan)
- [Phase 01]: Reflection annotation test pattern: validate Spring annotations without loading context
- [Phase 01]: INFR-08 requirement overrides D-08: JaCoCo coverage thresholds now enforced (70% instruction, 50% branch)
- [Phase 02]: initialize-schema: never to let Flyway own session table lifecycle
- [Phase 02]: Angular signals (not BehaviorSubject) for reactive auth state -- Angular 21 modern pattern
- [Phase 02]: setup() does NOT set currentUser (per D-03: no auto-login after setup)
- [Phase 02]: CSRF SPA mode with ignoringRequestMatchers for login/setup POST endpoints
- [Phase 02]: DelegatingPasswordEncoder for future algorithm migration (bcrypt default)
- [Phase 02]: OnPush + signals for auth components, afterNextRender for autofocus
- [Phase 02]: Explicit SecurityContext session save per Spring Security 7 BFF cookie flow
- [Phase 02]: Generic error 'Identifiants invalides' on login failure to prevent user enumeration
- [Phase 02]: Testcontainers PostgreSQL 2.0 for integration tests (artifact: testcontainers-postgresql)
- [Phase 02]: Spring Boot 4 @AutoConfigureMockMvc in spring-boot-webmvc-test module
- [Phase 03]: archived column added via ALTER TABLE in V009 (not in initial schema V002 per D-06)
- [Phase 03]: AccessLevel.isAtLeast() uses ordinal comparison — enum declaration order READ(0) < WRITE(1) < ADMIN(2) must never change
- [Phase 03]: UpdateAccountRequest uses all-nullable fields for partial PATCH semantics (D-08)
- [Phase 03]: AccountAccessDeniedException returns 403 (not 404) per D-02 to avoid leaking account existence
- [Phase 03]: AccountRepository returns Object[] pairs [Account, AccessLevel] to avoid N+1 when projecting access level alongside account
- [Phase 03]: AccountAccessRepository uses Spring Data derived queries (no @Query) — method names map directly to JPA property navigation
- [Phase 03]: orElseThrow lambda in getAccount/updateAccount distinguishes 403 vs 404 via existsById check
- [Phase 03]: AccountService.setAccess uses orElseGet to create new AccountAccess lazily only when entry does not exist
- [Phase 03]: UserController separate from AuthController: Spring MVC concatenates class-level and method-level paths — @GetMapping("/api/users") on AuthController (@RequestMapping("/api/auth")) produces /api/auth/api/users, not /api/users
- [Phase 03]: findByIdAndUserId returns List<Object[]> not Optional<Object[]> to avoid Hibernate multi-projection wrapping bug
- [Phase 03]: HttpParams used for conditional query params: conditional object literal {} causes TypeScript to pick ArrayBuffer overload on http.get, HttpParams avoids the ambiguity
- [Phase 03]: provideRouter([]) required in Angular component tests when RouterLink is imported in the component under test
- [Phase 03]: p-toggleswitch uses plain boolean property (not signal) for ngModel two-way binding compatibility
- [Phase 03]: ConfirmationService provided at component level in providers array to scope confirm dialogs
- [Phase 03]: UserResponse.id added as UUID in backend record and string in frontend interface — required for add-user dropdown in access dialog
- [Phase 03]: Immediate-save access dialog: each ngModelChange fires individual setAccess call, savingRowId signal tracks per-row loading
- [Phase 04]: Deterministic UUID pattern a0000000-0000-0000-0000-00000000XXYY for Flyway seed categories
- [Phase 04]: 49 curated categories (14 roots + 35 children) for French household mapped to Plaid PFCv2
- [Phase 04]: No access control on PATCH category in Phase 4 -- backend-only endpoint, Phase 5 adds proper checks
- [Phase 04]: CategorySelector emits UUID string (node.data), not TreeNode object -- consumers work with UUIDs only
- [Phase 04]: Parent selector shows root-only categories to enforce 2-level depth constraint
- [Phase 04]: Shared component directory frontend/src/app/shared/ established for cross-module reuse
- [Phase 05]: generateTransaction sets state=MANUAL_UNMATCHED for reconciliation workflow consistency with manual transactions
- [Phase 05]: advanceNextDueDate clamps dayOfMonth to lengthOfMonth to correctly handle February and 31-day months
- [Phase 05]: Switched TransactionRepository.findByFilters from JPQL to native SQL with CAST for null-safe PostgreSQL type inference
- [Phase 05]: Native SQL sort uses column name (transaction_date) not Java field name (transactionDate)
- [Phase 06]: EnvelopeResponse.ratio denominator = effectiveBudget + carryOver (D-13 single source of truth, documented in Javadoc)
- [Phase 06]: CreateEnvelopeRequest omits scope field; scope derived server-side from account.accountType (Pitfall 4)
- [Phase 06]: EnvelopeCategoryRef declared as inner record in EnvelopeResponse to avoid leaking full Category DTO
- [Phase 06]: Consolidated EnvelopeServiceTest replaces proposed AllocationService/ConsumedAggregation/Rollover split — 26 @Disabled stubs cover same surface in one class
- [Phase 06]: AutoConfigureMockMvc imported from org.springframework.boot.webmvc.test.autoconfigure (Spring Boot 4.0.x package); legacy 3.x package does not exist in 4.0.5
- [Phase 06]: Frontend test scaffolds deferred to Plan 08 (Wave 4) — Vitest specs colocate with component files
- [Phase 06]: [Phase 06 P01] Envelope entity @ManyToMany Set<Category> via envelope_categories join table + archived flag (D-01 + D-18); junction uses composite PK, CASCADE on envelope, RESTRICT on category
- [Phase 06]: [Phase 06 P01] Consumed aggregation uses native recursive CTE over categories.parent_id plus NOT EXISTS defensive dedup on transactions+transaction_splits UNION ALL branches (guards against D-06 drift)
- [Phase 06]: [Phase 06 P01] 12-month history uses generate_series with CAST(:to AS date) - INTERVAL '1 day' so half-open [from, to) yields exactly 12 buckets; months with zero consumption appear via LEFT JOIN
- [Phase 06]: [Phase 06 P05] Controllers split: EnvelopeController (8 routes) + EnvelopeAllocationController (4 routes) in two files for atomic review; Principal#getName() over @AuthenticationPrincipal UserDetails to match Phase 5 TransactionController canon
- [Phase 06]: [Phase 06 P05] DataIntegrityViolationException -> 409 handler scoped to EnvelopeAllocationController only (not @ControllerAdvice) to avoid over-translating DB errors in unrelated controllers; @DateTimeFormat(pattern=yyyy-MM) for native YearMonth query binding in Spring Boot 4.0
- [Phase 06]: EnvelopeService.computeRatio denominator = effectiveBudget + carryOver (D-13 single source of truth) — shared by toResponse and getEnvelopeHistory
- [Phase 06]: [Phase 06 P04] Rollover helper split: resolveEffectiveBudget + sumConsumed + computeCarryOver compose into computeAvailable AND into the per-month getEnvelopeHistory loop (1-month lookback, zero-clamp, no chaining)
- [Phase 06]: [Phase 06 P04] Pitfall 3 enforced in updateEnvelope: env.getCategories().clear() + addAll() mutates managed @ManyToMany Set in place (never setCategories)
- [Phase 06]: [Phase 06 P04] EnvelopeAllocationService intentionally duplicates requireEnvelopeAccess helper from EnvelopeService — duplication beats premature abstraction across only 2 services
- [Phase 06]: [Phase 06 P07] CategorySelector extended to dual-mode via selectionMode input; onSelect/onClear renamed to onSingleSelect/onSingleClear (no external callers); new categoriesSelected output emits string[] for checkbox mode
- [Phase 06]: [Phase 06 P07] Stub components (EnvelopesPage / EnvelopeDetailsPage) created in Plan 07 to keep lazy-route type-check green until Plan 08 overwrites them — avoids cross-plan build breakage during parallel waves
- [Phase 06]: [Phase 06 P07] EnvelopeService cache signal shared by loadEnvelopes and loadEnvelopesForAccount — one readonly cache simplifies list page consumption, endpoint choice is a load-time decision
- [Phase 06]: [Phase 06 P06] EnvelopeServiceTest uses ZoneId.systemDefault() with LocalDate.now / YearMonth.now to align test time source with service's YearMonth.now() call (no Clock injection); errorprone JavaTimeDefaultTimeZone satisfied
- [Phase 06]: [Phase 06 P06] DELETE hard-vs-soft observed via status().isNoContent() + follow-up envelopeRepository.findById / isArchived read — preserves public-API-only testing while asserting the observable state change
- [Phase 06]: [Phase 06 P06] Spotless side-effect on Plan 04/05 envelope sources committed as separate chore(06-06) — 6 touch-only reformat files kept out of test-logic commits; Rule 3 blocking-issue fix for ./mvnw verify spotless:check gate

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 7 (Plaid): Needs research-phase -- Plaid EU/FR specific behaviors, institution availability for SG and Banque Populaire
- Envelope shared visibility: clarify whether User A and User B see same envelopes on shared account (decision needed before Phase 6)

## Session Continuity

Last session: 2026-04-22T12:07:32.224Z
Stopped at: Completed 06-06 backend-tests (54 Testcontainers behavior tests — 26 service + 21 controller + 7 allocation controller)
Resume file: None
