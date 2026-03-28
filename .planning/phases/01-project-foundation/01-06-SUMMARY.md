---
phase: 01-project-foundation
plan: 06
subsystem: infra
tags: [angular, primeng, tailwind, eslint, prettier, frontend]

# Dependency graph
requires: []
provides:
  - Angular 21 SPA shell with build tooling
  - PrimeNG 21.x component library configured
  - Tailwind CSS v4 with PrimeNG integration
  - ESLint flat config for Angular
  - Prettier formatting pipeline
affects: [02-auth, ui-phases]

# Tech tracking
tech-stack:
  added: [angular-21.2, primeng-21.1.4, tailwindcss-4.2.2, tailwindcss-primeui-0.6.1, eslint, prettier, vitest-4]
  patterns: [standalone-components, css-imports-for-tailwind-v4, flat-eslint-config]

key-files:
  created:
    - frontend/package.json
    - frontend/angular.json
    - frontend/eslint.config.js
    - frontend/.prettierrc
    - frontend/.prettierignore
    - frontend/src/app/app.ts
    - frontend/src/app/app.config.ts
    - frontend/src/app/app.spec.ts
    - frontend/src/styles.css
  modified: []

key-decisions:
  - "PrimeNG 21 requires no providePrimeNG -- purely CSS-based theming via tailwindcss-primeui"
  - "Angular 21 uses simplified file naming (app.ts not app.component.ts) and Vitest instead of Karma"

patterns-established:
  - "Tailwind v4 CSS import: @import 'tailwindcss' then @import 'tailwindcss-primeui' (no JS plugin)"
  - "ESLint flat config with angular-eslint processInlineTemplates"
  - "Prettier with singleQuote, trailingComma all, printWidth 100"

requirements-completed: [INFR-04, INFR-05]

# Metrics
duration: 3min
completed: 2026-03-28
---

# Phase 01 Plan 06: Frontend Scaffolding Summary

**Angular 21 SPA with PrimeNG 21.1, Tailwind CSS v4, ESLint flat config, and Prettier -- builds, lints, and formats cleanly**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-28T20:46:14Z
- **Completed:** 2026-03-28T20:49:57Z
- **Tasks:** 1
- **Files modified:** 24

## Accomplishments
- Angular 21.2 project scaffolded with standalone components and Vitest test runner
- PrimeNG 21.1.4 installed with Tailwind CSS v4 integration via tailwindcss-primeui
- ESLint flat config via @angular-eslint/schematics with Angular-specific rules
- Prettier configured with format:check and format:fix scripts
- Production build creates dist/ at 222 kB (57 kB transfer)

## Task Commits

Each task was committed atomically:

1. **Task 1: Scaffold Angular 21 project with PrimeNG, Tailwind CSS v4, ESLint, and Prettier** - `a436b0c` (feat)

**Plan metadata:** [pending final commit] (docs: complete plan)

## Files Created/Modified
- `frontend/package.json` - Angular project with PrimeNG, Tailwind, ESLint, Prettier deps and scripts
- `frontend/angular.json` - Angular CLI config with ESLint lint target
- `frontend/eslint.config.js` - Flat ESLint config with angular-eslint rules
- `frontend/.prettierrc` - Prettier config: singleQuote, trailingComma, printWidth 100
- `frontend/.prettierignore` - Ignores dist/, node_modules/, coverage/, .angular/
- `frontend/src/app/app.ts` - Minimal component rendering "Prosperity"
- `frontend/src/app/app.config.ts` - App config with router and global error listeners
- `frontend/src/app/app.spec.ts` - Tests for app creation and title rendering
- `frontend/src/styles.css` - Tailwind v4 + tailwindcss-primeui CSS imports
- `frontend/src/index.html` - HTML entry point
- `frontend/src/main.ts` - Bootstrap entry point
- `frontend/tsconfig.json` - TypeScript 5.9 config
- `frontend/pnpm-lock.yaml` - Locked dependencies

## Decisions Made
- PrimeNG 21 does not export `providePrimeNG` -- theming is purely CSS-based via tailwindcss-primeui import, no provider configuration needed
- Angular 21 CLI generates `app.ts` (not `app.component.ts`), uses Vitest instead of Karma, and includes Prettier out of the box
- Kept Angular router configuration from scaffold (app.routes.ts) but no routes defined per D-15

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Tailwind CSS v4 not bundled with Angular CLI**
- **Found during:** Task 1 (Step 2)
- **Issue:** Angular CLI 21 does not auto-install tailwindcss as a dependency; only the build tooling supports it
- **Fix:** Installed tailwindcss and @tailwindcss/postcss as dev dependencies
- **Files modified:** frontend/package.json, frontend/pnpm-lock.yaml
- **Verification:** pnpm build succeeds with Tailwind styles processed
- **Committed in:** a436b0c (Task 1 commit)

**2. [Rule 1 - Bug] Angular 21 file naming conventions differ from plan**
- **Found during:** Task 1 (Step 5)
- **Issue:** Plan references `app.component.ts` but Angular 21 generates `app.ts` with class name `App` (not `AppComponent`)
- **Fix:** Adapted to Angular 21 conventions -- edited `app.ts` and `app.spec.ts` with correct class names
- **Files modified:** frontend/src/app/app.ts, frontend/src/app/app.spec.ts
- **Verification:** pnpm test passes (2/2 tests), pnpm lint passes
- **Committed in:** a436b0c (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both auto-fixes necessary for correctness. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviations above.

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - no stubs or placeholder data in the frontend shell.

## Next Phase Readiness
- Frontend SPA shell ready for auth UI (Phase 2)
- PrimeNG components available for use in any future frontend work
- ESLint and Prettier enforce code quality from first line of Angular code

---
*Phase: 01-project-foundation*
*Completed: 2026-03-28*
