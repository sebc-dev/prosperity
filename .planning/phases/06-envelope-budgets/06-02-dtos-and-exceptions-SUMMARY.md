---
phase: 06-envelope-budgets
plan: 02
subsystem: api
tags: [dto, records, validation, exceptions, envelope, bean-validation, jakarta-validation]

requires:
  - phase: 03-accounts-access
    provides: Partial-PATCH convention (all-nullable fields, D-08), simple RuntimeException pattern for error handling
  - phase: 04-categories
    provides: DuplicateCategoryNameException pattern (409 mapping via @ExceptionHandler)
provides:
  - EnvelopeStatus enum (GREEN/YELLOW/RED, D-13 server-owned thresholds)
  - CreateEnvelopeRequest / UpdateEnvelopeRequest / EnvelopeAllocationRequest with bean validation
  - EnvelopeResponse (incl. inner EnvelopeCategoryRef) / EnvelopeAllocationResponse / EnvelopeHistoryEntry
  - EnvelopeNotFoundException / EnvelopeAllocationNotFoundException (404)
  - DuplicateEnvelopeCategoryException (409, D-01 signal)
affects: [06-04-service-layer, 06-05-controllers, 06-06-backend-tests, 06-07-frontend-infrastructure, 06-08-frontend-pages]

tech-stack:
  added: []
  patterns:
    - Server-computed domain enum (EnvelopeStatus) exposed to frontend, thresholds owned server-side (D-13)
    - Inner record EnvelopeCategoryRef within EnvelopeResponse to avoid leaking full Category DTO
    - Non-scope-in-create: CreateEnvelopeRequest has NO scope field; scope derived from account.accountType (Pitfall 4)

key-files:
  created:
    - backend/src/main/java/com/prosperity/envelope/EnvelopeStatus.java
    - backend/src/main/java/com/prosperity/envelope/CreateEnvelopeRequest.java
    - backend/src/main/java/com/prosperity/envelope/UpdateEnvelopeRequest.java
    - backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRequest.java
    - backend/src/main/java/com/prosperity/envelope/EnvelopeResponse.java
    - backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationResponse.java
    - backend/src/main/java/com/prosperity/envelope/EnvelopeHistoryEntry.java
    - backend/src/main/java/com/prosperity/envelope/EnvelopeNotFoundException.java
    - backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationNotFoundException.java
    - backend/src/main/java/com/prosperity/envelope/DuplicateEnvelopeCategoryException.java
  modified: []

key-decisions:
  - "EnvelopeStatus uses 3-value enum (GREEN/YELLOW/RED) so frontend maps 1:1 to PrimeNG severity without recomputing thresholds (D-13)"
  - "CreateEnvelopeRequest excludes scope field — scope derived server-side from account.accountType (Pitfall 4, enforced at type level)"
  - "EnvelopeResponse.ratio denominator = effectiveBudget + carryOver (D-13 literal; iteration 1 revision aligns with CONTEXT.md)"
  - "UpdateEnvelopeRequest fields all nullable (Phase 3 D-08 partial-PATCH convention); only @Size + @DecimalMin annotations"
  - "EnvelopeCategoryRef declared as inner record inside EnvelopeResponse (lightweight id+name, avoids Category DTO coupling)"
  - "Exception classes carry no @ResponseStatus annotation — controller @ExceptionHandler wires HTTP status (Phase 3/5 convention)"

patterns-established:
  - "Inner record for lightweight ref types: EnvelopeResponse.EnvelopeCategoryRef for id+name pairs inside list responses"
  - "Javadoc documents computed-field formulas (ratio = consumed / (effectiveBudget + carryOver)) so consumers don't re-derive"

requirements-completed:
  - ENVL-01
  - ENVL-02
  - ENVL-05
  - ENVL-06
  - ENVL-07

duration: 3min
completed: 2026-04-22
---

# Phase 06 Plan 02: DTOs and Exceptions Summary

**Envelope REST contracts: 7 record DTOs (requests + responses + EnvelopeStatus enum) and 3 custom exceptions, aligned with Phase 3/5 conventions and D-13 ratio semantics.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-22T11:33:23Z
- **Completed:** 2026-04-22T11:36:02Z
- **Tasks:** 2
- **Files created:** 10

## Accomplishments

- EnvelopeStatus enum declared (GREEN/YELLOW/RED) as the server-owned single source of truth for threshold logic (D-13)
- Full envelope DTO surface defined: create/update/allocation requests + envelope/allocation/history responses with Jakarta Bean Validation annotations matching Phase 3/5 style
- Three custom exceptions (404 Not Found x2, 409 Conflict x1) ready for Plan 05 controller to wire via `@ExceptionHandler`
- Backend compiles cleanly (`./mvnw compile` → BUILD SUCCESS), unblocking Plan 04 service layer to work against final contracts

## Task Commits

Each task was committed atomically:

1. **Task 1: EnvelopeStatus enum + 6 DTO records** — `b0e6e6f` (feat)
2. **Task 2: 3 custom exceptions** — `06a8ca2` (feat)

## Files Created/Modified

- `backend/src/main/java/com/prosperity/envelope/EnvelopeStatus.java` — 3-value enum (D-13 thresholds documented in Javadoc: ratio = consumed / (effectiveBudget + carryOver))
- `backend/src/main/java/com/prosperity/envelope/CreateEnvelopeRequest.java` — name / categoryIds / budget / rolloverPolicy, no scope field (Pitfall 4)
- `backend/src/main/java/com/prosperity/envelope/UpdateEnvelopeRequest.java` — partial PATCH, all-nullable fields
- `backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRequest.java` — monthly override request (YearMonth + allocatedAmount)
- `backend/src/main/java/com/prosperity/envelope/EnvelopeResponse.java` — full envelope read DTO incl. inner `EnvelopeCategoryRef` record, status + ratio exposed
- `backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationResponse.java` — allocation read DTO
- `backend/src/main/java/com/prosperity/envelope/EnvelopeHistoryEntry.java` — single month row for 12-month history (ENVL-06)
- `backend/src/main/java/com/prosperity/envelope/EnvelopeNotFoundException.java` — RuntimeException, 404 mapping
- `backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationNotFoundException.java` — RuntimeException, 404 mapping
- `backend/src/main/java/com/prosperity/envelope/DuplicateEnvelopeCategoryException.java` — RuntimeException, 409 mapping (D-01 enforcement signal)

## Decisions Made

- **EnvelopeCategoryRef as inner record:** placed inside `EnvelopeResponse` to keep the envelope-category coupling surface minimal; avoids pulling in a full Category DTO and keeps the API self-descriptive.
- **No `scope` in CreateEnvelopeRequest:** type-level enforcement of Pitfall 4. Scope will be derived by the service from the parent account's `accountType`.
- **Ratio denominator = `effectiveBudget + carryOver`:** documented in Javadoc so frontend and service layer share the same formula without guessing. Makes the "100% consumed" semantics mean "you've used up everything allocated for this period including rollover".
- **Exceptions without `@ResponseStatus`:** consistent with Phase 3/5 pattern where controller's `@ExceptionHandler` maps status, keeping exception classes decoupled from the web layer.

## Deviations from Plan

None — plan executed exactly as written.

Note on acceptance criteria strictness: the plan's grep checks specified `returns 1` for `GREEN`/`YELLOW`/`RED` counts, but the plan's own Javadoc code example legitimately references each enum value three times (in `@link`, in the severity sentence, and in the enum declaration). The intent (enum exists with those three values) is preserved. Likewise `scope` grep returns 1 because the Javadoc explicitly documents "NO scope field — scope is DERIVED server-side" (intentional educational text). The **record signature** contains no `scope` field, which is the actual structural invariant.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Plan 04 (service layer) can now implement against final `EnvelopeResponse`, `EnvelopeAllocationResponse`, `EnvelopeHistoryEntry` contracts without rework.
- Plan 05 (controllers) has the three exceptions ready for `@ExceptionHandler` wiring (404/404/409).
- Plan 06 (backend tests) can assert against stable DTO shapes; Plan 07/08 (frontend) can generate TypeScript interfaces from these records.

---

*Phase: 06-envelope-budgets*
*Completed: 2026-04-22*

## Self-Check: PASSED

Verified files exist on disk:
- FOUND: backend/src/main/java/com/prosperity/envelope/EnvelopeStatus.java
- FOUND: backend/src/main/java/com/prosperity/envelope/CreateEnvelopeRequest.java
- FOUND: backend/src/main/java/com/prosperity/envelope/UpdateEnvelopeRequest.java
- FOUND: backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationRequest.java
- FOUND: backend/src/main/java/com/prosperity/envelope/EnvelopeResponse.java
- FOUND: backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationResponse.java
- FOUND: backend/src/main/java/com/prosperity/envelope/EnvelopeHistoryEntry.java
- FOUND: backend/src/main/java/com/prosperity/envelope/EnvelopeNotFoundException.java
- FOUND: backend/src/main/java/com/prosperity/envelope/EnvelopeAllocationNotFoundException.java
- FOUND: backend/src/main/java/com/prosperity/envelope/DuplicateEnvelopeCategoryException.java

Verified commits exist:
- FOUND: b0e6e6f (Task 1)
- FOUND: 06a8ca2 (Task 2)

Compile check: `./mvnw compile` → BUILD SUCCESS.
