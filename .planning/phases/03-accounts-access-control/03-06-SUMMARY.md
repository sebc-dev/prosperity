---
phase: 03-accounts-access-control
plan: "06"
subsystem: backend-testing
tags: [testing, unit-tests, integration-tests, account, access-control]
dependency_graph:
  requires: [03-04, 03-05]
  provides: [acceptance-gate-backend-03]
  affects: [AccountService, AccountController, AccountRepository]
tech_stack:
  added: []
  patterns:
    - Mockito @ExtendWith(MockitoExtension.class) for unit tests
    - SpringBootTest + Testcontainers for integration tests
    - accessRows() helper for Object[] mock return types
    - List<Object[]> return type for multi-projection JPQL (avoids Optional<Object[]> Hibernate bug)
key_files:
  created:
    - backend/src/test/java/com/prosperity/account/AccountServiceTest.java
    - backend/src/test/java/com/prosperity/account/AccountControllerTest.java
  modified:
    - backend/src/main/java/com/prosperity/account/AccountService.java
    - backend/src/main/java/com/prosperity/account/AccountRepository.java
decisions:
  - findByIdAndUserId returns List<Object[]> not Optional<Object[]> to avoid Hibernate multi-projection wrapping bug
  - accessRows() helper in unit tests wraps Object[] in ArrayList to satisfy Java type inference
metrics:
  duration: 14min
  completed_date: "2026-04-05"
  tasks_completed: 2
  files_changed: 4
---

# Phase 03 Plan 06: Account Tests Summary

Unit tests for AccountService (Mockito) and integration tests for AccountController (Testcontainers + MockMvc) covering all 9 phase requirements with 28 passing tests and one auto-fixed Hibernate bug.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | AccountServiceTest unit tests | 7767061 | AccountServiceTest.java |
| 2 | AccountControllerTest integration tests + Hibernate fix | 984b269 | AccountControllerTest.java, AccountService.java, AccountRepository.java, AccountServiceTest.java |

## Outcomes

### AccountServiceTest (13 unit tests, @ExtendWith(MockitoExtension.class))

Covers all AccountService business rules with mocked repositories. No Spring context loaded.

Tests covering ACCT-01 to ACCT-05:
- `create_account_saves_account_and_returns_response`
- `create_account_grants_admin_access_to_creator` — ArgumentCaptor verifies ADMIN level (D-04)
- `get_accounts_returns_only_accessible_non_archived`
- `get_accounts_includes_archived_when_requested` — D-07
- `get_account_throws_access_denied_when_no_access` — D-02: 403, not 404
- `get_account_throws_not_found_when_account_missing`
- `update_account_applies_partial_fields` — D-08 partial PATCH
- `update_account_rejects_read_only_user`

Tests covering ACCS-01 to ACCS-04:
- `get_access_entries_requires_admin_level`
- `set_access_creates_new_entry_when_not_exists`
- `set_access_updates_existing_entry`
- `remove_access_deletes_entry`
- `remove_access_prevents_removing_last_admin` — IllegalStateException

### AccountControllerTest (15 integration tests, @SpringBootTest + Testcontainers)

Covers full HTTP layer with real PostgreSQL via Testcontainers.

Account CRUD: create PERSONAL/SHARED returns 201 with ADMIN access, list returns only accessible accounts, list excludes archived by default, includes when requested, GET returns 403 with no access, PATCH changes name, PATCH archives account, PATCH returns 403 for READ-only user.

Access management: GET /access returns entries for ADMIN, GET /access returns 403 for WRITE user, POST /access grants new user, DELETE /access returns 204, DELETE last admin returns 409.

Users endpoint: GET /api/users returns all users.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed Hibernate Optional<Object[]> multi-projection bug in AccountRepository**

- **Found during:** Task 2
- **Issue:** `AccountRepository.findByIdAndUserId` returned `Optional<Object[]>`. When a row exists, Hibernate wrapped the result as `Object[]{Account}` (length 1) losing the `AccessLevel` scalar. When no row exists, it returned `Optional.of(new Object[0])` (empty array) instead of `Optional.empty()`. Both cases caused `ArrayIndexOutOfBoundsException`.
- **Fix:** Changed `findByIdAndUserId` return type from `Optional<Object[]>` to `List<Object[]>` (consistent with other repo methods). Updated `AccountService.getAccount` and `updateAccount` to use `list.isEmpty()` check instead of `Optional.orElseThrow`. Updated unit test mocks accordingly.
- **Files modified:** `AccountRepository.java`, `AccountService.java`, `AccountServiceTest.java`
- **Commit:** 984b269

**2. [Rule 1 - Bug] Java type inference for Object[] in unit test mocks**

- **Found during:** Task 1
- **Issue:** `List.of(new Object[]{...})` infers `List<Object>` not `List<Object[]>` due to Java varargs erasure. `Optional.of(new Object[]{...})` had similar type inference issues.
- **Fix:** Used `new ArrayList<>()` with explicit `.add(new Object[]{...})` for lists, and an `accessRows()` helper method.
- **Files modified:** `AccountServiceTest.java`
- **Commit:** 7767061

## Known Stubs

None. All tests verify concrete behavior against real implementations.

## Self-Check: PASSED
