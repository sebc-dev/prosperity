# Roadmap: Prosperity

## Overview

Prosperity delivers a self-hosted financial management app for a couple, built in six phases. Phase 1 establishes the running infrastructure, authentication, and account management -- the foundation everything depends on. Phases 2 and 3 build the core financial engine: manual transactions with forecasting, then budgets and internal debt tracking. Phase 4 layers in automated bank sync via Plaid with reconciliation between manual forecasts and imported transactions. Phase 5 assembles the dashboard, quick-add mobile entry, and PWA shell -- the daily-use experience that ties all features together. Phase 6 hardens operations with backups, monitoring, and accessibility compliance.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation** - Infrastructure, authentication, and account management (completed 2026-03-09)
- [ ] **Phase 2: Transactions** - Manual entries, forecasts, recurring transactions, and history
- [ ] **Phase 3: Budgets and Debts** - Monthly budgets by category and internal debt tracking
- [ ] **Phase 4: Bank Sync** - Plaid integration, imported transactions, and reconciliation
- [ ] **Phase 5: Dashboard and Mobile** - Dashboard, quick-add, PWA shell, and responsive design
- [ ] **Phase 6: Hardening** - Backups, monitoring, and accessibility compliance

## Phase Details

### Phase 1: Foundation
**Goal**: Both users can log in to a running application, manage their profiles, and create bank accounts with proper personal/shared visibility
**Depends on**: Nothing (first phase)
**Requirements**: AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05, ACCT-01, ACCT-02, ACCT-03, INFR-01, INFR-02, INFR-03, INFR-04
**Success Criteria** (what must be TRUE):
  1. User can log in with email/password and stay logged in across browser sessions (JWT refresh works transparently)
  2. Admin and Standard roles enforce different capabilities (Admin sees system config, Standard does not)
  3. User can create Personal and Shared bank accounts, with Personal accounts invisible to the other user
  4. User can update display name and set preferences (theme, currency, favorite categories)
  5. Application runs via `docker compose up` with PostgreSQL, Spring Boot API, and SvelteKit web -- all accessible behind HTTPS with security headers
**Plans:** 6/6 plans complete

Plans:
- [ ] 01-01-PLAN.md — Backend scaffolding: Maven project, shared kernel, Spring Security, Liquibase migrations
- [ ] 01-02-PLAN.md — Frontend scaffolding: SvelteKit, Tailwind, Paraglide, Docker Compose, CI/CD
- [ ] 01-03-PLAN.md — Authentication: login, JWT refresh, setup wizard, role enforcement, security headers test
- [ ] 01-04-PLAN.md — Backend CRUD: account management with permissions, user profile/preferences, categories
- [ ] 01-05-PLAN.md — Accounts UI: component library, app layout, account cards, account creation
- [ ] 01-06-PLAN.md — Settings UI: profile, preferences, security, user management pages

### Phase 2: Transactions
**Goal**: Users can manage their financial forecasts through manual transaction entries, with recurring generation and dual balance visibility
**Depends on**: Phase 1
**Requirements**: TXNS-01, TXNS-02, TXNS-03, TXNS-04, TXNS-08, TXNS-09, TXNS-10, TXNS-11
**Success Criteria** (what must be TRUE):
  1. User can create manual transactions as forecasts, assign categories (default or custom), and edit or delete their own entries
  2. User can mark a manual entry as recurring (monthly); recurring entries generate automatically at the start of each month
  3. Unreconciled manual entries remain visible as expected future spending
  4. Each account displays dual balance: real (bank) and projected (real + unreconciled forecasts)
  5. User can browse transaction history with filters by date, category, account, and status
**Plans**: TBD

Plans:
- [ ] 02-01: TBD
- [ ] 02-02: TBD
- [ ] 02-03: TBD

### Phase 3: Budgets and Debts
**Goal**: Users can control spending through monthly budgets and automatically track who owes what within the couple
**Depends on**: Phase 2
**Requirements**: BUDG-01, BUDG-02, BUDG-03, BUDG-04, BUDG-05, DEBT-01, DEBT-02, DEBT-03
**Success Criteria** (what must be TRUE):
  1. User can create monthly budgets by category in either envelope mode (spend until empty) or goal mode (savings target)
  2. Budget progress displays visually with gauges, and in-app alerts fire at 75%, 90%, and 100% thresholds
  3. User can apply budget templates for quick setup of common categories
  4. User can mark a transaction as an advance for the couple, and the system calculates the net debt balance between both users automatically
  5. Debt balance is always visible and up to date as transactions are added or modified
**Plans**: TBD

Plans:
- [ ] 03-01: TBD
- [ ] 03-02: TBD
- [ ] 03-03: TBD

### Phase 4: Bank Sync
**Goal**: Admin can connect bank accounts via Plaid, transactions import automatically, and users can reconcile imported transactions against their manual forecasts
**Depends on**: Phase 2
**Requirements**: ACCT-04, ACCT-05, ACCT-06, ACCT-07, TXNS-05, TXNS-06, TXNS-07
**Success Criteria** (what must be TRUE):
  1. Admin can connect a bank account via Plaid Link and transactions import automatically
  2. Imported transactions appear with source IMPORTED and status STANDALONE
  3. User can reconcile an imported transaction with a manual forecast entry -- both become RECONCILED
  4. System suggests reconciliation matches based on amount tolerance and date proximity
  5. Plaid tokens are encrypted AES-256 at rest, and Plaid errors (token expiry, institution down, PSD2 re-auth) are handled gracefully with user-facing messages
**Plans**: TBD

Plans:
- [ ] 04-01: TBD
- [ ] 04-02: TBD
- [ ] 04-03: TBD

### Phase 5: Dashboard and Mobile
**Goal**: Users have a comprehensive dashboard for financial overview and a fast mobile experience for daily use
**Depends on**: Phase 3, Phase 4
**Requirements**: DASH-01, DASH-02, DASH-03, DASH-04, DASH-05, TXNS-12, PWA-01, PWA-02, PWA-03
**Success Criteria** (what must be TRUE):
  1. Dashboard displays account balances (real + projected), budget gauges, 5 most recent transactions with status indicators, and the debt balance widget
  2. Dashboard layout is responsive and usable on both mobile and desktop
  3. User can add a transaction via quick-add in 3 taps or fewer (amount, favorite category, confirm)
  4. App is installable as a PWA with manifest, icons, and service worker caching assets
  5. Online/offline indicator is visible to the user
**Plans**: TBD

Plans:
- [ ] 05-01: TBD
- [ ] 05-02: TBD
- [ ] 05-03: TBD

### Phase 6: Hardening
**Goal**: The application meets production-grade operational and accessibility standards
**Depends on**: Phase 5
**Requirements**: INFR-05, INFR-06, INFR-07
**Success Criteria** (what must be TRUE):
  1. PostgreSQL backups run daily (pg_dump), encrypted with GPG, and can be restored successfully
  2. Spring Boot Actuator health endpoint is accessible and logs are structured (JSON format)
  3. Application passes WCAG 2.2 AA audit on all user-facing pages (keyboard navigation, screen reader, contrast ratios)
**Plans**: TBD

Plans:
- [ ] 06-01: TBD
- [ ] 06-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 6/6 | Complete   | 2026-03-09 |
| 2. Transactions | 0/3 | Not started | - |
| 3. Budgets and Debts | 0/3 | Not started | - |
| 4. Bank Sync | 0/3 | Not started | - |
| 5. Dashboard and Mobile | 0/3 | Not started | - |
| 6. Hardening | 0/2 | Not started | - |
