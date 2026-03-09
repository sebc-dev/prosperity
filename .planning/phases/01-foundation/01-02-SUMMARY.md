---
phase: 01-foundation
plan: 02
subsystem: infra
tags: [sveltekit, tailwind-css-4, paraglide, docker-compose, caddy, github-actions, vitest, svelte-5]

# Dependency graph
requires:
  - phase: none
    provides: greenfield project
provides:
  - SvelteKit 2 project with Svelte 5, Tailwind CSS 4, Paraglide i18n (FR/EN)
  - BFF auth hooks skeleton (token refresh + auth guard)
  - API client factory for server-side fetch with Bearer forwarding
  - Preferences store using Svelte 5 runes
  - Docker Compose config (PostgreSQL 16 + Spring Boot API + SvelteKit web)
  - Caddy reverse proxy with security headers
  - GitHub Actions CI pipeline (backend + frontend in parallel)
  - Vitest config with jsdom for frontend testing
affects: [01-03, 01-05, 01-06, all-frontend-plans]

# Tech tracking
tech-stack:
  added: [sveltekit-2, svelte-5, tailwindcss-4, paraglide-js-2, adapter-node, vitest, jsdom, eslint-9, prettier]
  patterns: [bff-auth-hooks, svelte-5-runes-store, fouc-prevention, multi-stage-dockerfile]

key-files:
  created:
    - prosperity-web/package.json
    - prosperity-web/vite.config.ts
    - prosperity-web/vitest.config.ts
    - prosperity-web/svelte.config.js
    - prosperity-web/src/hooks.server.ts
    - prosperity-web/src/lib/api/client.ts
    - prosperity-web/src/lib/stores/preferences.svelte.ts
    - prosperity-web/src/app.html
    - prosperity-web/src/app.css
    - prosperity-web/src/app.d.ts
    - prosperity-web/messages/fr.json
    - prosperity-web/messages/en.json
    - prosperity-web/Dockerfile
    - docker-compose.yml
    - docker-compose.dev.yml
    - Caddyfile
    - .env.example
    - .github/workflows/ci.yml
    - .gitignore
  modified: []

key-decisions:
  - "Used @sveltejs/vite-plugin-svelte v5 for vite 6 compatibility (v4 requires vite 5, v6+ requires vite 6.3+)"
  - "Used paraglideVitePlugin export from @inlang/paraglide-js (v2 API changed from named 'paraglide' export)"
  - "Cookie-based theme persistence with FOUC prevention inline script in app.html"
  - "Production docker-compose.yml has no exposed ports (Caddy handles routing); dev overlay exposes all"

patterns-established:
  - "BFF auth: tokenRefresh + authGuard handles in sequence, JWT decoded client-side (no verification -- API's job)"
  - "API client factory: server-side only, forwards Bearer token from event.locals"
  - "Preferences store: Svelte 5 class with $state/$derived runes, exported singleton"
  - "Tailwind CSS 4: @import 'tailwindcss' + @theme block for custom colors + @variant for dark mode"
  - "i18n: Paraglide Vite plugin generates typed message functions in src/lib/i18n/"

requirements-completed: [INFR-01, INFR-02]

# Metrics
duration: 5min
completed: 2026-03-09
---

# Phase 1 Plan 2: Frontend & Infrastructure Summary

**SvelteKit 2 scaffold with Tailwind CSS 4, Paraglide i18n, BFF auth hooks, Docker Compose (3 services), Caddy reverse proxy, and GitHub Actions CI**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-09T06:24:05Z
- **Completed:** 2026-03-09T06:29:10Z
- **Tasks:** 2
- **Files modified:** 25

## Accomplishments
- SvelteKit project builds cleanly with 0 errors (svelte-check passes)
- BFF auth skeleton with token refresh and auth guard ready for API integration
- Docker Compose defines complete 3-service stack (db, api, web) with health checks
- CI pipeline with parallel backend (Java 21 + Maven + PostgreSQL) and frontend (Node 22) jobs

## Task Commits

Each task was committed atomically:

1. **Task 1: Scaffold SvelteKit project with Tailwind, Paraglide, BFF skeleton, and Vitest** - `6d0acc9` (feat)
2. **Task 2: Create Docker Compose, Caddy config, CI workflow, and .env setup** - `69fdce4` (feat)

## Files Created/Modified
- `prosperity-web/package.json` - SvelteKit project with all dependencies
- `prosperity-web/vite.config.ts` - Tailwind + Paraglide + SvelteKit Vite plugins
- `prosperity-web/vitest.config.ts` - Vitest with jsdom environment
- `prosperity-web/svelte.config.js` - SvelteKit with adapter-node
- `prosperity-web/src/hooks.server.ts` - BFF auth hooks (tokenRefresh + authGuard)
- `prosperity-web/src/lib/api/client.ts` - API client factory with Bearer forwarding
- `prosperity-web/src/lib/stores/preferences.svelte.ts` - Theme/locale/currency store with Svelte 5 runes
- `prosperity-web/src/app.html` - HTML template with FOUC prevention script
- `prosperity-web/src/app.css` - Tailwind CSS 4 with custom theme colors
- `prosperity-web/src/app.d.ts` - App.Locals type with accessToken and user
- `prosperity-web/src/routes/+layout.svelte` - Root layout with app.css import
- `prosperity-web/messages/fr.json` - French UI strings (34 keys)
- `prosperity-web/messages/en.json` - English UI strings (34 keys)
- `prosperity-web/project.inlang/settings.json` - Paraglide i18n config (FR source, EN target)
- `prosperity-web/Dockerfile` - Multi-stage Node 22 alpine build
- `prosperity-web/eslint.config.js` - ESLint 9 flat config with Svelte + TS + Prettier
- `prosperity-web/.prettierrc` - Prettier config with Svelte plugin
- `docker-compose.yml` - Production config: db + api + web, no exposed ports
- `docker-compose.dev.yml` - Development overlay exposing ports 5432, 8080, 3000
- `Caddyfile` - Reverse proxy with HSTS, X-Frame-Options, CSP headers
- `.env.example` - Template for DB_PASSWORD, JWT_SECRET, APP_ORIGIN, APP_DOMAIN
- `.github/workflows/ci.yml` - CI with parallel backend and frontend jobs
- `.gitignore` - Java, Node, IDE, Docker, env exclusions

## Decisions Made
- Used @sveltejs/vite-plugin-svelte v5 (not v4 or v6/v7) for compatibility with vite 6.x
- Used `paraglideVitePlugin` export name (Paraglide JS 2.x changed API from earlier versions)
- Production docker-compose has no exposed ports -- Caddy handles all routing
- Added cookie persistence for theme preference to complement the FOUC prevention script

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed Paraglide import name**
- **Found during:** Task 1 (svelte-check verification)
- **Issue:** Plan referenced `paraglide` named export, but Paraglide JS 2.x exports `paraglideVitePlugin`
- **Fix:** Changed import to `paraglideVitePlugin` from `@inlang/paraglide-js`
- **Files modified:** `prosperity-web/vite.config.ts`
- **Verification:** svelte-check passes with 0 errors
- **Committed in:** 6d0acc9 (Task 1 commit)

**2. [Rule 3 - Blocking] Fixed vite-plugin-svelte version compatibility**
- **Found during:** Task 1 (npm install)
- **Issue:** @sveltejs/vite-plugin-svelte v4 requires vite ^5.0.0, but project uses vite ^6.0.0
- **Fix:** Updated to @sveltejs/vite-plugin-svelte v5 which supports vite ^6.0.0
- **Files modified:** `prosperity-web/package.json`
- **Verification:** npm install succeeds, no peer dependency conflicts
- **Committed in:** 6d0acc9 (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 blocking)
**Impact on plan:** Both auto-fixes necessary to resolve dependency and API compatibility. No scope creep.

## Issues Encountered
- Docker CLI not available in WSL environment, so `docker compose config -q` validation could not run. Docker Compose YAML structure was verified via Node.js parsing instead.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Frontend scaffold complete, ready for auth UI (Plan 01-03) and component library (Plan 01-05)
- Docker Compose config ready but requires prosperity-api to be scaffolded (Plan 01-01) before containers can build
- CI workflow ready but backend job will fail until Maven project exists

## Self-Check: PASSED

All 19 created files verified present. Both task commits (6d0acc9, 69fdce4) verified in git log.

---
*Phase: 01-foundation*
*Completed: 2026-03-09*
