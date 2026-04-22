---
phase: 06-envelope-budgets
plan: 07
subsystem: ui
tags: [angular, typescript, primeng, treeselect, httpclient, signals, routing, lazy-loading]

requires:
  - phase: 06-envelope-budgets
    provides: DTO records + HTTP routes (Plan 02 DTOs + Plan 05 controllers — 12 REST routes, EnvelopeStatus/EnvelopeScope/RolloverPolicy enums)
  - phase: 04-categories
    provides: CategorySelector shared component (p-treeselect single mode) — extended here to dual-mode
  - phase: 03-accounts-access
    provides: AccountService signal pattern (HttpClient + signal cache) — mirrored in EnvelopeService
provides:
  - envelope.types.ts (9 TS types/interfaces mirroring backend DTOs verbatim)
  - EnvelopeService (Angular @Injectable, 11 methods covering all 11 backend routes, signal-based in-memory cache)
  - CategorySelector selectionMode='checkbox' extension (display="chip", selectedIds pre-fill, string[] emission)
  - Sidebar "Enveloppes" navigation entry (pi-wallet icon, routerLinkActive)
  - Lazy routes /envelopes and /envelopes/:id in authenticated layout
  - EnvelopesPage and EnvelopeDetailsPage stubs (filled in Plan 08)
affects: [06-08-frontend-pages]

tech-stack:
  added: []
  patterns:
    - "Frontend DTO interfaces mirror backend records verbatim (BigDecimal -> number, Instant -> string, YearMonth -> yyyy-MM string, enums -> uppercase string unions)"
    - "Angular shared component dual-mode via selectionMode input — single (legacy) + checkbox (new) branches in template, preserves backward-compatible API with additive new output"
    - "Stub component exports (@Component with placeholder template) unblock lazy routes between atomic plans — avoids broken type-check during phase iteration"
    - "EnvelopeListFilters helper type (accountId?/includeArchived?) to keep HttpParams conditional logic readable"

key-files:
  created:
    - frontend/src/app/envelopes/envelope.types.ts
    - frontend/src/app/envelopes/envelope.service.ts
    - frontend/src/app/envelopes/envelopes.ts (stub — Plan 08 fills)
    - frontend/src/app/envelopes/envelope-details.ts (stub — Plan 08 fills)
    - .planning/phases/06-envelope-budgets/deferred-items.md
  modified:
    - frontend/src/app/shared/category-selector.ts (single-mode preserved, checkbox mode added)
    - frontend/src/app/shared/category-selector.spec.ts (3 existing tests updated to new method names, 3 new checkbox tests)
    - frontend/src/app/layout/sidebar.ts (Enveloppes entry)
    - frontend/src/app/layout/sidebar.spec.ts (new test asserting Enveloppes link)
    - frontend/src/app/app.routes.ts (2 lazy children)

key-decisions:
  - "CategorySelector renamed onSelect/onClear to onSingleSelect/onSingleClear: plan template uses explicit single-mode prefix to pair with onCheckboxChange/onCheckboxClear; existing tests updated (no external callers depended on the old names — verified via grep across frontend/)"
  - "Stub components EnvelopesPage + EnvelopeDetailsPage created in Plan 07 (not deferred to Plan 08): lazy loadComponent imports must resolve at type-check time; stubs keep the phase branch green between plans rather than coupling Plan 07 acceptance to Plan 08 delivery"
  - "Monetary fields typed as TypeScript number (matches Phase 5 transaction.types.ts), not string: Jackson default BigDecimal serialisation is JSON number and the frontend formats via Intl.NumberFormat — no string arithmetic precision concern for EUR at household scale"
  - "pi-wallet icon reused (not pi-chart-pie): UI-SPEC accepts both; pi-wallet aligns with the Comptes link and keeps the sidebar's financial semantics consistent (planner's exact call deferred to executor per UI-SPEC line 140)"
  - "EnvelopeService cache signal set by BOTH loadEnvelopes AND loadEnvelopesForAccount: single readonly cache simplifies list-page consumption; the distinction is at load time (which endpoint), not at storage"

patterns-established:
  - "Dual-mode shared component pattern: @if selectionMode() branches template, separate output per mode (categorySelected vs categoriesSelected), both outputs declared so TypeScript consumers can bind either — future shared components can mix modes without duplicating components"
  - "Stub component bridge pattern for parallel-wave plans: when Plan N wires lazy routes consumed by Plan N+1, Plan N creates @Component class stubs with placeholder templates; Plan N+1 overwrites them with full implementation"
  - "Deferred-items.md at phase level: pre-existing lint/build warnings discovered during plan execution but out of scope are logged to .planning/phases/XX-name/deferred-items.md — preserves visibility without polluting plan scope"

requirements-completed:
  - ENVL-01
  - ENVL-02
  - ENVL-03
  - ENVL-06
  - ENVL-07

duration: 5min
completed: 2026-04-22
---

# Phase 06 Plan 07: Frontend Infrastructure Summary

**Envelope frontend scaffolding ready for Plan 08: 9 TypeScript DTO interfaces, 11-method HttpClient-based EnvelopeService with signal cache, dual-mode CategorySelector (single + checkbox), sidebar Enveloppes entry, and two lazy routes with stub components.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-22T11:52:09Z
- **Completed:** 2026-04-22T11:57:01Z
- **Tasks:** 4
- **Files created:** 5 (2 production + 2 stubs + 1 deferred-items log)
- **Files modified:** 5

## Accomplishments

- **TypeScript DTO mirror**: `envelope.types.ts` exposes the exact 9 types/interfaces the rest of the frontend needs — `EnvelopeStatus`, `EnvelopeScope`, `RolloverPolicy`, `EnvelopeCategoryRef`, `EnvelopeResponse`, `EnvelopeAllocationResponse`, `EnvelopeHistoryEntry`, plus three request records (`CreateEnvelopeRequest`, `UpdateEnvelopeRequest`, `EnvelopeAllocationRequest`) and an `EnvelopeListFilters` helper. All shapes verbatim to Plan 02 backend records with the conventional JSON wire mappings (BigDecimal→number, Instant→string, YearMonth→"yyyy-MM", enums→uppercase union).
- **EnvelopeService**: 11 public methods (`loadEnvelopes`, `loadEnvelopesForAccount`, `getEnvelope`, `createEnvelope`, `updateEnvelope`, `deleteEnvelope`, `getHistory`, `listAllocations`, `createAllocation`, `updateAllocation`, `deleteAllocation`) covering Plan 05's 11 REST routes. Signal-based `envelopes` cache (readonly to consumers) populated by both list-loading methods. HttpParams used for conditional query params (accountId, includeArchived, month).
- **CategorySelector dual-mode**: Single mode preserved byte-for-byte in observable behaviour; new `selectionMode='checkbox'` branch uses `p-treeselect selectionMode="checkbox" display="chip" [showClear]="true"` with checkbox propagation (parent tick ticks children — D-02 alignment). New `selectedIds` input pre-fills via a reactive effect that flattens the tree. New `categoriesSelected` output emits `string[]`. 6 tests pass (3 existing single-mode + 3 new checkbox-mode).
- **Navigation**: Sidebar gains an "Enveloppes" entry after Categories (pi-wallet icon, matching `routerLinkActive` styling); sidebar spec asserts its presence. `app.routes.ts` registers `/envelopes` and `/envelopes/:id` as lazy children inside the authenticated layout. Stub `EnvelopesPage` and `EnvelopeDetailsPage` exports keep the TypeScript build green until Plan 08 delivers the real components.

## Task Commits

Each task was committed atomically:

1. **Task 1: envelope.types.ts** — `5f9c43b` (feat)
2. **Task 2: envelope.service.ts** — `a44080e` (feat)
3. **Task 3: CategorySelector checkbox mode** — `dcca3e5` (feat)
4. **Task 4: Sidebar Enveloppes + lazy routes + stubs** — `cd922dd` (feat)

## Files Created/Modified

- `frontend/src/app/envelopes/envelope.types.ts` — 9 types/interfaces (69 lines)
- `frontend/src/app/envelopes/envelope.service.ts` — @Injectable({providedIn:'root'}), 11 HttpClient methods, `envelopes` readonly signal cache (109 lines)
- `frontend/src/app/envelopes/envelopes.ts` — EnvelopesPage stub for Plan 08 (13 lines, placeholder template)
- `frontend/src/app/envelopes/envelope-details.ts` — EnvelopeDetailsPage stub for Plan 08 (13 lines, placeholder template)
- `frontend/src/app/shared/category-selector.ts` — Dual-mode rewrite: `selectionMode: 'single' | 'checkbox'`, `selectedIds: string[]`, `categoriesSelected: string[]`, `categorySelected: string | null`, flatten helper, effect-based pre-fill. Template branches via `@if`.
- `frontend/src/app/shared/category-selector.spec.ts` — Renamed existing tests' method calls (`onSelect` → `onSingleSelect`, `onClear` → `onSingleClear`); appended 3 new tests: `emits_empty_array_on_checkbox_clear`, `emits_selected_ids_array_on_checkbox_change`, `preserves_single_mode_when_selection_mode_omitted`.
- `frontend/src/app/layout/sidebar.ts` — Enveloppes link after Categories (pi-wallet icon, same classes as existing links).
- `frontend/src/app/layout/sidebar.spec.ts` — `renders_navigation_link_to_envelopes` test.
- `frontend/src/app/app.routes.ts` — 2 new lazy children under the authenticated layout.
- `.planning/phases/06-envelope-budgets/deferred-items.md` — 3 pre-existing Phase 5 lint errors logged (out of scope).

## Decisions Made

- **CategorySelector method rename (`onSelect/onClear` → `onSingleSelect/onSingleClear`)**: The plan's new component template uses mode-prefixed method names to pair cleanly with `onCheckboxChange/onCheckboxClear`. No external callers depended on the old names (verified via `grep -rn "onSelect\|onClear" src/app --include="*.ts" | grep -v "category-selector"` — only matches were PrimeNG `(onClear)` event bindings on `<p-treeselect>`, which are independent). Existing tests were updated to use the new method names while preserving their assertions. Verdict: internal refactor, no public API breakage.
- **Stub components created in Plan 07, not deferred to Plan 08**: Angular's `loadComponent: () => import('./envelopes/envelopes').then((m) => m.EnvelopesPage)` fails type-check if the target module or export doesn't exist. Creating 13-line stub classes keeps `pnpm exec tsc --noEmit` exit 0 and satisfies Task 4's acceptance criterion. Plan 08 will overwrite these stubs with the real pages.
- **Single cache signal for both list methods**: `loadEnvelopes({accountId})` and `loadEnvelopesForAccount(accountId)` both write to `_envelopes`. The list page displays "envelopes for X" semantics regardless of which endpoint filtered them — one cache keeps the surface consistent.
- **pi-wallet icon (vs pi-chart-pie)**: UI-SPEC allows either. pi-wallet preserves the "financial surface" iconography (Comptes already uses it) and the differentiation is carried by the label "Enveloppes" + the URL.
- **Monetary fields as TypeScript `number`**: Consistent with Phase 5's `transaction.types.ts` convention; `Intl.NumberFormat('fr-FR', { style: 'currency' })` handles EUR display in the pages. The max envelope budget at household scale is well within IEEE-754 exact range.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Existing CategorySelector tests called removed methods `onSelect`/`onClear`**
- **Found during:** Task 3 (CategorySelector dual-mode implementation)
- **Issue:** The plan's component template renamed the single-mode event handlers from `onSelect`/`onClear` to `onSingleSelect`/`onSingleClear` (to pair with new `onCheckboxChange`/`onCheckboxClear`). The existing `category-selector.spec.ts` tests called the old method names directly on the component instance, breaking them with "Property 'onSelect' does not exist on type 'CategorySelector'" compilation errors.
- **Fix:** Updated the 2 affected existing tests to call `onSingleSelect(...)` and `onSingleClear()`. Preserved test names, AAA structure, and assertions. All 6 tests (3 existing + 3 new) pass.
- **Files modified:** `frontend/src/app/shared/category-selector.spec.ts`
- **Verification:** `pnpm exec ng test --include=src/app/shared/category-selector.spec.ts --no-watch` reports `Test Files 1 passed (1) / Tests 6 passed (6)`.
- **Committed in:** `dcca3e5` (Task 3 commit).

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug/test-breakage from planned rename).
**Impact on plan:** Trivial — the plan's template dictated the new method names, but its spec-file section didn't include the method-name updates for existing tests. No scope creep, no behavioural change.

## Issues Encountered

- **Scope boundary: pre-existing Phase 5 lint errors** — `pnpm lint` reports 3 errors in `frontend/src/app/transactions/` (2× `@typescript-eslint/no-inferrable-types`, 1× `@typescript-eslint/no-unused-vars`). Confirmed present before Plan 07 (verified via `git stash` + `pnpm lint` re-run). Per scope-boundary rule (only auto-fix issues directly caused by the current task), these are NOT fixed in this plan. Logged to `.planning/phases/06-envelope-budgets/deferred-items.md` for a future Phase 5 follow-up or broader lint-hygiene sweep.
- **Parallel wave: `EnvelopeServiceTest.java` modified in working tree but not committed by this plan** — backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java appeared as modified in `git status`. This file belongs to Plan 06 (backend-tests), executing in parallel. Plan 07 did NOT stage or commit it; all Plan 07 commits contain only `frontend/src/app/envelopes/*` and `frontend/src/app/layout/*` and `frontend/src/app/shared/*` paths.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **Plan 08 (frontend-pages)**: All scaffolding Plan 08 consumes is in place. It can now:
  - Import `EnvelopeResponse`/`EnvelopeAllocationResponse`/`EnvelopeHistoryEntry` and the request types from `envelope.types.ts`.
  - Inject `EnvelopeService` and call any of its 11 methods; read the `envelopes` signal on the list page.
  - Import `CategorySelector` with `[selectionMode]="'checkbox'"` + `[selectedIds]="..."` + `(categoriesSelected)="..."` for the envelope create/edit dialog (D-21, UI-SPEC §Extended CategorySelector Contract).
  - Overwrite `envelopes/envelopes.ts` and `envelopes/envelope-details.ts` with the real list page + details page components (class names `EnvelopesPage` / `EnvelopeDetailsPage` are locked in `app.routes.ts`).
- **No blockers** for Plan 08.
- **Phase-level lint follow-up**: address the 3 pre-existing Phase 5 lint errors in a standalone quick task after Phase 6 ships.

---
*Phase: 06-envelope-budgets*
*Completed: 2026-04-22*

## Self-Check: PASSED

Verified files exist on disk:
- FOUND: frontend/src/app/envelopes/envelope.types.ts
- FOUND: frontend/src/app/envelopes/envelope.service.ts
- FOUND: frontend/src/app/envelopes/envelopes.ts
- FOUND: frontend/src/app/envelopes/envelope-details.ts
- FOUND: frontend/src/app/shared/category-selector.ts (modified)
- FOUND: frontend/src/app/shared/category-selector.spec.ts (modified)
- FOUND: frontend/src/app/layout/sidebar.ts (modified)
- FOUND: frontend/src/app/layout/sidebar.spec.ts (modified)
- FOUND: frontend/src/app/app.routes.ts (modified)
- FOUND: .planning/phases/06-envelope-budgets/06-07-frontend-infrastructure-SUMMARY.md
- FOUND: .planning/phases/06-envelope-budgets/deferred-items.md

Verified commits exist:
- FOUND: 5f9c43b (Task 1 — envelope.types.ts)
- FOUND: a44080e (Task 2 — envelope.service.ts)
- FOUND: dcca3e5 (Task 3 — CategorySelector checkbox mode)
- FOUND: cd922dd (Task 4 — Sidebar Enveloppes + lazy routes + stubs)

Verification commands:
- `pnpm exec tsc --noEmit -p tsconfig.app.json` → exit 0 (no output)
- `pnpm exec ng test --include=src/app/shared/category-selector.spec.ts --no-watch` → Tests 6 passed (6)
- `pnpm exec ng test --include=src/app/layout/sidebar.spec.ts --no-watch` → Tests 2 passed (2)
