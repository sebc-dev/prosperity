---
phase: 02-authentication-setup-wizard
plan: 07
subsystem: ui
tags: [angular, primeng, routing, layout, guards]

requires:
  - phase: 02-05
    provides: AuthService, route guards (authGuard, unauthenticatedGuard, setupGuard), auth interceptor
  - phase: 02-06
    provides: Setup wizard and Login page components
provides:
  - Layout shell (header + sidebar + router-outlet) for authenticated pages
  - Dashboard placeholder with personalized welcome
  - Complete route configuration with lazy loading and guard protection
  - App root wired to router-outlet
affects: [dashboard, navigation, accounts]

tech-stack:
  added: []
  patterns: [layout-shell-with-nested-routes, lazy-loading-all-routes]

key-files:
  created:
    - frontend/src/app/layout/header.ts
    - frontend/src/app/layout/sidebar.ts
    - frontend/src/app/layout/layout.ts
    - frontend/src/app/dashboard/dashboard.ts
  modified:
    - frontend/src/app/app.routes.ts
    - frontend/src/app/app.ts

key-decisions:
  - "Used setupGuard (existing code) instead of noAdminGuard (plan name) — adapted to actual codebase"
  - "Sidebar uses PrimeNG p-drawer with toggle method for future phase integration"

patterns-established:
  - "Layout shell pattern: authenticated pages render inside Layout component with nested router-outlet"
  - "Lazy loading: all routes use loadComponent for code splitting"

requirements-completed: [AUTH-01, AUTH-03, AUTH-04]

duration: 8min
completed: 2026-04-01
---

# Plan 02-07: Layout Shell, Dashboard & Routing Summary

**Layout shell with header/sidebar, dashboard placeholder, and complete route wiring with lazy loading and guard protection**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-01T19:05:00Z
- **Completed:** 2026-04-01T19:13:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Layout shell renders header (app title + logout button) with sidebar placeholder wrapping authenticated content
- Dashboard shows personalized "Bienvenue {display_name}" from AuthService user signal
- Routes connect setup (setupGuard), login (unauthenticatedGuard), and authenticated layout (authGuard) with lazy loading
- App root simplified to router-outlet — all page chrome handled by layout components

## Task Commits

Each task was committed atomically:

1. **Task 1: Create layout shell components** - `242ea15` (feat)
2. **Task 2: Create dashboard, routing, update app root** - `fc89b49` (feat)

## Files Created/Modified
- `frontend/src/app/layout/header.ts` - Header with app title and logout button (OnPush)
- `frontend/src/app/layout/sidebar.ts` - Empty drawer placeholder for future navigation
- `frontend/src/app/layout/layout.ts` - Shell wrapping header + sidebar + router-outlet
- `frontend/src/app/dashboard/dashboard.ts` - Personalized welcome message placeholder
- `frontend/src/app/app.routes.ts` - Complete route config with guards and lazy loading
- `frontend/src/app/app.ts` - Simplified to router-outlet only

## Decisions Made
- Used `setupGuard` from existing codebase instead of `noAdminGuard` referenced in plan — same semantics, matches actual code
- Used `protected` visibility for authService in Dashboard to allow template access with OnPush
- All components use ChangeDetectionStrategy.OnPush following project convention

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] ChangeDetection enum required**
- **Found during:** Task 1 (layout components)
- **Issue:** Angular 21 rejects `changeDetection: 0` numeric literal — requires explicit enum
- **Fix:** Changed to `ChangeDetectionStrategy.OnPush` import
- **Files modified:** All 4 new component files
- **Verification:** `pnpm build` passes, `pnpm lint` passes
- **Committed in:** 242ea15 and fc89b49

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Angular 21 strictness fix, no scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All frontend auth pages wired: setup -> login -> dashboard flow complete
- Backend plans (02-03, 02-04) still needed for end-to-end functionality
- Layout ready for future navigation items in sidebar

---
*Phase: 02-authentication-setup-wizard*
*Completed: 2026-04-01*
