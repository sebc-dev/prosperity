---
phase: 03-accounts-access-control
plan: 05
subsystem: api
tags: [spring-mvc, rest, accounts, access-control, authentication-principal]

# Dependency graph
requires:
  - phase: 03-04
    provides: AccountService with full CRUD and access management business logic

provides:
  - AccountController exposing 7 REST endpoints for account CRUD and access management
  - UserController exposing GET /api/users for access dialog user dropdown
  - Exception handlers mapping AccountNotFoundException to 404, AccountAccessDeniedException to 403, IllegalStateException to 409

affects: [03-06, 03-07, 03-08, 03-09, frontend]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "@ExceptionHandler at controller level for domain exception -> HTTP status mapping"
    - "@AuthenticationPrincipal UserDetails to resolve current user, pass username to service"
    - "Dedicated UserController in auth package for /api/users to avoid class-level @RequestMapping path collision"

key-files:
  created:
    - backend/src/main/java/com/prosperity/account/AccountController.java
    - backend/src/main/java/com/prosperity/auth/UserController.java
  modified: []

key-decisions:
  - "UserController separate from AuthController: Spring MVC always concatenates class-level and method-level @RequestMapping paths, so adding @GetMapping(\"/api/users\") to AuthController (which has @RequestMapping(\"/api/auth\")) would produce /api/auth/api/users, not /api/users. Dedicated UserController with @RequestMapping(\"/api/users\") is the correct approach."

patterns-established:
  - "Controller exception handlers: domain exceptions mapped to HTTP codes within controller class via @ExceptionHandler — 404 for AccountNotFoundException, 403 for AccountAccessDeniedException, 409 for IllegalStateException"
  - "AuthenticationPrincipal pattern: all controller methods receive @AuthenticationPrincipal UserDetails and pass getUsername() to service layer — service never touches SecurityContextHolder"

requirements-completed: [ACCT-01, ACCT-02, ACCT-03, ACCT-04, ACCT-05, ACCS-02, ACCS-03]

# Metrics
duration: 1min
completed: 2026-04-05
---

# Phase 03 Plan 05: Accounts & Access Control — REST Controllers Summary

**AccountController (7 endpoints) and UserController (GET /api/users) exposing the service layer as REST API with proper HTTP status codes and @AuthenticationPrincipal resolution**

## Performance

- **Duration:** 1 min
- **Started:** 2026-04-05T13:03:24Z
- **Completed:** 2026-04-05T13:04:55Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- AccountController with 7 REST endpoints: POST (create 201), GET (list), GET/{id}, PATCH/{id}, GET/{id}/access, POST/{id}/access, DELETE/{id}/access/{accessId} (noContent 204)
- Exception handlers: AccountNotFoundException -> 404, AccountAccessDeniedException -> 403, IllegalStateException -> 409
- UserController with GET /api/users returning all users for access management dialog dropdown

## Task Commits

Each task was committed atomically:

1. **Task 1: AccountController REST endpoints** - `474b3c8` (feat)
2. **Task 2: Users list endpoint for access dialog** - `42531ee` (feat)

## Files Created/Modified

- `backend/src/main/java/com/prosperity/account/AccountController.java` — REST controller, 7 endpoints, exception handlers
- `backend/src/main/java/com/prosperity/auth/UserController.java` — GET /api/users endpoint for access dialog

## Decisions Made

- `UserController` in auth package instead of adding `listUsers` to `AuthController`: Spring MVC concatenates class-level and method-level @RequestMapping paths — `@GetMapping("/api/users")` on `AuthController` (which maps `/api/auth`) would resolve to `/api/auth/api/users`, not `/api/users`. Dedicated controller with `@RequestMapping("/api/users")` is correct.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Created UserController instead of adding method to AuthController**
- **Found during:** Task 2 (Users list endpoint for access dialog)
- **Issue:** Plan instructed adding `@GetMapping("/api/users")` directly to `AuthController` which has `@RequestMapping("/api/auth")`. Spring MVC concatenates these paths, resulting in `/api/auth/api/users` instead of the required `/api/users`.
- **Fix:** Created `UserController` in `com.prosperity.auth` package with `@RequestMapping("/api/users")` and the `listUsers` method. Same dependencies (`UserRepository`, `AuthService`) as the plan specified.
- **Files modified:** `backend/src/main/java/com/prosperity/auth/UserController.java` (new)
- **Verification:** `./mvnw compile -q` succeeds; endpoint maps to `/api/users` as required
- **Committed in:** `42531ee` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug — incorrect Spring MVC path mapping in plan)
**Impact on plan:** Fix essential for correct URL routing. No scope creep. Endpoint behavior identical to plan specification.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All 7 account REST endpoints available at `/api/accounts/**`
- GET `/api/users` available for frontend access management dialog
- HTTP status codes per specification: 201 (create), 200 (read/update), 204 (delete), 403 (access denied), 404 (not found), 409 (last admin conflict)
- Phase 03-06 (integration tests) can proceed: full endpoint surface is now exposed

---
*Phase: 03-accounts-access-control*
*Completed: 2026-04-05*
