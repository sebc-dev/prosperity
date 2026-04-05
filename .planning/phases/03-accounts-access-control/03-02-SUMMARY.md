---
phase: 03-accounts-access-control
plan: 02
subsystem: api
tags: [java, records, dto, jakarta-validation, exceptions]

# Dependency graph
requires:
  - phase: 03-accounts-access-control/03-01
    provides: AccessLevel enum, Account entity, AccountAccess entity, AccountType enum
provides:
  - CreateAccountRequest record with Jakarta Validation
  - UpdateAccountRequest record (nullable fields for PATCH)
  - AccountResponse record with currentUserAccessLevel
  - AccountAccessResponse record for access management responses
  - SetAccessRequest record for granting/updating access
  - AccountNotFoundException (RuntimeException, 404)
  - AccountAccessDeniedException (RuntimeException, 403)
affects:
  - 03-03-account-service
  - 03-04-account-controller
  - 03-05-account-service-tests

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Java records for DTOs (request/response) following auth package conventions"
    - "RuntimeException subclasses with String message constructor for domain exceptions"

key-files:
  created:
    - backend/src/main/java/com/prosperity/account/CreateAccountRequest.java
    - backend/src/main/java/com/prosperity/account/UpdateAccountRequest.java
    - backend/src/main/java/com/prosperity/account/AccountResponse.java
    - backend/src/main/java/com/prosperity/account/AccountAccessResponse.java
    - backend/src/main/java/com/prosperity/account/SetAccessRequest.java
    - backend/src/main/java/com/prosperity/account/AccountNotFoundException.java
    - backend/src/main/java/com/prosperity/account/AccountAccessDeniedException.java
  modified: []

key-decisions:
  - "UpdateAccountRequest uses all-nullable fields to support partial PATCH semantics (D-08)"
  - "AccountResponse embeds currentUserAccessLevel to avoid extra round-trips from the frontend"
  - "AccountAccessDeniedException returns 403 (not 404) per D-02 to avoid leaking account existence"

patterns-established:
  - "DTO pattern: Java records in feature package with Jakarta Validation annotations on request DTOs only"
  - "Exception pattern: RuntimeException subclass with single String message constructor, caught in controller"

requirements-completed: [ACCT-01, ACCT-02, ACCT-04, ACCS-01, ACCS-03]

# Metrics
duration: 3min
completed: 2026-04-05
---

# Phase 03 Plan 02: Account DTOs and Exceptions Summary

**5 Java record DTOs with Jakarta Validation and 2 custom RuntimeException classes for account CRUD and access management contracts**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-05T12:53:50Z
- **Completed:** 2026-04-05T12:55:22Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Created 5 DTO records covering the full account CRUD and access management API surface
- Created 2 domain exception classes for 404 (not found) and 403 (access denied) scenarios
- All files compile cleanly with `./mvnw compile`

## Task Commits

Each task was committed atomically:

1. **Task 1: Request and Response DTO records** - `26c3e3d` (feat)
2. **Task 2: Custom exception classes** - `d9af80f` (feat)

## Files Created/Modified
- `backend/src/main/java/com/prosperity/account/CreateAccountRequest.java` - Create account request with @NotBlank name and @NotNull AccountType
- `backend/src/main/java/com/prosperity/account/UpdateAccountRequest.java` - Partial update request with all-nullable fields for PATCH
- `backend/src/main/java/com/prosperity/account/AccountResponse.java` - Account response including currentUserAccessLevel
- `backend/src/main/java/com/prosperity/account/AccountAccessResponse.java` - Access entry response with user info and accessLevel
- `backend/src/main/java/com/prosperity/account/SetAccessRequest.java` - Grant/update access request with @NotNull userId and accessLevel
- `backend/src/main/java/com/prosperity/account/AccountNotFoundException.java` - 404 exception
- `backend/src/main/java/com/prosperity/account/AccountAccessDeniedException.java` - 403 exception

## Decisions Made
- `UpdateAccountRequest` uses all-nullable fields (no `@NotNull`) to support partial PATCH semantics — name, accountType, and archived can each be omitted independently
- `AccountResponse` embeds `currentUserAccessLevel` so the frontend can conditionally render actions without a separate access check call
- `AccountAccessDeniedException` signals a 403 (not 404) per D-02, ensuring access-denied and not-found are distinguishable for the controller

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All data contracts are defined; service layer (03-03) can now reference these DTOs and exceptions
- Controller layer (03-04) can implement exception handlers mapping AccountNotFoundException -> 404 and AccountAccessDeniedException -> 403

## Self-Check: PASSED

- All 7 created files: FOUND
- Commit 26c3e3d (feat: DTO records): FOUND
- Commit d9af80f (feat: exception classes): FOUND

---
*Phase: 03-accounts-access-control*
*Completed: 2026-04-05*
