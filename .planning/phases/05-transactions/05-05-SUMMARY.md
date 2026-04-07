---
phase: 05-transactions
plan: 05
subsystem: frontend
tags: [angular, primeng, transactions, pagination, dialog, p-table, lazy-loading, filters]

# Dependency graph
requires:
  - phase: 05-02
    provides: TransactionController REST endpoints (GET/POST/PUT/DELETE/PATCH)
  - phase: 04-categories
    provides: CategoryService.loadCategories, CategorySelector shared component

provides:
  - TransactionResponse/TransactionFilters/Page TypeScript interfaces aligned with backend DTOs
  - TransactionService with 5 HTTP methods covering all 5 transaction endpoints
  - Transactions list page with lazy p-table, 6 filter fields, empty state, amount coloring, pointed toggle
  - TransactionDialog create/edit dialog with p-inputnumber (EUR), p-datepicker, category selector
  - Route /accounts/:accountId/transactions lazy-loaded
  - Sidebar updated with per-account transaction links

affects: [05-06, future-dashboard-transactions-widget]

# Tech tracking
tech-stack:
  added: [DatePickerModule from primeng/datepicker]
  patterns:
    - "TableLazyLoadEvent rows type is number|null|undefined — method signature must use nullable type to avoid TS2345"
    - "isValid as getter (not computed signal) for plain property reactivity in OnPush components"
    - "httpMock.match() in tests to flush all pending requests matching a predicate (vs expectOne for strict 1:1)"
    - "Transactions component loads categories for filter bar and dialog via CategoryService.loadCategories in constructor"

key-files:
  created:
    - frontend/src/app/transactions/transaction.types.ts
    - frontend/src/app/transactions/transaction.service.ts
    - frontend/src/app/transactions/transactions.ts
    - frontend/src/app/transactions/transaction-dialog.ts
    - frontend/src/app/transactions/transactions.spec.ts
    - frontend/src/app/transactions/transaction-dialog.spec.ts
  modified:
    - frontend/src/app/app.routes.ts
    - frontend/src/app/layout/sidebar.ts
    - frontend/src/app/categories/category-dialog.spec.ts

key-decisions:
  - "CategorySelector not directly reused in filter bar — TreeSelect used inline to avoid needing options as a required input; same TreeNode pattern as CategorySelector"
  - "filterCategoryNode as plain property (not signal) for ngModel two-way binding compatibility (same p-toggleswitch pattern from Phase 3)"
  - "loadAccountName checks existing AccountService.accounts() signal first before issuing HTTP request, reducing unnecessary API calls"
  - "TransactionDialog.isValid as getter instead of computed() because amount/transactionDate are plain properties (not signals), avoiding stale computed reads"
  - "Sidebar loads accounts via loadAccounts() on construction — accounts signal is shared from AccountService so all components reading it stay in sync"

# Metrics
duration: 11min
completed: 2026-04-07
---

# Phase 05 Plan 05: Frontend Transaction UI Summary

**Full transaction frontend: TypeScript interfaces, HTTP service, lazy-paginated list page with 6 filters, create/edit dialog, per-account sidebar navigation, and 9 component tests**

## Performance

- **Duration:** 11 min
- **Started:** 2026-04-07T03:54:32Z
- **Completed:** 2026-04-07T04:06:00Z
- **Tasks:** 2
- **Files modified:** 9 (6 created, 3 modified)

## Accomplishments

- `transaction.types.ts`: 6 TypeScript interfaces (TransactionResponse, TransactionSplitResponse, CreateTransactionRequest, UpdateTransactionRequest, TransactionFilters, Page<T>)
- `transaction.service.ts`: 5 HTTP methods using HttpParams for conditional filter params
- `transactions.ts`: OnPush list page with lazy p-table (server-side pagination), 6-field filter bar (dateFrom, dateTo, amountMin, amountMax, categoryId, search), empty state with copywriting contract, pointed toggle via icon click, MANUAL-only edit/delete, red/green amount coloring with tabular-nums
- `transaction-dialog.ts`: Create/edit dialog with p-inputnumber (currency EUR), p-datepicker, description text input, category tree select, pre-fill in edit mode via effect()
- Route `/accounts/:accountId/transactions` lazy-loaded, sidebar updated with per-account links using `pi pi-list` icon
- 9 component tests: 4 for Transactions (create, heading, lazy load, empty state) and 5 for TransactionDialog (create, headings, pre-fill, disabled button, save emit)

## Task Commits

1. **Task 1: Types + Service + Route + Sidebar** — `70d23d6`
2. **Task 2: Transaction list page + dialog + tests** — `4ab4fcd`

## Files Created/Modified

- `frontend/src/app/transactions/transaction.types.ts` — TypeScript interfaces for all transaction DTOs
- `frontend/src/app/transactions/transaction.service.ts` — HTTP service with 5 endpoints and HttpParams
- `frontend/src/app/transactions/transactions.ts` — Transaction list page (lazy table, filters, dialog wiring)
- `frontend/src/app/transactions/transaction-dialog.ts` — Create/edit dialog
- `frontend/src/app/transactions/transactions.spec.ts` — 4 component tests
- `frontend/src/app/transactions/transaction-dialog.spec.ts` — 5 component tests
- `frontend/src/app/app.routes.ts` — Added accounts/:accountId/transactions lazy route
- `frontend/src/app/layout/sidebar.ts` — Per-account transaction links using AccountService.accounts signal
- `frontend/src/app/categories/category-dialog.spec.ts` — Fixed pre-existing jasmine.createSpy incompatibility

## Decisions Made

- `CategorySelector` not reused directly in filter bar since it requires `options` as a required input — used inline `p-treeselect` with same TreeNode structure
- `filterCategoryNode` as plain property for ngModel compatibility (consistent with p-toggleswitch in Phase 3)
- `loadAccountName` checks cached `accounts()` signal first before issuing HTTP
- `isValid` as property getter not computed signal — plain properties (`amount`, `transactionDate`) don't trigger computed() updates
- Sidebar loads accounts in constructor — all consumers of the `AccountService.accounts` signal stay synchronized

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed jasmine.createSpy incompatibility in category-dialog.spec.ts**
- **Found during:** Task 2 test run
- **Issue:** Pre-existing `category-dialog.spec.ts` used `jasmine.createSpy()` which is not available in Vitest environment, causing build failure and blocking all tests
- **Fix:** Replaced `jasmine.createSpy('saved')` and `jasmine.createSpy('visibleChange')` with direct subscription pattern using local boolean/value variables
- **Files modified:** `frontend/src/app/categories/category-dialog.spec.ts`
- **Commit:** `4ab4fcd`

**2. [Rule 1 - Bug] Fixed TableLazyLoadEvent type mismatch**
- **Found during:** Task 2 build verification
- **Issue:** PrimeNG 21 `TableLazyLoadEvent.rows` is typed `number | null | undefined`, not `number | undefined` — method signature caused TS2345
- **Fix:** Changed `loadTransactions(event: { first?: number; rows?: number })` to use nullable types
- **Files modified:** `frontend/src/app/transactions/transactions.ts`
- **Commit:** `4ab4fcd`

**3. [Rule 2 - Missing functionality] isValid as getter not computed signal**
- **Found during:** Task 2 test writing
- **Issue:** `isValid = computed()` based on plain properties doesn't update reactively when amount/transactionDate change — `save()` would always see initial value
- **Fix:** Changed to `get isValid(): boolean` property getter for correct evaluation at call time
- **Files modified:** `frontend/src/app/transactions/transaction-dialog.ts`
- **Commit:** `4ab4fcd`

---

**Total deviations:** 3 auto-fixed (2 bugs, 1 missing correctness)

## Known Stubs

None — all data is wired to real HTTP endpoints via TransactionService.

## Self-Check: PASSED
