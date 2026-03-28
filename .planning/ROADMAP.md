# Roadmap: Prosperity

## Overview

Prosperity delivers a self-hosted personal finance app for a household of two, built from domain model outward. The build order follows natural dependencies: foundation and domain model first, then authentication (everything needs users), then accounts and access control (everything needs accounts), then categories and transactions (the operational core), then envelopes (depend on categorized transactions), then Plaid sync (enriches an already stable model), then administration and debt tracking, and finally the dashboard that consumes everything. Each phase delivers a coherent, reviewable increment.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Project Foundation** - Scaffolding, domain model, dev infrastructure (Docker Compose, Flyway, CI), comprehensive quality gates (lint, format, static analysis, coverage, security scanning)
- [ ] **Phase 2: Authentication & Setup Wizard** - BFF cookie auth, CSRF protection, session persistence, first-launch wizard
- [ ] **Phase 3: Accounts & Access Control** - Bank account CRUD (personal + shared), per-user permissions, repository-level filtering
- [ ] **Phase 4: Categories** - Hierarchical category system with Plaid base categories and custom user categories
- [ ] **Phase 5: Transactions** - Manual entry, edit, delete, recurring templates, pointage, split, search, pagination
- [ ] **Phase 6: Envelope Budgets** - Per-account envelopes with allocation, auto-imputation, rollover, visual indicators
- [ ] **Phase 7: Plaid Integration** - Abstract bank connector + Plaid implementation (sync, pending/posted, PSD2 consent)
- [ ] **Phase 8: Administration** - User invitation, rights management, system monitoring
- [ ] **Phase 9: Internal Debt** - Automatic debt calculation from shared account transactions, repayment tracking
- [ ] **Phase 10: Dashboard & Production Readiness** - Consolidated dashboard with charts, automated backup, PWA

## Phase Details

### Phase 1: Project Foundation
**Goal**: A working development environment with a validated domain model, comprehensive quality gates, and a CI pipeline that enforces code quality from day one
**Depends on**: Nothing (first phase)
**Requirements**: INFR-02, INFR-04, INFR-05, INFR-06, INFR-07, INFR-08, INFR-09, INFR-10
**Success Criteria** (what must be TRUE):
  1. `docker compose up -d` starts PostgreSQL, Spring Boot, and Caddy and the API responds on /api/health
  2. `./mvnw test` runs domain model unit tests (Money value object with BigDecimal, Account, Transaction with matching states, Envelope with rollover/overspend) and all pass
  3. `pnpm dev` starts the Angular SPA and it loads in the browser
  4. Flyway migrations execute on startup and create the database schema
  5. Domain model enforces Money as BigDecimal (no floating-point) and Transaction states (MANUAL_UNMATCHED, IMPORTED_UNMATCHED, MATCHED)
  6. `./mvnw verify` runs Checkstyle, google-java-format check, static analysis, dead code detection, test coverage threshold check, and OWASP dependency scan -- build fails if any gate is violated
  7. `pnpm lint` runs ESLint and `pnpm format:check` runs Prettier -- both fail on violations
  8. Pre-commit hooks (via Husky or lefthook) automatically run lint and format checks before each commit, preventing non-compliant code from entering the repository
  9. CI pipeline (GitHub Actions) runs all quality gates (lint, format, static analysis, dead code, coverage thresholds, security scan) on every push/PR and blocks merge on failure
**Plans**: 13 plans

Plans:
- [x] 01-01-PLAN.md — Backend scaffold: Maven project + quality gate plugins
- [x] 01-02-PLAN.md — Value objects + enums: Money, MoneyConverter, enums, BankConnector interface
- [ ] 01-03-PLAN.md — User entity + UserRepository (auth layer)
- [ ] 01-04-PLAN.md — Account + AccountAccess entities + repositories (account layer)
- [ ] 01-05-PLAN.md — Transaction entity + TransactionRepository (transaction layer)
- [x] 01-06-PLAN.md — Frontend scaffolding: Angular 21 + PrimeNG + Tailwind + ESLint + Prettier
- [ ] 01-07-PLAN.md — Category + Envelope + EnvelopeAllocation entities + repositories (envelope/category layer)
- [ ] 01-08-PLAN.md — Flyway migrations: V001 through V006 initial schema
- [ ] 01-09-PLAN.md — Domain unit tests: Money, TransactionState, Envelope
- [ ] 01-10-PLAN.md — ArchUnit architecture tests
- [ ] 01-11-PLAN.md — Boot test: ProsperityApplicationTest
- [x] 01-12-PLAN.md — Docker Compose + Caddy + backend Dockerfile
- [ ] 01-13-PLAN.md — Lefthook pre-commit hooks + GitHub Actions CI pipeline
### Phase 2: Authentication & Setup Wizard
**Goal**: Users can securely access the application, starting with admin account creation on first launch
**Depends on**: Phase 1
**Requirements**: AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05
**Success Criteria** (what must be TRUE):
  1. First launch shows a setup wizard that creates the admin account (email + password)
  2. User can log in with email/password and receives httpOnly cookie (no JWT in browser storage)
  3. User can log out from any page and is redirected to the login screen
  4. User session persists after browser refresh without re-login
  5. CSRF token is active on all mutating endpoints (POST/PUT/DELETE return 403 without valid token)
**Plans**: TBD
**UI hint**: yes

Plans:
- [ ] 02-01: TBD
- [ ] 02-02: TBD

### Phase 3: Accounts & Access Control
**Goal**: Users can create and manage bank accounts (personal and shared) with per-user access permissions enforced at every level
**Depends on**: Phase 2
**Requirements**: ACCT-01, ACCT-02, ACCT-03, ACCT-04, ACCT-05, ACCS-01, ACCS-02, ACCS-03, ACCS-04
**Success Criteria** (what must be TRUE):
  1. User can create a personal bank account and a shared bank account visible to authorized users
  2. User sees only the accounts they have access to (personal accounts + shared accounts with granted permission)
  3. Admin can set read/write/admin permissions per user per account
  4. User can edit account name/type and archive an account (hidden but data preserved)
  5. Access control applies to all data queries (a user without access to an account cannot see its data in any API endpoint)
**Plans**: TBD
**UI hint**: yes

Plans:
- [ ] 03-01: TBD
- [ ] 03-02: TBD

### Phase 4: Categories
**Goal**: A hierarchical category system exists that transactions and envelopes will use for classification
**Depends on**: Phase 3
**Requirements**: CATG-01, CATG-02, CATG-03, CATG-04
**Success Criteria** (what must be TRUE):
  1. Plaid base categories are seeded in the database and available for selection
  2. User can create custom categories and sub-categories (parent/child hierarchy)
  3. User can change the category assigned to any transaction
  4. Categories are displayed hierarchically in selection UI (parent > sub-category)
**Plans**: TBD
**UI hint**: yes

Plans:
- [ ] 04-01: TBD

### Phase 5: Transactions
**Goal**: Users can manage their financial transactions manually with full CRUD, search, and reconciliation support
**Depends on**: Phase 4
**Requirements**: TXNS-01, TXNS-02, TXNS-03, TXNS-04, TXNS-05, TXNS-06, TXNS-07, TXNS-08
**Success Criteria** (what must be TRUE):
  1. User can create, edit, and delete a manual transaction (amount, date, description, category, account)
  2. User can create recurring transaction templates (e.g., rent, subscriptions) and generate transactions from them
  3. User can manually reconcile (pointer) a manual transaction with an imported transaction (matching pair counts once in balances)
  4. User can split a single transaction across multiple categories
  5. User can search and filter transactions by date, amount, category, and description with paginated results
**Plans**: TBD
**UI hint**: yes

Plans:
- [ ] 05-01: TBD
- [ ] 05-02: TBD

### Phase 6: Envelope Budgets
**Goal**: Users can budget with per-account envelopes that automatically track spending from categorized transactions
**Depends on**: Phase 5
**Requirements**: ENVL-01, ENVL-02, ENVL-03, ENVL-04, ENVL-05, ENVL-06, ENVL-07
**Success Criteria** (what must be TRUE):
  1. User can create an envelope on a specific account and allocate a monthly budget amount
  2. Categorized transactions automatically reduce the corresponding envelope balance
  3. Envelope rollover is configurable per envelope (carry forward remaining or reset to zero each month)
  4. Visual indicators show envelope status: green (on track), yellow (>80% consumed), red (overspent)
  5. User can view consumption history for an envelope and can modify or delete envelopes
**Plans**: TBD
**UI hint**: yes

Plans:
- [ ] 06-01: TBD
- [ ] 06-02: TBD

### Phase 7: Plaid Integration
**Goal**: Bank transactions sync automatically from Societe Generale and Banque Populaire via Plaid with proper lifecycle management
**Depends on**: Phase 5
**Requirements**: PLAD-01, PLAD-02, PLAD-03, PLAD-04, PLAD-05, PLAD-06, PLAD-07, ADMN-03
**Success Criteria** (what must be TRUE):
  1. Admin can connect a bank account via Plaid Link and configure connection settings (add, remove, view status)
  2. User can trigger a manual import and transactions appear with Plaid categories pre-filled
  3. Scheduled automatic import runs at a configurable frequency (batch)
  4. Initial import depth is configurable and pending-to-posted transitions are handled correctly (delete + recreate, not update)
  5. PSD2 consent expiration (180 days) is tracked and surfaced in admin UI before expiry
**Plans**: TBD
**UI hint**: yes

Plans:
- [ ] 07-01: TBD
- [ ] 07-02: TBD
- [ ] 07-03: TBD

### Phase 8: Administration
**Goal**: Admin can manage the household's users and monitor system health
**Depends on**: Phase 2
**Requirements**: ADMN-01, ADMN-02, ADMN-04
**Success Criteria** (what must be TRUE):
  1. Admin can invite new users by email and they can create their account from the invitation
  2. Admin can view and modify user roles/rights
  3. Admin can see system monitoring: sync status, last sync time, application health indicators
**Plans**: TBD
**UI hint**: yes

Plans:
- [ ] 08-01: TBD

### Phase 9: Internal Debt
**Goal**: The household can track who owes whom based on shared account transactions
**Depends on**: Phase 5, Phase 8
**Requirements**: DEBT-01, DEBT-02, DEBT-03, DEBT-04
**Success Criteria** (what must be TRUE):
  1. System automatically calculates debt balances from transactions on shared accounts (who paid what)
  2. Each user sees their debt balance with every other household member
  3. User can record a repayment that adjusts the debt balance toward zero
  4. Full history of debts and repayments is accessible (long-term tracking)
**Plans**: TBD
**UI hint**: yes

Plans:
- [ ] 09-01: TBD

### Phase 10: Dashboard & Production Readiness
**Goal**: Users have a daily-use consolidated view and the application is production-ready for self-hosting
**Depends on**: Phase 6, Phase 7, Phase 9
**Requirements**: DASH-01, DASH-02, DASH-03, DASH-04, INFR-01, INFR-03
**Success Criteria** (what must be TRUE):
  1. User sees all account balances on a single consolidated dashboard view
  2. User sees envelope status (remaining, consumed, percentage) on the dashboard
  3. User sees evolution charts (balances and expenses over time) powered by ngx-echarts
  4. User sees the latest transactions across all accounts on the dashboard
  5. pg_dump backup runs on a configurable schedule and the PWA is installable with an active service worker
**Plans**: TBD
**UI hint**: yes

Plans:
- [ ] 10-01: TBD
- [ ] 10-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Project Foundation | 0/13 | Planning | - |
| 2. Authentication & Setup Wizard | 0/2 | Not started | - |
| 3. Accounts & Access Control | 0/2 | Not started | - |
| 4. Categories | 0/1 | Not started | - |
| 5. Transactions | 0/2 | Not started | - |
| 6. Envelope Budgets | 0/2 | Not started | - |
| 7. Plaid Integration | 0/3 | Not started | - |
| 8. Administration | 0/1 | Not started | - |
| 9. Internal Debt | 0/1 | Not started | - |
| 10. Dashboard & Production Readiness | 0/2 | Not started | - |
