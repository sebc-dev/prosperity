# Requirements: Prosperity

**Defined:** 2026-03-09
**Core Value:** Le couple dispose d'une vision financière claire, partagée et actualisée — avec un suivi automatique de qui doit combien à qui.

## v1 Requirements

### Authentication

- [ ] **AUTH-01**: User can log in with email and password
- [ ] **AUTH-02**: User session persists via JWT + Refresh Tokens with automatic rotation
- [ ] **AUTH-03**: Two roles enforced: Admin (config, Plaid, system) and Standard (daily use)
- [ ] **AUTH-04**: User can update profile (display name)
- [ ] **AUTH-05**: User can set preferences (theme light/dark, default currency, favorite categories)

### Accounts

- [ ] **ACCT-01**: User can create bank accounts as Personal or Shared
- [ ] **ACCT-02**: Personal accounts visible only to owner
- [ ] **ACCT-03**: Shared accounts accessible by both users
- [ ] **ACCT-04**: Admin can connect bank accounts via Plaid Link
- [ ] **ACCT-05**: Transactions imported automatically from Plaid (source: IMPORTED)
- [ ] **ACCT-06**: Plaid tokens encrypted AES-256 at rest
- [ ] **ACCT-07**: Graceful handling of Plaid errors (token expiry, institution down, PSD2 re-auth)

### Transactions

- [ ] **TXNS-01**: User can create manual entries as forecasted transactions (source: MANUAL, status: FORECAST)
- [ ] **TXNS-02**: User can mark manual entries as recurring (monthly, with day-of-month)
- [ ] **TXNS-03**: Recurring entries generated automatically at start of each month
- [ ] **TXNS-04**: User can edit and delete own manual entries
- [ ] **TXNS-05**: Imported transactions arrive automatically via Plaid (source: IMPORTED, status: STANDALONE)
- [ ] **TXNS-06**: User can reconcile (pointer) an imported transaction with a manual entry — both become RECONCILED
- [ ] **TXNS-07**: System suggests reconciliation matches (same amount +/- tolerance, close dates)
- [ ] **TXNS-08**: Unreconciled manual entries remain visible as expected future spending
- [ ] **TXNS-09**: Account displays dual balance: real (bank) and projected (real + unreconciled forecasts)
- [ ] **TXNS-10**: User can categorize transactions (default categories + custom)
- [ ] **TXNS-11**: User can view transaction history with filters (date, category, account, status: forecast/reconciled/imported)
- [ ] **TXNS-12**: Quick-add mobile: 3 taps max (amount, favorite category, confirm)

### Budgets

- [ ] **BUDG-01**: User can create monthly budgets by category
- [ ] **BUDG-02**: Budgets support envelope mode (spend until empty) and goal mode (savings target)
- [ ] **BUDG-03**: Visual progress tracking with gauges
- [ ] **BUDG-04**: Progressive in-app alerts at 75%, 90%, 100% of budget
- [ ] **BUDG-05**: Budget templates for quick setup (groceries, transport, leisure, etc.)

### Debts

- [ ] **DEBT-01**: User can mark transaction as advance ("paid by X for the couple")
- [ ] **DEBT-02**: System calculates net balance between the two users automatically
- [ ] **DEBT-03**: Dashboard widget shows debt balance permanently

### Dashboard

- [ ] **DASH-01**: Account balances displayed: real (bank) and projected (with unreconciled forecasts)
- [ ] **DASH-02**: Budget status with visual gauges (spent vs allocated vs remaining)
- [ ] **DASH-03**: 5 most recent transactions (with source/status indicators)
- [ ] **DASH-04**: Debt balance widget with net amount
- [ ] **DASH-05**: Responsive layout (mobile + desktop)

### PWA

- [ ] **PWA-01**: App installable as PWA (manifest, icons, service worker for asset caching)
- [ ] **PWA-02**: Mobile-responsive design (mobile-first for entry, desktop for analysis)
- [ ] **PWA-03**: Online/offline indicator

### Infrastructure

- [ ] **INFR-01**: Docker Compose deployment (PostgreSQL + Spring Boot API + SvelteKit web)
- [ ] **INFR-02**: CI/CD pipeline: build, tests, lint on push (advanced tools added progressively)
- [ ] **INFR-03**: Security headers (CSP, HSTS, X-Frame-Options), HTTPS via Caddy
- [ ] **INFR-04**: Passwords bcrypted (12 rounds), OWASP Top 10 compliance
- [ ] **INFR-05**: PostgreSQL backup automated (pg_dump daily, GPG encrypted)
- [ ] **INFR-06**: Spring Boot Actuator health endpoint + structured logs
- [ ] **INFR-07**: Accessibility WCAG 2.2 AA

## v2 Requirements

### Debts (deferred)

- **DEBT-04**: Settlement suggestions (single transfer to balance debts)
- **DEBT-05**: History of advances and repayments

### Data

- **DATA-01**: Full data export (JSON/CSV)

### PWA Offline

- **PWA-04**: IndexedDB for offline transaction storage
- **PWA-05**: Sync queue with retry on reconnection
- **PWA-06**: Conflict resolution UI (side-by-side comparison)
- **PWA-07**: Background Sync API

### AI / MCP

- **AI-01**: MCP server for automated spending analysis
- **AI-02**: AI auto-categorization of transactions
- **AI-03**: Personalized monthly financial insights

### Notifications

- **NOTF-01**: Push/email budget alerts
- **NOTF-02**: Debt reminders

## Out of Scope

| Feature | Reason |
|---------|--------|
| Investment / net worth tracking | Different product — massive scope expansion, requires market data feeds |
| Multi-currency support | Adds significant complexity; single configurable currency sufficient |
| More than 2 users | Architecture supports 10, but MVP is couple-only |
| Real-time sync (WebSocket) | 2 users don't justify the complexity; poll-based refresh sufficient |
| Receipt scanning / image attachments | Storage + camera integration not worth the cost at MVP |
| Granular RBAC permissions | 2 users need Admin/Standard only, not enterprise RBAC |
| In-app chat between partners | Anti-feature for a couple living together |
| Redis | Cache en mémoire Spring suffit pour 2 utilisateurs |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUTH-01 | Phase 1 | Pending |
| AUTH-02 | Phase 1 | Pending |
| AUTH-03 | Phase 1 | Pending |
| AUTH-04 | Phase 1 | Pending |
| AUTH-05 | Phase 1 | Pending |
| ACCT-01 | Phase 1 | Pending |
| ACCT-02 | Phase 1 | Pending |
| ACCT-03 | Phase 1 | Pending |
| ACCT-04 | Phase 4 | Pending |
| ACCT-05 | Phase 4 | Pending |
| ACCT-06 | Phase 4 | Pending |
| ACCT-07 | Phase 4 | Pending |
| TXNS-01 | Phase 2 | Pending |
| TXNS-02 | Phase 2 | Pending |
| TXNS-03 | Phase 2 | Pending |
| TXNS-04 | Phase 2 | Pending |
| TXNS-05 | Phase 4 | Pending |
| TXNS-06 | Phase 4 | Pending |
| TXNS-07 | Phase 4 | Pending |
| TXNS-08 | Phase 2 | Pending |
| TXNS-09 | Phase 2 | Pending |
| TXNS-10 | Phase 2 | Pending |
| TXNS-11 | Phase 2 | Pending |
| TXNS-12 | Phase 5 | Pending |
| BUDG-01 | Phase 3 | Pending |
| BUDG-02 | Phase 3 | Pending |
| BUDG-03 | Phase 3 | Pending |
| BUDG-04 | Phase 3 | Pending |
| BUDG-05 | Phase 3 | Pending |
| DEBT-01 | Phase 3 | Pending |
| DEBT-02 | Phase 3 | Pending |
| DEBT-03 | Phase 3 | Pending |
| DASH-01 | Phase 5 | Pending |
| DASH-02 | Phase 5 | Pending |
| DASH-03 | Phase 5 | Pending |
| DASH-04 | Phase 5 | Pending |
| DASH-05 | Phase 5 | Pending |
| PWA-01 | Phase 5 | Pending |
| PWA-02 | Phase 5 | Pending |
| PWA-03 | Phase 5 | Pending |
| INFR-01 | Phase 1 | Pending |
| INFR-02 | Phase 1 | Pending |
| INFR-03 | Phase 1 | Pending |
| INFR-04 | Phase 1 | Pending |
| INFR-05 | Phase 6 | Pending |
| INFR-06 | Phase 6 | Pending |
| INFR-07 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 42 total
- Mapped to phases: 42
- Unmapped: 0

---
*Requirements defined: 2026-03-09*
*Last updated: 2026-03-09 after roadmap creation*
