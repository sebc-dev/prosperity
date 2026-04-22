---
phase: 06-envelope-budgets
plan: 05
subsystem: api
tags: [rest, controller, spring-boot, spring-web, envelope, exception-handler, http-status, yearmonth]

requires:
  - phase: 06-envelope-budgets
    provides: EnvelopeService / EnvelopeAllocationService method signatures (Plan 04), DTO records + exceptions (Plan 02), entities + repositories (Plan 01)
  - phase: 03-accounts-access
    provides: AccountAccessDeniedException (403 mapping), AccountNotFoundException (404 mapping), existsById+access check 404/403 convention
  - phase: 04-categories
    provides: CategoryNotFoundException (404 mapping)
  - phase: 05-transactions
    provides: TransactionController canonical @ExceptionHandler + Principal patterns
provides:
  - EnvelopeController (8 routes: create, list-by-account, list-all, get, update, delete, history + account-filter variant)
  - EnvelopeAllocationController (4 routes: create, list, update, delete)
  - HTTP status mapping for all envelope exceptions (404/403/409)
  - DataIntegrityViolation -> 409 scoped to allocation controller only
  - YearMonth query param binding via @DateTimeFormat(pattern="yyyy-MM")
affects: [06-06-backend-tests, 06-07-frontend-infrastructure, 06-08-frontend-pages]

tech-stack:
  added: []
  patterns:
    - "@DateTimeFormat(pattern=\"yyyy-MM\") for YearMonth query binding (Spring Boot 4.0 native)"
    - "Controller-scoped @ExceptionHandler(DataIntegrityViolationException.class) — NOT @ControllerAdvice — so other controllers keep default Spring handling"
    - "Map<String,String> error body (short-form @ResponseStatus on handler method) matches Phase 3/5 style"
    - "Principal#getName() for userEmail (Phase 5 TransactionController convention) instead of @AuthenticationPrincipal UserDetails"

key-files:
  created:
    - backend/src/main/java/com/prosperity/envelope/EnvelopeController.java
    - backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationController.java
  modified: []

key-decisions:
  - "Controllers use Principal#getName() (Phase 5 TransactionController pattern) instead of @AuthenticationPrincipal UserDetails (Phase 3 AccountController pattern) — thinner, fewer imports, same userEmail outcome"
  - "DataIntegrityViolationException handler lives on EnvelopeAllocationController only — not @ControllerAdvice — to avoid changing default 500 behavior for other controllers that might legitimately surface DB errors"
  - "Split into two controllers (Envelope vs EnvelopeAllocation) instead of single EnvelopeController — atomic decoupling for reviewability (plan directive); ~150 + ~105 lines each vs ~250 combined"
  - "French error message for duplicate allocation ('Une personnalisation existe deja pour ce mois sur cette enveloppe') — consistent with French product copy; backend error body language aligns with UI locale"
  - "Short-form @ResponseStatus(HttpStatus.X) above @ExceptionHandler methods returning Map<String,String> — cleaner than ResponseEntity builder; matches plan template verbatim; diverges from Phase 3/5 ResponseEntity.status().body() style but preserves observable HTTP contract"

patterns-established:
  - "Controller-scoped DataIntegrityViolationException -> 409 mapping (not @ControllerAdvice): scope error translation to the controller that owns the constraint"
  - "Two-controller split for domain-with-sub-resource: root entity controller + child entity controller (pattern reusable for future N:1 sub-resources)"

requirements-completed:
  - ENVL-01
  - ENVL-02
  - ENVL-06
  - ENVL-07

duration: 2min
completed: 2026-04-22
---

# Phase 06 Plan 05: Controllers Summary

**REST surface for envelope budgets: EnvelopeController (CRUD + 12-month history) and EnvelopeAllocationController (monthly overrides) with full HTTP status mapping via @ExceptionHandler — 12 routes total, all exceptions translated to 404/403/409 per contract.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-22T11:43:09Z
- **Completed:** 2026-04-22T11:45:25Z
- **Tasks:** 2
- **Files created:** 2

## Accomplishments

- **EnvelopeController**: 8 endpoints covering account-scoped create/list, cross-account list (with optional `accountId` filter), envelope-scoped get/update/delete, and the 12-month history query with `YearMonth` binding from `yyyy-MM` query param. Five exception handlers translate `EnvelopeNotFoundException`, `AccountNotFoundException`, `CategoryNotFoundException` to 404, `AccountAccessDeniedException` to 403, and `DuplicateEnvelopeCategoryException` to 409.
- **EnvelopeAllocationController**: 4 endpoints for monthly override CRUD (create, list ordered by month asc, update, delete). Five exception handlers cover `EnvelopeNotFoundException`/`EnvelopeAllocationNotFoundException`/`AccountNotFoundException` (404), `AccountAccessDeniedException` (403), and the distinctive `DataIntegrityViolationException -> 409` mapping that translates the `UNIQUE(envelope_id, month)` constraint into a user-friendly conflict response.
- Both controllers wire ENVL-01, ENVL-02, ENVL-06 and ENVL-07 on the API surface; Plan 04 services are now reachable from the frontend once merged.

## Task Commits

Each task was committed atomically:

1. **Task 1: EnvelopeController (CRUD + history) with exception handlers** — `9f26020` (feat)
2. **Task 2: EnvelopeAllocationController + DataIntegrityViolation -> 409 mapping** — `cb0a64e` (feat)

## Files Created/Modified

- `backend/src/main/java/com/prosperity/envelope/EnvelopeController.java` — 151 lines. 8 routes + 5 @ExceptionHandler methods. `@RequestMapping("/api")` with per-method path suffixes (matches TransactionController convention). `@DateTimeFormat(pattern="yyyy-MM")` binds `YearMonth` from query params natively; `month` param defaults to `YearMonth.now()` when omitted (per plan's "defaults to current month" truth).
- `backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationController.java` — 105 lines. 4 routes + 5 @ExceptionHandler methods. DataIntegrityViolation handler deliberately scoped to this controller (not `@ControllerAdvice`) so other controllers keep their default Spring behavior.

## Decisions Made

- **Principal#getName() over @AuthenticationPrincipal UserDetails**: Plan 05 mirrors the Phase 5 TransactionController pattern exactly (`principal.getName()` resolves userEmail). Phase 3 AccountController uses `@AuthenticationPrincipal UserDetails userDetails.getUsername()` — either works, but Phase 5 is the most recent canonical style and keeps imports minimal.
- **Two controllers, not one**: Per plan directive (atomic decoupling), envelope CRUD and allocation CRUD live in separate files. Each stays under ~150 lines, easier to review, and exception handler blocks stay scoped to each controller's concerns.
- **Controller-scoped DataIntegrityViolationException handler**: A `@ControllerAdvice`-scoped handler would 409-ify every DB integrity violation across the entire app, including unrelated transaction or account constraint errors. Scoping to EnvelopeAllocationController keeps the translation local to the constraint that owns it (`UNIQUE(envelope_id, month)` on the `envelope_allocations` table).
- **Short-form @ResponseStatus on @ExceptionHandler methods**: The plan template uses `@ResponseStatus(HttpStatus.X)` on the handler method returning `Map<String, String>` directly, instead of the Phase 3/5 `ResponseEntity.status().body()` builder form. The observable HTTP contract (status + body) is identical; this form is slightly terser.
- **French error message for duplicate allocation**: The controller exception body message is user-facing copy (shown in frontend toasts per UI-SPEC). Product copy across the app is French; backend error strings for conflict mapping follow suit.

## Deviations from Plan

None — plan executed exactly as written. Both controllers match the plan's code templates verbatim (imports, route paths, handler signatures, status codes).

Note on compile verification: the plan's `<verify><automated>./mvnw compile` step cannot pass on this branch alone because `EnvelopeService` and `EnvelopeAllocationService` (Plan 04 deliverables) are built in a parallel worktree and have not yet merged to `gsd/phase-06-envelope-budgets`. This is expected parallel-wave behavior — the orchestrator explicitly instructed: "Task 1 of Plan 05 only needs EnvelopeService/EnvelopeAllocationService METHOD SIGNATURES to wire the controller." The phase integration step will run the full compile after both Wave 2 plans merge; controller signatures were written against the exact signatures in `06-04-service-layer-PLAN.md` <interfaces> block, so integration compile is expected to pass without further edits.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **Plan 06 (backend tests)**: Can fill assertions against stable route paths + HTTP status codes. Plan 03's @Disabled MockMvc scaffolds already expect `/api/envelopes` and `/api/envelopes/allocations/{id}` shapes.
- **Plan 07 (frontend infrastructure)**: Angular HttpClient services can typesafe-generate client code against the route surface documented here (8 envelope routes + 4 allocation routes, all returning the records defined in Plan 02).
- **Phase-level verifier**: Once Plan 04 merges, `./mvnw -pl backend compile` and `./mvnw -pl backend test -Dtest=ProsperityApplicationTest` will both pass — nothing on the controller side needs further changes.

---
*Phase: 06-envelope-budgets*
*Completed: 2026-04-22*

## Self-Check: PASSED

Verified files exist on disk:
- FOUND: backend/src/main/java/com/prosperity/envelope/EnvelopeController.java
- FOUND: backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationController.java
- FOUND: .planning/phases/06-envelope-budgets/06-05-controllers-SUMMARY.md

Verified commits exist:
- FOUND: 9f26020 (Task 1 — EnvelopeController)
- FOUND: cb0a64e (Task 2 — EnvelopeAllocationController)

Acceptance criteria greps all pass (18/18 for Task 1, 9/9 for Task 2).

Compile verification deferred to phase integration: `./mvnw compile` blocked by Plan 04 parallel dependency (EnvelopeService / EnvelopeAllocationService not yet on this branch). This is expected parallel-wave behavior — the orchestrator's prompt explicitly instructed writing against method signatures only.
