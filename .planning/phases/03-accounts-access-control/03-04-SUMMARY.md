---
phase: 03-accounts-access-control
plan: 04
subsystem: api
tags: [java, spring, jpa, accounts, access-control, authorization]

# Dependency graph
requires:
  - phase: 03-accounts-access-control
    provides: "Plan 03-01 through 03-03: Account/AccountAccess entities, repositories, DTOs, exceptions"
provides:
  - "AccountService with 7 business methods: createAccount, getAccounts, getAccount, updateAccount, getAccessEntries, setAccess, removeAccess"
  - "Access enforcement: READ for list/get (implicit via repo query), WRITE for update, ADMIN for access management"
  - "Creator auto-ADMIN on account creation (D-04)"
  - "Last-admin protection in removeAccess"
  - "Archived accounts excluded by default, included on request (D-07)"
affects: [03-05, 03-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Service receives userEmail from controller — never touches SecurityContextHolder"
    - "Access-filtered repository queries return Object[] [Account, AccessLevel] pairs"
    - "Partial PATCH semantics via nullable UpdateAccountRequest fields — only non-null fields applied"
    - "D-02: 403 when account exists but user has no access (not 404, avoids leaking existence)"

key-files:
  created:
    - backend/src/main/java/com/prosperity/account/AccountService.java
  modified: []

key-decisions:
  - "orElseThrow lambda in getAccount/updateAccount distinguishes 403 vs 404 via existsById check"
  - "setAccess uses orElseGet to create new AccountAccess lazily only when entry doesn't exist"
  - "removeAccess verifies entry.bankAccount.id matches route accountId to prevent cross-account access manipulation"

patterns-established:
  - "Pattern: service methods are @Transactional at method level, read-only methods use @Transactional(readOnly = true)"
  - "Pattern: ADMIN check via accountRepository.hasAccess() before any access management mutation"
  - "Pattern: resolveUser(email) private helper centralises user lookup + RuntimeException on missing user"

requirements-completed: [ACCT-01, ACCT-02, ACCT-04, ACCT-05, ACCS-01, ACCS-02, ACCS-03]

# Metrics
duration: 2min
completed: 2026-04-05
---

# Phase 03 Plan 04: AccountService Summary

**AccountService with 7 business methods enforcing WRITE/ADMIN access gates, creator auto-ADMIN (D-04), 403-vs-404 distinction (D-02), and last-admin protection**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-04-05T13:00:00Z
- **Completed:** 2026-04-05T13:01:22Z
- **Tasks:** 2 (implemented in one commit — both tasks write to same file)
- **Files modified:** 1

## Accomplishments

- Full AccountService with all 7 business methods compiling cleanly
- Access enforcement: repo-level READ filtering, WRITE required for update, ADMIN for access management
- Creator automatically receives ADMIN access entry on account creation (D-04); no auto-access for other users on shared accounts (D-05)
- Archived accounts excluded by default via separate repository query (D-07)
- Last-admin protection in removeAccess throws IllegalStateException before deleting sole ADMIN entry
- No SecurityContextHolder usage — all methods receive userEmail from controller layer

## Task Commits

1. **Task 1 + Task 2: AccountService — CRUD and access management** - `be831eb` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `backend/src/main/java/com/prosperity/account/AccountService.java` — All 7 business methods + private helpers resolveUser, toResponse, toAccessResponse

## Decisions Made

- Tasks 1 and 2 were both implemented in the same `AccountService.java` file and committed together since they represent a single logical unit; splitting would have left the file in a partial state
- `orElseThrow` with a lambda that calls `existsById` used to differentiate 403 from 404 in getAccount and updateAccount — matches D-02 requirement without extra query on the happy path
- `setAccess` uses `orElseGet` to lazily construct a new AccountAccess only when no entry exists, loading the Account entity only in that branch

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- AccountService is ready for AccountController (Plan 03-05) to wire HTTP endpoints
- All 7 service methods match the interface expected by the controller plan
- No blockers
