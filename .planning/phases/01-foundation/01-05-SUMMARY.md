---
phase: 01-foundation
plan: 05
subsystem: ui
tags: [svelte5, tailwind4, components, sidebar, accounts-ui, color-picker, i18n, responsive]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: Account CRUD API (POST/GET /api/accounts), User management API (/api/users/me), JWT auth with httpOnly cookies, Paraglide i18n setup
provides:
  - UI component library (Button, Input, Card, Badge, Select, ColorPicker) with dark mode
  - App layout with responsive sidebar navigation and logout
  - Accounts page with colored cards grouped Personal/Shared with dual balance
  - Account creation form with name, bank, type, currency, initial balance, color
  - Dashboard placeholder with welcome message
affects: [01-06, 02-transactions, all-frontend-features]

# Tech tracking
tech-stack:
  added: []
  patterns: [ui-component-library, responsive-sidebar-layout, colored-account-cards, progressive-enhancement]

key-files:
  created:
    - prosperity-web/src/lib/components/ui/Button.svelte
    - prosperity-web/src/lib/components/ui/Input.svelte
    - prosperity-web/src/lib/components/ui/Card.svelte
    - prosperity-web/src/lib/components/ui/Badge.svelte
    - prosperity-web/src/lib/components/ui/Select.svelte
    - prosperity-web/src/lib/components/ui/ColorPicker.svelte
    - prosperity-web/src/lib/components/AccountCard.svelte
    - prosperity-web/src/routes/(app)/+layout.svelte
    - prosperity-web/src/routes/(app)/+layout.server.ts
    - prosperity-web/src/routes/(app)/+page.svelte
    - prosperity-web/src/routes/(app)/accounts/+page.svelte
    - prosperity-web/src/routes/(app)/accounts/+page.server.ts
    - prosperity-web/src/routes/(app)/accounts/new/+page.svelte
    - prosperity-web/src/routes/(app)/accounts/new/+page.server.ts
    - prosperity-web/src/routes/logout/+page.server.ts
  modified:
    - prosperity-web/messages/fr.json
    - prosperity-web/messages/en.json

key-decisions:
  - "App layout fetches user from /api/users/me (not just JWT claims) for fresh data"
  - "Logout via separate /logout route with form action clearing cookies"
  - "AccountCard uses Intl.NumberFormat for locale-aware currency formatting"
  - "ColorPicker uses 10 preset colors with hidden input for form submission"

patterns-established:
  - "UI components: Props interface with variant/size, Tailwind classes via $derived, dark mode via dark: prefix"
  - "App layout: Desktop sidebar + mobile hamburger menu, nav items array for DRY rendering"
  - "Account cards: Color bar on top, dual balance grid, type badge via Badge component"
  - "Form pages: use:enhance for progressive enhancement, fail() for validation errors, redirect on success"

requirements-completed: [AUTH-04, ACCT-01]

# Metrics
duration: 5min
completed: 2026-03-09
---

# Phase 1 Plan 05: UI Components, App Layout & Accounts Page Summary

**Svelte 5 component library (Button, Input, Card, Badge, Select, ColorPicker) with responsive sidebar layout, accounts page showing colored cards grouped Personal/Shared with dual balance, and account creation form**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-09T06:49:08Z
- **Completed:** 2026-03-09T06:54:33Z
- **Tasks:** 2
- **Files modified:** 17

## Accomplishments
- UI component library with 6 reusable components (Button, Input, Card, Badge, Select, ColorPicker) all supporting dark mode and consistent Linear/Vercel design
- Responsive app layout with desktop sidebar (logo, nav links, user info, logout) and mobile hamburger menu
- Accounts page with colored AccountCard components grouped into "Mes comptes" / "Comptes partages" sections, including empty state
- Account creation form with all required fields (name, bank, type, currency, initial balance, color picker) using progressive enhancement

## Task Commits

Each task was committed atomically:

1. **Task 1: UI component library and app layout** - `67d030f` (feat)
2. **Task 2: Accounts page and creation form** - `353824a` (feat)

## Files Created/Modified
- `prosperity-web/src/lib/components/ui/Button.svelte` - Reusable button with primary/secondary/ghost/danger variants, loading spinner
- `prosperity-web/src/lib/components/ui/Input.svelte` - Form input with label, error display, required indicator
- `prosperity-web/src/lib/components/ui/Card.svelte` - Container card with optional hover elevation
- `prosperity-web/src/lib/components/ui/Badge.svelte` - Inline badge with default/success/warning/info variants
- `prosperity-web/src/lib/components/ui/Select.svelte` - Native select with custom styling and error display
- `prosperity-web/src/lib/components/ui/ColorPicker.svelte` - 10 preset color circles with checkmark selection
- `prosperity-web/src/lib/components/AccountCard.svelte` - Colored account card with color bar, dual balance, type badge
- `prosperity-web/src/routes/(app)/+layout.svelte` - App layout with responsive sidebar navigation
- `prosperity-web/src/routes/(app)/+layout.server.ts` - Fetch current user from API, redirect if not authenticated
- `prosperity-web/src/routes/(app)/+page.svelte` - Dashboard placeholder with welcome message
- `prosperity-web/src/routes/(app)/accounts/+page.svelte` - Accounts list grouped Personal/Shared
- `prosperity-web/src/routes/(app)/accounts/+page.server.ts` - Load accounts from API
- `prosperity-web/src/routes/(app)/accounts/new/+page.svelte` - Account creation form
- `prosperity-web/src/routes/(app)/accounts/new/+page.server.ts` - Form action POST to API
- `prosperity-web/src/routes/logout/+page.server.ts` - Clear cookies and redirect to /login
- `prosperity-web/messages/fr.json` - Added 20 new i18n keys for dashboard, accounts, forms
- `prosperity-web/messages/en.json` - Added 20 new i18n keys for dashboard, accounts, forms

## Decisions Made
- App layout fetches user from /api/users/me rather than relying solely on JWT claims to ensure fresh data (displayName, role changes)
- Logout implemented as separate /logout route with form action (POST) rather than inline in layout, for clean separation
- AccountCard uses Intl.NumberFormat for locale-aware currency formatting rather than manual string formatting
- ColorPicker provides 10 preset colors (no custom hex input) for simplicity and design consistency

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Created logout route**
- **Found during:** Task 1 (App layout)
- **Issue:** Layout references POST /logout action but no route existed
- **Fix:** Created prosperity-web/src/routes/logout/+page.server.ts with cookie clearing and redirect
- **Files modified:** prosperity-web/src/routes/logout/+page.server.ts
- **Verification:** Build passes, logout form action has valid target
- **Committed in:** 67d030f (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Essential for logout functionality. No scope creep.

## Issues Encountered
- Settings pages from a prior (likely Plan 06) execution already existed as untracked files in the (app) directory. They were included in the first commit since they are part of the (app) route group. No conflicts.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- UI component library ready for reuse across all frontend pages (settings, transactions, budgets)
- Accounts page ready for integration with running API
- Account creation form ready to POST to /api/accounts endpoint
- Dashboard placeholder ready for Phase 5 expansion with charts and summaries
- All text bilingual FR/EN via Paraglide i18n

## Self-Check: PASSED

All 15 key files verified present. Both task commits (67d030f, 353824a) verified in git log.

---
*Phase: 01-foundation*
*Completed: 2026-03-09*
