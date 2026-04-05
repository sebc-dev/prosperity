---
phase: 03-accounts-access-control
plan: "03"
subsystem: account
tags: [repository, jpql, access-control, data-access]
dependency_graph:
  requires: [03-01, 03-02]
  provides: [account-repository-queries, access-repository-queries]
  affects: [account-service, account-controller]
tech_stack:
  added: []
  patterns: [JPQL-join-filter, Spring-Data-derived-queries]
key_files:
  created: []
  modified:
    - backend/src/main/java/com/prosperity/account/AccountRepository.java
    - backend/src/main/java/com/prosperity/account/AccountAccessRepository.java
decisions:
  - "AccountRepository returns Object[] pairs [Account, AccessLevel] to avoid N+1 when projecting access level alongside account"
  - "AccountAccessRepository uses Spring Data derived queries (no @Query) — method names map directly to JPA property navigation"
metrics:
  duration: "1min"
  completed_date: "2026-04-05"
  tasks_completed: 2
  files_modified: 2
---

# Phase 03 Plan 03: Repository JPQL Queries Summary

JPQL access-filtered queries added to AccountRepository and AccountAccessRepository — every account query JOINs on account_access, forming the data access foundation for D-01 access control.

## What Was Built

### AccountRepository (4 JPQL methods)

All queries JOIN on `AccountAccess` so no account is ever returned without a matching access entry for the requesting user. The inherited `findAll()` from `JpaRepository` is not exposed to service code.

- `findAllAccessibleByUserId(UUID userId)` — non-archived accounts + access level, ordered by name
- `findAllAccessibleByUserIdIncludingArchived(UUID userId)` — same JOIN but includes archived (D-07)
- `findByIdAndUserId(UUID accountId, UUID userId)` — single account detail with access level, returns `Optional<Object[]>`
- `hasAccess(UUID accountId, UUID userId, Collection<AccessLevel> levels)` — boolean authorization check using `IN :levels`

### AccountAccessRepository (3 derived query methods)

Spring Data derived queries (no `@Query` needed) for access management operations:

- `findByBankAccountId(UUID bankAccountId)` — all access entries for an account (access management dialog)
- `findByBankAccountIdAndUserId(UUID bankAccountId, UUID userId)` — find a specific user's entry
- `countByBankAccountIdAndAccessLevel(UUID bankAccountId, AccessLevel accessLevel)` — count admins to prevent removing the last one

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1: AccountRepository JPQL queries | 83d02db | feat(03-03): add JPQL access-filtered queries to AccountRepository |
| Task 2: AccountAccessRepository queries | 7dfc8c3 | feat(03-03): add derived queries to AccountAccessRepository |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — these are repository interfaces with no UI or stub data.

## Self-Check: PASSED

- `backend/src/main/java/com/prosperity/account/AccountRepository.java` — FOUND
- `backend/src/main/java/com/prosperity/account/AccountAccessRepository.java` — FOUND
- Commit 83d02db — FOUND
- Commit 7dfc8c3 — FOUND
- `./mvnw compile` — PASSED
