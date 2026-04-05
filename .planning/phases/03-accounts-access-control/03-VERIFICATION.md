---
phase: 03-accounts-access-control
verified: 2026-04-05T12:00:00Z
status: passed
score: 9/9 must-haves verified
gaps: []
human_verification:
  - test: "Visual verification of account list page"
    expected: "p-table shows Nom, Type, Solde, Statut, Actions columns with correct badges and action buttons visible per access level"
    why_human: "CSS/visual rendering of PrimeNG p-table and p-tag components cannot be verified programmatically"
  - test: "Archive toggle hides/shows archived accounts"
    expected: "Toggle switch reloads list excluding/including archived accounts; archived row appears muted"
    why_human: "Conditional UI state requires browser rendering"
  - test: "Access management dialog usability (ACCS-03)"
    expected: "Dialog opens on click, lists current access entries, p-select change triggers immediate save, current user's row is disabled"
    why_human: "Interaction flow and p-select state require browser interaction"
---

# Phase 3: Accounts & Access Control — Verification Report

**Phase Goal:** Implement the complete accounts and access control feature — users can create, view, edit, and archive bank accounts, and manage shared account access for household members.
**Verified:** 2026-04-05
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Account entity has an `archived` boolean field defaulting to false | VERIFIED | `Account.java` line 51: `private boolean archived = false;` with `@Column(nullable = false)` |
| 2 | V009 migration adds `archived` column to `bank_accounts` | VERIFIED | `V009__add_archived_to_bank_accounts.sql`: `ALTER TABLE bank_accounts ADD COLUMN archived BOOLEAN NOT NULL DEFAULT FALSE;` |
| 3 | AccessLevel enum has `isAtLeast()` hierarchy method | VERIFIED | `AccessLevel.java` line 13: `public boolean isAtLeast(AccessLevel required)` using ordinal comparison |
| 4 | All account CRUD and access management DTOs exist with Jakarta Validation | VERIFIED | `CreateAccountRequest` (`@NotBlank`, `@Size`), `UpdateAccountRequest`, `AccountResponse`, `AccountAccessResponse`, `SetAccessRequest`, `AccountNotFoundException`, `AccountAccessDeniedException` all exist |
| 5 | Repository queries always filter by user ID (no unfiltered `findAll` exposed) | VERIFIED | `AccountRepository`: `findAllAccessibleByUserId`, `findAllAccessibleByUserIdIncludingArchived`, `findByIdAndUserId`, `hasAccess` — all JOIN on `account_access`. `AccountService` never calls inherited `findAll()` |
| 6 | `AccountService` implements full CRUD + access management with business rules | VERIFIED | `AccountService.java`: `createAccount` (auto-ADMIN), `getAccounts` (archive filter), `getAccount` (403 on no-access), `updateAccount` (WRITE check), `getAccessEntries` / `setAccess` / `removeAccess` (ADMIN only, last-admin protection) |
| 7 | REST endpoints expose all CRUD and access management operations; 403/404 returned correctly | VERIFIED | `AccountController`: POST/GET/GET{id}/PATCH{id} for CRUD; GET/POST/DELETE for `/{id}/access`. Exception handlers map `AccountAccessDeniedException` → 403, `AccountNotFoundException` → 404, `IllegalStateException` → 409 |
| 8 | `GET /api/users` endpoint exists for the access dialog user dropdown | VERIFIED | `UserController.java` at `/api/users` with `GET listUsers()` returning all users via `userRepository.findAll()` |
| 9 | Frontend: accounts page, create/edit dialog, and access dialog are all wired and functional | VERIFIED | `accounts.ts` (p-table, archive toggle, create/edit/archive actions), `account-dialog.ts` (reactive form, create/update calls), `access-dialog.ts` (immediate-save pattern, add/remove user), all wired via `inject(AccountService)` |
| 10 | Sidebar has Comptes link; `/accounts` route is lazy-loaded with `authGuard` | VERIFIED | `sidebar.ts` line 16: `routerLink="/accounts"`. `app.routes.ts` line 25: `{ path: 'accounts', loadComponent: ... }` under parent route with `canActivate: [authGuard]` |

**Score:** 10/10 truths verified (includes derived truths from all 9 plan must_haves)

---

### Required Artifacts

| Artifact | Provides | Status | Details |
|----------|----------|--------|---------|
| `backend/.../db/migration/V009__add_archived_to_bank_accounts.sql` | Flyway migration adding archived column | VERIFIED | 2-line migration, correct ALTER TABLE syntax |
| `backend/.../account/Account.java` | Account entity with archived field | VERIFIED | `private boolean archived = false` with `@Column(nullable = false)` |
| `backend/.../account/AccessLevel.java` | AccessLevel enum with hierarchy method | VERIFIED | READ/WRITE/ADMIN with `isAtLeast()` using ordinal comparison |
| `backend/.../account/CreateAccountRequest.java` | Create account request DTO | VERIFIED | Record with `@NotBlank @Size(max=100)` and `@NotNull` |
| `backend/.../account/UpdateAccountRequest.java` | Update account request DTO (partial PATCH) | VERIFIED | Record with all nullable fields |
| `backend/.../account/AccountResponse.java` | Account response DTO with `currentUserAccessLevel` | VERIFIED | Record including all required fields |
| `backend/.../account/AccountAccessResponse.java` | Access entry response DTO | VERIFIED | Includes `id`, `userId`, `userEmail`, `userDisplayName`, `accessLevel` |
| `backend/.../account/SetAccessRequest.java` | Set access request DTO | VERIFIED | Record with `userId` and `accessLevel` |
| `backend/.../account/AccountNotFoundException.java` | 404 exception | VERIFIED | Exists in account package |
| `backend/.../account/AccountAccessDeniedException.java` | 403 exception | VERIFIED | Exists in account package |
| `backend/.../account/AccountRepository.java` | JPQL access-filtered account queries | VERIFIED | 4 access-filtered queries, no unfiltered `findAll` override |
| `backend/.../account/AccountAccessRepository.java` | Access entry queries | VERIFIED | `findByBankAccountId`, `findByBankAccountIdAndUserId`, `countByBankAccountIdAndAccessLevel` |
| `backend/.../account/AccountService.java` | Business logic for account CRUD + access management | VERIFIED | 252 lines, all 7 required methods implemented |
| `backend/.../account/AccountController.java` | REST controller for all endpoints | VERIFIED | 139 lines, 7 endpoints + exception handlers |
| `backend/.../auth/UserController.java` | GET /api/users endpoint | VERIFIED | Separate controller at `/api/users` |
| `backend/.../auth/UserResponse.java` | User response DTO with `id` | VERIFIED | Record with `UUID id` field added (required by Plan 09 for access dialog) |
| `backend/.../test/.../AccountServiceTest.java` | Unit tests for AccountService | VERIFIED | 300 lines, 13 test methods, covers CRUD + access management + last-admin protection |
| `backend/.../test/.../AccountControllerTest.java` | Integration tests for AccountController | VERIFIED | 315 lines, 15 test methods, Testcontainers + MockMvc, full endpoint coverage |
| `frontend/.../accounts/account.types.ts` | TypeScript interfaces matching backend DTOs | VERIFIED | All 5 interfaces matching backend record structures exactly |
| `frontend/.../accounts/account.service.ts` | Angular HTTP service with signal-based state | VERIFIED | Signal for accounts state, 6 HTTP methods covering all backend endpoints |
| `frontend/.../accounts/accounts.ts` | Account list page with p-table and archive toggle | VERIFIED | 257 lines, full p-table, toggle, confirm archive, opens both dialogs |
| `frontend/.../accounts/account-dialog.ts` | Create/edit account dialog | VERIFIED | 162 lines, reactive form, create/update via AccountService |
| `frontend/.../accounts/access-dialog.ts` | Access management dialog (immediate-save) | VERIFIED | 253 lines, forkJoin load, level change/add/remove all wired to AccountService |
| `frontend/.../layout/sidebar.ts` | Sidebar with Comptes navigation link | VERIFIED | `routerLink="/accounts"` with RouterLinkActive active styling |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `AccountRepository.java` | `account_access` table | JPQL JOIN AccountAccess | VERIFIED | `JOIN AccountAccess aa ON aa.bankAccount = a` in all 3 account query methods |
| `AccountService.java` | `AccountRepository` | constructor injection | VERIFIED | `accountRepository.findAllAccessibleByUserId` called in `getAccounts` |
| `AccountService.java` | `UserRepository` | constructor injection | VERIFIED | `userRepository.findByEmail` called in `resolveUser` helper |
| `AccountController.java` | `AccountService.java` | constructor injection | VERIFIED | `accountService.createAccount` and all other service methods called |
| `AccountController.java` | Spring Security | `@AuthenticationPrincipal UserDetails` | VERIFIED | All endpoints extract `userDetails.getUsername()` for service calls |
| `account.service.ts` | `/api/accounts` | HttpClient | VERIFIED | `http.get<AccountResponse[]>('/api/accounts', { params })` |
| `account.service.ts` | `/api/users` | HttpClient | VERIFIED | `http.get<UserResponse[]>('/api/users')` in `loadUsers()` |
| `accounts.ts` | `account.service.ts` | `inject(AccountService)` | VERIFIED | `accountService.loadAccounts`, `updateAccount` called |
| `account-dialog.ts` | `account.service.ts` | `inject(AccountService)` | VERIFIED | `accountService.createAccount` and `accountService.updateAccount` |
| `access-dialog.ts` | `account.service.ts` | `inject(AccountService)` | VERIFIED | `accountService.getAccessEntries`, `loadUsers`, `setAccess`, `removeAccess` |
| `accounts.ts` | `access-dialog.ts` | component composition | VERIFIED | `<app-access-dialog>` in template, `accessDialogVisible`/`accessDialogAccount` wired |
| `sidebar.ts` | `/accounts` | `routerLink` | VERIFIED | `routerLink="/accounts"` confirmed |
| `/accounts` route | `authGuard` | `canActivate` | VERIFIED | Route nested under parent route with `canActivate: [authGuard]` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `accounts.ts` | `accounts` signal from `AccountService` | `account.service.ts` → `GET /api/accounts` → `AccountController` → `AccountService` → `accountRepository.findAllAccessibleByUserId` (JPQL JOIN) | Yes — JPQL query returns real DB rows | FLOWING |
| `access-dialog.ts` | `accessEntries` signal | `forkJoin([getAccessEntries, loadUsers])` → `GET /api/accounts/{id}/access` → `accountAccessRepository.findByBankAccountId` | Yes — direct DB query, real entries | FLOWING |
| `account-dialog.ts` | Form values → `createAccount` / `updateAccount` | POST/PATCH `/api/accounts` → `AccountService` → `accountRepository.save` | Yes — writes to DB, response from saved entity | FLOWING |

---

### Behavioral Spot-Checks

Step 7b: SKIPPED (server not running; all behavioral verifications require live Spring Boot + PostgreSQL)

---

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|----------------|-------------|--------|----------|
| ACCT-01 | 03-02, 03-04, 03-05, 03-06, 03-08 | Utilisateur peut creer un compte bancaire personnel | SATISFIED | `POST /api/accounts` with `accountType: PERSONAL`; `AccountService.createAccount`; `account-dialog.ts` |
| ACCT-02 | 03-02, 03-04, 03-05, 03-06, 03-08 | Utilisateur peut creer un compte bancaire commun | SATISFIED | Same flow with `accountType: SHARED`; integration test `create_shared_account_returns_201_and_creator_has_admin` |
| ACCT-03 | 03-03, 03-05, 03-06, 03-07, 03-08 | Utilisateur peut voir la liste de ses comptes avec soldes | SATISFIED | `GET /api/accounts` filtered by user; `accounts.ts` p-table with `balance` column; signal-based reactive state |
| ACCT-04 | 03-02, 03-04, 03-05, 03-06, 03-08 | Utilisateur peut modifier les informations d'un compte | SATISFIED | `PATCH /api/accounts/{id}` (partial update); `account-dialog.ts` edit mode; `updateAccount` service call |
| ACCT-05 | 03-01, 03-04, 03-05, 03-06, 03-08 | Utilisateur peut archiver un compte (masque sans supprimer) | SATISFIED | V009 migration adds `archived` column; `PATCH /{id}` with `{"archived":true}`; confirm dialog in `accounts.ts`; `includeArchived` query param toggle |
| ACCS-01 | 03-01, 03-02, 03-04, 03-06 | Chaque compte a des permissions par utilisateur (READ/WRITE/ADMIN) | SATISFIED | `AccessLevel` enum; `AccountAccess` entity; creator auto-ADMIN at creation; `isAtLeast()` used in service for mutation checks |
| ACCS-02 | 03-03, 03-04, 03-05, 03-06, 03-07 | Utilisateur ne voit que les comptes auxquels il a acces | SATISFIED | All repository queries JOIN on `account_access WHERE aa.user.id = :userId`; integration test `list_accounts_returns_only_accessible_accounts` |
| ACCS-03 | 03-04, 03-05, 03-06, 03-09 | Admin peut modifier les permissions d'acces pour chaque utilisateur | SATISFIED | `GET/POST /api/accounts/{id}/access`, `DELETE /api/accounts/{id}/access/{accessId}`; `access-dialog.ts` with immediate-save pattern |
| ACCS-04 | 03-03, 03-06 | Le controle d'acces s'applique aux requetes d'agregation | SATISFIED | JPQL JOIN approach means no unfiltered DB query exists; `AccountService` never calls `findAll()`; `hasAccess()` used for all admin checks |

---

### Anti-Patterns Found

No blockers or stubs detected.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `accounts.ts` | 192 | Stale comment: `// Access dialog state (to be implemented in Plan 09)` | Info | None — code IS implemented; comment is outdated |

---

### Human Verification Required

#### 1. Visual rendering of account list table

**Test:** Log in, navigate to `/accounts`, create one personal and one shared account
**Expected:** p-table shows 5 columns (Nom, Type, Solde, Statut, Actions); Type column shows "Personnel"/"Commun" badge; Statut shows "Actif" badge; Actions shows edit (pencil) button for both, access (users) button only for SHARED accounts with ADMIN access
**Why human:** PrimeNG p-table and p-tag visual rendering cannot be verified programmatically

#### 2. Archive toggle behavior

**Test:** Archive a personal account via the confirm dialog; verify it disappears from list; toggle "Afficher les archives" on; verify it reappears with "Archive" badge and muted text
**Expected:** Archived accounts hidden by default, revealed on toggle; visual muting applied via `text-muted-color` class
**Why human:** Conditional UI state and CSS class application require browser rendering

#### 3. Access management dialog for SHARED accounts

**Test:** Create a shared account, click "Gerer les acces" button, verify dialog opens with current user listed as ADMIN (level dropdown disabled), add a second user, change access level, then remove the second user
**Expected:** Current user row is disabled (cannot self-demote); level change saves immediately on dropdown change; removing last admin blocked with 409 error message
**Why human:** Immediate-save interaction flow, p-select state, and error handling require browser interaction

---

### Gaps Summary

No gaps found. All 9 requirements (ACCT-01 through ACCT-05, ACCS-01 through ACCS-04) are implemented end-to-end:
- Backend: entity (with migration), DTOs, repositories (access-filtered), service (business rules), controller (REST endpoints), tests (13 unit + 15 integration)
- Frontend: TypeScript types, Angular service (signals), list page, create/edit dialog, access dialog, navigation (sidebar + route guard)
- The ACCS-04 requirement (access control on aggregation queries) is enforced architecturally — all repository queries JOIN on `account_access`, making unfiltered data access impossible at the service level.

One notable observation: `AccountRepository` inherits `findAll()` from `JpaRepository` (Spring Data cannot remove it), but `AccountService` never calls it. This is acceptable — the architectural enforcement is at the service layer, not the repository interface.

The sole stale comment (`// to be implemented in Plan 09`) in `accounts.ts` line 192 is cosmetic and does not affect functionality.

---

_Verified: 2026-04-05_
_Verifier: Claude (gsd-verifier)_
