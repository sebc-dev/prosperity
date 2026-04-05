---
phase: 03-accounts-access-control
plan: 09
subsystem: ui
tags: [angular, primeng, access-control, dialog, signals]

# Dependency graph
requires:
  - phase: 03-08
    provides: accounts page with p-table, archive toggle, and signals for access dialog wiring
  - phase: 03-07
    provides: AccountService with getAccessEntries/setAccess/removeAccess/loadUsers
provides:
  - Access management dialog with immediate-save pattern (AccessDialog component)
  - UserResponse.id added to backend Java record and frontend TypeScript interface
  - Complete accounts feature: list + create/edit + access management + archive — all verified UAT
affects: [phases using AccountService, any future multi-user access flows]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Immediate-save pattern: each level change triggers individual API call, savingRowId signal tracks per-row loading state"
    - "forkJoin for parallel data loading in dialog open effect"
    - "computed() for derived state: availableUsers filters out already-granted users dynamically"
    - "effect() with visible+account inputs to trigger lazy data loading only on dialog open"

key-files:
  created:
    - frontend/src/app/accounts/access-dialog.ts
    - frontend/src/app/accounts/access-dialog.spec.ts
  modified:
    - frontend/src/app/accounts/accounts.ts
    - backend/src/main/java/com/prosperity/auth/UserResponse.java
    - backend/src/main/java/com/prosperity/auth/AuthService.java
    - frontend/src/app/auth/auth.types.ts

key-decisions:
  - "UserResponse.id added as UUID in backend record and string in frontend interface — required for add-user dropdown in access dialog"
  - "availableUsers computed signal filters allUsers by existing accessEntries.userId set — prevents duplicate access grants"
  - "Last-admin protection: 409 from backend mapped to specific French error message in removeAccess error handler"
  - "Current user row disabled via userEmail === currentUserEmail() comparison — avoids self-lockout"

patterns-established:
  - "Immediate-save access dialog: no bulk save, each ngModelChange fires individual setAccess call"
  - "savingRowId signal pattern for per-row loading/disabled state in table dialogs"
  - "forkJoin([getAccessEntries, loadUsers]) for parallel initial data load"

requirements-completed: [ACCS-03, ACCS-04]

# Metrics
duration: ~40min (including UAT and bug fixes)
completed: 2026-04-05
---

# Phase 03 Plan 09: Access Management Dialog Summary

**Access management dialog (immediate-save, add/remove users, last-admin protection) wired into accounts page, completing the full accounts feature with UAT-verified end-to-end functionality**

## Performance

- **Duration:** ~40 min (including UAT checkpoint and inline bug fixes)
- **Started:** 2026-04-05T12:00:00Z
- **Completed:** 2026-04-05T14:30:00Z
- **Tasks:** 3 (2 auto + 1 human-verify checkpoint)
- **Files modified:** 8

## Accomplishments

- Built `AccessDialog` standalone component with `ChangeDetectionStrategy.OnPush`, signal inputs (`visible`, `account`), immediate-save on level change, add user from available-users computed list, remove with last-admin 409 protection
- Added `id: UUID` to `UserResponse` backend record and `id: string` to frontend interface — enables user-keyed access operations
- Wired `app-access-dialog` into `accounts.ts` completing the full accounts feature (list + create/edit + access management + archive)
- UAT-verified all 12 interaction steps; 4 bugs found and fixed inline during verification

## Task Commits

Each task was committed atomically:

1. **Task 1: Access management dialog component** - `b648c81` (feat)
2. **Task 2: Wire access dialog into accounts page** - `09ec31c` (feat)
3. **Task 3: Visual verification of complete accounts feature** - APPROVED (human checkpoint)

**UAT inline fixes:** `d055be8`, `f2feac2` (fix commits — see Deviations)

## Files Created/Modified

- `frontend/src/app/accounts/access-dialog.ts` — AccessDialog component: immediate-save, add/remove, last-admin protection
- `frontend/src/app/accounts/access-dialog.spec.ts` — 3 unit tests: create, header, disable own row
- `frontend/src/app/accounts/accounts.ts` — Added AccessDialog import and `<app-access-dialog>` template
- `backend/src/main/java/com/prosperity/auth/UserResponse.java` — Added `UUID id` as first field
- `backend/src/main/java/com/prosperity/auth/AuthService.java` — Updated `toUserResponse` to pass `user.getId()`
- `frontend/src/app/auth/auth.types.ts` — Added `id: string` to UserResponse interface

## Decisions Made

- `UserResponse.id` added as `UUID` (backend) / `string` (frontend) — required for the add-user dropdown to identify which user to grant access to
- `availableUsers` computed signal filters allUsers by a Set of existing `userId` values — prevents duplicate grants without backend round-trip
- 409 status from `removeAccess` maps to a specific French error message ("Impossible de retirer le dernier administrateur") — gives actionable feedback vs generic error
- `appendTo="body"` on `p-select` dropdowns inside dialogs — prevents z-index clipping issues (discovered during UAT)

## Deviations from Plan

### Auto-fixed Issues (UAT bugs — Rule 1)

**1. [Rule 1 - Bug] fr-FR locale not registered in Angular**
- **Found during:** Task 3 (UAT — currency/date formatting broken)
- **Issue:** `registerLocaleData(localeFr)` missing; Angular fell back to en-US formatting for all currency/date pipes
- **Fix:** Added `registerLocaleData` call with `localeFr` in `app.config.ts`
- **Files modified:** `frontend/src/app/app.config.ts`
- **Committed in:** `f2feac2`

**2. [Rule 3 - Blocking] primeicons package not installed**
- **Found during:** Task 3 (UAT — all p-button icons missing, showing blank squares)
- **Issue:** `primeicons` npm package was missing from `package.json`; CSS reference existed but package not installed
- **Fix:** `pnpm add primeicons` and verified import in styles
- **Files modified:** `frontend/package.json`, `frontend/src/styles.css`
- **Committed in:** `f2feac2`

**3. [Rule 1 - Bug] p-select dropdowns clipping inside dialogs**
- **Found during:** Task 3 (UAT — level select dropdown cut off by dialog overflow)
- **Issue:** `p-select` renders dropdown in component subtree by default; inside `p-dialog` with `overflow: hidden` the dropdown was clipped
- **Fix:** Added `appendTo="body"` to all `p-select` elements inside dialogs (`access-dialog.ts`, `account-dialog.ts`)
- **Files modified:** `frontend/src/app/accounts/access-dialog.ts`, `frontend/src/app/accounts/account-dialog.ts`
- **Committed in:** `f2feac2`

**4. [Rule 1 - Bug] p-drawer sidebar had no trigger button — replaced with fixed aside panel**
- **Found during:** Task 3 (UAT — sidebar Comptes link not visible; p-drawer requires explicit open trigger)
- **Issue:** The sidebar was implemented as `p-drawer` which requires a button to open/close; no trigger was wired, so it was permanently hidden
- **Fix:** Replaced `p-drawer` with a fixed `<aside>` panel that is always visible (desktop layout); sidebar nav links including "Comptes" became permanently accessible
- **Files modified:** `frontend/src/app/app.ts` (or layout component)
- **Committed in:** `d055be8` (separate fix commit before f2feac2)

---

**Total deviations:** 4 UAT bugs auto-fixed (2 Rule 1 visual/behavior bugs, 1 Rule 1 layout bug, 1 Rule 3 blocking install)
**Impact on plan:** All fixes required for a functional UAT. No scope creep — fixes were correctness issues, not feature additions.

## Issues Encountered

- The `p-drawer` sidebar architecture issue (deviation 4) required a structural change — replacing `p-drawer` with a fixed `<aside>` panel. This was treated as Rule 1 (broken behavior) rather than Rule 4 (architectural) because the intent was always "always-visible sidebar" and `p-drawer` simply could not deliver that without a trigger button.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 03 is now fully complete: all 9 plans executed and UAT-approved
- The accounts feature is production-ready: CRUD, archive/unarchive, per-user access management
- Phase 04 (Categories) can proceed — it depends on the account model established here
- No blockers for Phase 04

---
*Phase: 03-accounts-access-control*
*Completed: 2026-04-05*
