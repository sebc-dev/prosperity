---
phase: 03-accounts-access-control
plan: 07
subsystem: ui
tags: [angular, typescript, signals, http-client, routing, primeng]

# Dependency graph
requires:
  - phase: 03-accounts-access-control/03-02
    provides: backend DTOs (AccountResponse, AccountAccessResponse, etc.)
  - phase: 03-accounts-access-control/03-05
    provides: backend REST endpoints (/api/accounts, /api/users)
  - phase: 02-authentication-setup-wizard
    provides: auth.types.ts (UserResponse), auth.service.ts signal pattern
provides:
  - TypeScript interfaces matching backend account DTOs
  - AccountService with signal-based state and 7 HTTP methods
  - Sidebar navigation with Comptes link and active state styling
  - Lazy-loaded /accounts route inside layout shell
  - Placeholder Accounts component for route wiring
affects:
  - 03-08 (accounts list/detail components will use AccountService and Accounts route)
  - future phases using account data layer

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "HttpParams for conditional query params avoids TypeScript overload ambiguity with http.get"
    - "signal<T[]>([]).asReadonly() pattern for reactive Angular service state"
    - "RouterLink + RouterLinkActive with routerLinkActive class binding for active nav state"
    - "provideRouter([]) in component tests when RouterLink is imported"

key-files:
  created:
    - frontend/src/app/accounts/account.types.ts
    - frontend/src/app/accounts/account.service.ts
    - frontend/src/app/accounts/account.service.spec.ts
    - frontend/src/app/accounts/accounts.ts
  modified:
    - frontend/src/app/layout/sidebar.ts
    - frontend/src/app/layout/sidebar.spec.ts
    - frontend/src/app/app.routes.ts

key-decisions:
  - "HttpParams used for conditional query params: conditional object literal {} causes TypeScript to pick ArrayBuffer overload on http.get, HttpParams avoids the ambiguity"
  - "accounts.ts placeholder created immediately to prevent lazy-load build error before Plan 08"

patterns-established:
  - "Angular service tests: provideRouter([]) required when component imports RouterLink"

requirements-completed: [ACCT-03, ACCS-02]

# Metrics
duration: 5min
completed: 2026-04-05
---

# Phase 03 Plan 07: Frontend Data Layer & Navigation Summary

**Angular AccountService with signal-based state, TypeScript DTO contracts, and sidebar Comptes navigation wired to lazy-loaded /accounts route**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-05T13:23:33Z
- **Completed:** 2026-04-05T13:28:02Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments
- Created `account.types.ts` with TypeScript interfaces matching backend DTOs exactly (AccountResponse, CreateAccountRequest, UpdateAccountRequest, AccountAccessResponse, SetAccessRequest)
- Built `AccountService` with `signal<AccountResponse[]>([])` reactive state and 7 HTTP methods covering full backend API surface
- Updated sidebar with Comptes link (pi-wallet icon, active state styling via routerLinkActive), wired /accounts route as lazy-loaded child of layout shell

## Task Commits

Each task was committed atomically:

1. **Task 1: TypeScript interfaces and AccountService** - `67737b3` (feat)
2. **Task 2: Sidebar navigation + routing** - `20f2867` (feat)
3. **Task 3: AccountService unit tests** - `a3715af` (test)

## Files Created/Modified
- `frontend/src/app/accounts/account.types.ts` - TypeScript interfaces for AccountResponse, CreateAccountRequest, UpdateAccountRequest, AccountAccessResponse, SetAccessRequest
- `frontend/src/app/accounts/account.service.ts` - Injectable service with signal state and 7 HTTP methods (loadAccounts, createAccount, updateAccount, getAccessEntries, setAccess, removeAccess, loadUsers)
- `frontend/src/app/accounts/account.service.spec.ts` - 8 unit tests covering all HTTP methods and signal update verification
- `frontend/src/app/accounts/accounts.ts` - Placeholder component for /accounts route (to be replaced in Plan 08)
- `frontend/src/app/layout/sidebar.ts` - RouterLink + RouterLinkActive imports added, Comptes navigation link with pi-wallet icon and active state styling
- `frontend/src/app/layout/sidebar.spec.ts` - Added provideRouter([]) to fix RouterLink dependency in tests
- `frontend/src/app/app.routes.ts` - Added lazy-loaded /accounts route as child of layout shell

## Decisions Made
- `HttpParams` used instead of conditional object literal for `includeArchived` param: passing `{}` as params to `http.get<AccountResponse[]>` causes TypeScript to match the `ArrayBuffer` overload, producing a type error. `HttpParams` avoids the overload ambiguity.
- `accounts.ts` placeholder created in Task 2 to prevent lazy-load compilation errors; the plan noted this explicitly.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] TypeScript ArrayBuffer overload ambiguity in http.get**
- **Found during:** Task 1 (TypeScript interfaces and AccountService)
- **Issue:** `http.get<AccountResponse[]>('/api/accounts', { params: {} })` caused `TS2769: No overload matches` — TypeScript picked the `ArrayBuffer` overload when params was an empty object literal `{}`
- **Fix:** Replaced conditional params object with `HttpParams` — `let params = new HttpParams(); if (includeArchived) params = params.set('includeArchived', 'true')`
- **Files modified:** `frontend/src/app/accounts/account.service.ts`
- **Verification:** `ng build --configuration=development` succeeds
- **Committed in:** `67737b3` (Task 1 commit)

**2. [Rule 1 - Bug] sidebar.spec.ts failed after adding RouterLink import**
- **Found during:** Task 3 (AccountService unit tests, running test suite)
- **Issue:** Adding `RouterLink` and `RouterLinkActive` to sidebar.ts caused `NG0201: No provider found for ActivatedRoute` in sidebar.spec.ts — tests used `NO_ERRORS_SCHEMA` but RouterLink injects router services at runtime
- **Fix:** Added `provideRouter([])` to sidebar.spec.ts test configuration
- **Files modified:** `frontend/src/app/layout/sidebar.spec.ts`
- **Verification:** All 48 tests pass
- **Committed in:** `a3715af` (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (2x Rule 1 - Bug)
**Impact on plan:** Both fixes necessary for compilation and test correctness. No scope creep.

## Issues Encountered
None beyond the two auto-fixed bugs above.

## Known Stubs
- `frontend/src/app/accounts/accounts.ts` — placeholder component with hardcoded heading "Comptes bancaires", no data loaded. Intentional: Plan 08 will replace this with the full account list/detail component.

## Next Phase Readiness
- AccountService is ready for Plan 08 (account list/detail UI components)
- TypeScript contracts established — Plan 08 components can import directly from account.types.ts and inject AccountService
- /accounts route wired — Plan 08 just needs to replace the placeholder component

---
*Phase: 03-accounts-access-control*
*Completed: 2026-04-05*
