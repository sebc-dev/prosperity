---
phase: 03-accounts-access-control
plan: 08
subsystem: ui
tags: [angular, primeng, p-table, p-dialog, signals, reactive-forms, accounts]

# Dependency graph
requires:
  - phase: 03-07
    provides: AccountService with loadAccounts/createAccount/updateAccount, account.types.ts

provides:
  - Accounts list page (accounts.ts) with p-table, archive toggle, confirm dialog
  - AccountDialog component (account-dialog.ts) for create/edit with reactive forms
  - accounts.spec.ts: 3 tests verifying component creation, heading, loadAccounts call
  - account-dialog.spec.ts: 4 tests verifying creation, null account, form validity, pre-fill

affects: [03-09-account-access-dialog, routing, layout-sidebar]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "p-toggleswitch with plain boolean field (not signal) for ngModel two-way binding compatibility"
    - "ConfirmationService provided at component level in providers array (not root)"
    - "Signal inputs input()/output() API for dialog visibility and account binding"
    - "effect() to sync reactive form values when signal input changes"
    - "computed() for dialogHeader switching between create/edit mode"

key-files:
  created:
    - frontend/src/app/accounts/account-dialog.ts
    - frontend/src/app/accounts/accounts.spec.ts
    - frontend/src/app/accounts/account-dialog.spec.ts
  modified:
    - frontend/src/app/accounts/accounts.ts

key-decisions:
  - "p-toggleswitch requires plain boolean (not signal) for ngModel two-way binding — documented in plan task notes"
  - "account-dialog.ts created in Task 1 as a prerequisite for accounts.ts import, then spec added in Task 2"
  - "protected visibility on dialogHeader/isEdit computed signals tested indirectly via public account() input and form state"

patterns-established:
  - "Dialog components use input()/output() signal APIs with effect() for form population"
  - "ConfirmationService provided at component level (providers array) not root, to scope confirm dialogs"
  - "Archive/unarchive actions: confirmArchive uses ConfirmationService, unarchive is direct call"

requirements-completed: [ACCT-01, ACCT-02, ACCT-03, ACCT-04, ACCT-05]

# Metrics
duration: 4min
completed: 2026-04-05
---

# Phase 03 Plan 08: Accounts UI Components Summary

**Angular OnPush accounts list page with p-table, archive toggle, and ConfirmationService, plus reactive-form create/edit dialog using signal inputs/outputs**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-05T13:30:34Z
- **Completed:** 2026-04-05T13:34:29Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Accounts list page with p-table (Nom/Type/Solde/Statut/Actions columns), striped rows, sortable Nom and Solde
- Archive toggle using p-toggleswitch with plain boolean field for ngModel compatibility
- Archive confirmation flow via ConfirmationService with UI-SPEC copy
- Action buttons: pi-pencil (edit), pi-users (manage access placeholder), pi-inbox (archive), pi-replay (unarchive) with aria-labels and tooltips
- AccountDialog with reactive form, computed dialogHeader, effect()-based form population from account input
- Empty state with "Aucun compte" heading per UI-SPEC
- 7 total tests across 2 spec files, all 55 frontend tests passing

## Task Commits

1. **Task 1: Accounts list page component** - `b1886ff` (feat)
2. **Task 2: Create/Edit account dialog component** - `9399f24` (feat)

**Plan metadata:** pending (docs commit after SUMMARY)

## Files Created/Modified

- `frontend/src/app/accounts/accounts.ts` - Full Accounts list page replacing placeholder
- `frontend/src/app/accounts/account-dialog.ts` - Create/edit dialog with p-dialog and reactive form
- `frontend/src/app/accounts/accounts.spec.ts` - 3 tests: component creation, heading, loadAccounts call
- `frontend/src/app/accounts/account-dialog.spec.ts` - 4 tests: creation, null account, form validity, pre-fill

## Decisions Made

- `p-toggleswitch` uses `[(ngModel)]` which requires a plain boolean property, not an Angular signal. Used `protected includeArchived = false` as the plan's task note specified.
- `account-dialog.ts` created during Task 1 (needed for the import in `accounts.ts`); its spec was added in Task 2.
- `dialogHeader` and `isEdit` kept `protected` per Angular convention; tests access behavior through the public `account()` input and the form's `controls` state.
- `openAccessDialog()` stubbed with a TODO comment per plan note — to be implemented in Plan 09.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Initial `account-dialog.spec.ts` tried to access `protected dialogHeader()` — fixed by testing the observable behavior through `account()` input and form state instead.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 08 complete: accounts list page and create/edit dialog wired to AccountService
- Ready for Plan 09: access management dialog (`openAccessDialog` stub already present in accounts.ts)
- All 55 frontend tests passing, build clean

---
*Phase: 03-accounts-access-control*
*Completed: 2026-04-05*
