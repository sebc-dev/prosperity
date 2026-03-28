# Pitfalls Research

**Domain:** Personal finance management (self-hosted, envelope budgeting, bank sync)
**Researched:** 2026-03-28
**Confidence:** HIGH (domain-specific, verified against Plaid docs and OSS project experience)

## Critical Pitfalls

### Pitfall 1: Envelope Budget Model Treated as Simple CRUD

**What goes wrong:**
The envelope budgeting domain is modeled as flat "category + amount" records, missing the complexity of allocation, rollover, overspend handling, and inter-envelope transfers. This leads to balance inconsistencies, especially when shared accounts have envelopes owned by different users. Firefly III users consistently report confusion between budgets, categories, bills, and tags because the domain model conflated concepts that should be separate.

**Why it happens:**
Envelope budgeting looks simple on the surface: put money in categories, spend against them. But the real complexity is in the edge cases: what happens when an envelope overspends? Does the deficit carry forward? Does it borrow from another envelope? What about refunds -- does a returned purchase restore the envelope balance? (Firefly III explicitly refuses to handle this case, frustrating users.) When envelopes are "per account" (as decided in PROJECT.md), you also need to handle the interaction between personal and shared account envelopes.

**How to avoid:**
- Model envelopes with explicit states: allocated, spent, remaining, rolled-over, overspent
- Define rollover as a first-class operation (configurable per envelope: carry forward or reset)
- Model refunds as envelope credits, not just transaction reversals
- Prototype the domain model with unit tests covering: allocation, spend, overspend, rollover month boundary, refund, inter-user visibility on shared accounts
- Keep envelopes and transaction categories as separate concepts (an envelope is a budget container, a category is a classification)

**Warning signs:**
- Envelope balance calculation requires ad-hoc SQL queries instead of deriving from domain events
- "Quick fix" flags like `is_overspent` boolean instead of computed state
- No tests for month-boundary rollover behavior
- Refund transactions have no relationship to the original envelope

**Phase to address:**
Domain modeling phase (before any persistence or UI). Must be validated with integration tests before building API endpoints.

---

### Pitfall 2: Plaid Pending-to-Posted Transaction Lifecycle Misunderstood

**What goes wrong:**
The app treats Plaid transactions as immutable records. In reality, pending transactions disappear and reappear as new posted transactions with different `transaction_id` values. If you store pending transactions with their original IDs and don't handle the `pending_transaction_id` linkage, you get duplicate transactions (one pending, one posted for the same purchase), phantom transactions (pending that never posted), and balance mismatches.

**Why it happens:**
Plaid does not model pending-to-posted as a state change. Instead, the pending transaction is *removed* and a new posted transaction is *added* with a `pending_transaction_id` field linking back. Some institutions (Capital One, USAA) don't provide pending data at all. Some posted transactions arrive with `pending_transaction_id: null` when Plaid fails to match. Amounts can change between pending and posted (e.g., restaurant tips added). Authorization holds (gas stations, hotels) create pending transactions that simply vanish without ever posting.

**How to avoid:**
- Use `/transactions/sync` (not `/transactions/get`) -- it provides `added`, `modified`, and `removed` arrays
- When processing sync results: apply removals first, then modifications, then additions
- Store Plaid's `transaction_id` as an external reference, not as your primary key
- When a posted transaction arrives with `pending_transaction_id`, find and replace (not duplicate) the pending record
- Handle `pending_transaction_id: null` gracefully -- treat the posted transaction as new
- Never compute balances from pending transactions alone
- Listen for webhooks: `SYNC_UPDATES_AVAILABLE`, `INITIAL_UPDATE`, `TRANSACTIONS_REMOVED`

**Warning signs:**
- Users report "duplicate" transactions in the UI
- Account balances don't match what the bank shows
- Pending transactions linger for weeks without resolving
- No webhook handler for `TRANSACTIONS_REMOVED`

**Phase to address:**
Bank sync / Plaid integration phase. Must be designed before any transaction import code is written.

---

### Pitfall 3: PSD2 Consent Expiry Ignored Until Users Lose Sync

**What goes wrong:**
In Europe (including France), PSD2 requires users to re-consent to bank data access. Currently this is every 180 days (extended from the original 90-day rule by EBA). If the app doesn't track consent expiration and proactively notify users, sync silently breaks. Users discover weeks later that their data is stale, with a gap of missing transactions that may be impossible to backfill.

**Why it happens:**
Developers build the initial Plaid Link flow (connect bank -> get transactions) and consider bank sync "done." The consent lifecycle is invisible in sandbox/development mode. The 180-day expiry feels distant during development and testing. Plaid sends a `PENDING_EXPIRATION` webhook 7 days before expiry, but if you don't handle it, nothing happens -- the Item just silently enters `ITEM_LOGIN_REQUIRED` error state.

**How to avoid:**
- Store `consent_expiration_time` from `/item/get` for every connected Item
- Implement `PENDING_EXPIRATION` webhook handler that triggers user notification
- Build "update mode" Link flow that re-authenticates the user when consent is about to expire
- Display consent status in the admin/settings UI (green/yellow/red based on days remaining)
- Implement a scheduled job that checks Items approaching expiration (don't rely solely on webhooks)
- Handle `ITEM_LOGIN_REQUIRED` error state with a clear UI flow to reconnect

**Warning signs:**
- No `consent_expiration_time` field stored in your Item/connection model
- No webhook endpoint for `PENDING_EXPIRATION`
- No UI to show connection health status
- Testing only in sandbox mode (sandbox Items don't expire)

**Phase to address:**
Bank sync phase. Consent management must be part of the initial Plaid integration, not added later.

---

### Pitfall 4: BFF Cookie Auth CSRF Token Regeneration Race Condition

**What goes wrong:**
Spring Security 6+ changed CSRF token behavior with `DeferredCsrfToken`. After login, the CSRF token cookie is cleared but a new one isn't immediately set in the response. The SPA makes a follow-up API call with the old (now invalid) CSRF token and gets a 403 Forbidden. Users see a "forbidden" error right after logging in successfully. This is a known issue (spring-security #12094, #12141, #13424).

**Why it happens:**
Spring Security 6+ defers CSRF token generation for performance. With `CookieCsrfTokenRepository`, the token cookie is cleared on authentication success, but the new token isn't generated until the next request that actually reads it. If the SPA makes an API call immediately after login (e.g., fetching dashboard data), the CSRF token cookie hasn't been set yet. This is especially tricky because it works fine with server-rendered forms but breaks with SPA + cookie-based CSRF.

**How to avoid:**
- After login response, have the SPA call a dedicated `/api/csrf` endpoint that forces token generation before making any state-changing requests
- Or configure `CsrfTokenRequestAttributeHandler` to eagerly generate the token (opt out of deferred behavior)
- Test the full login -> first API call flow in integration tests, not just login in isolation
- Use `SameSite=Strict` or `SameSite=Lax` on session cookies as defense-in-depth alongside CSRF tokens
- Consider Spring Security 7's defaults carefully -- they may change CSRF handling again

**Warning signs:**
- Intermittent 403 errors after login (works on retry)
- Login integration tests pass but end-to-end tests with the SPA fail
- No explicit CSRF configuration in SecurityFilterChain (relying on defaults)
- CSRF works in Postman but not from the Angular app

**Phase to address:**
Auth / security setup phase. Must be verified with end-to-end tests (not just backend unit tests).

---

### Pitfall 5: Shared Account Access Control Modeled at API Level Only

**What goes wrong:**
Access control for shared bank accounts is implemented as endpoint-level authorization checks (e.g., "can this user access GET /accounts/{id}?") rather than domain-level ownership. This creates data leaks: a user who shouldn't see a shared account's transactions can still see them through aggregate endpoints (dashboard totals, search results, budget summaries). Envelope budgets on shared accounts become inconsistent when two users allocate funds independently without visibility into each other's allocations.

**Why it happens:**
Developers implement access control as a filter on REST endpoints because it's the most visible entry point. But financial data flows through many paths: dashboard aggregations, budget calculations, transaction search, export, and reporting. If the domain model doesn't enforce ownership, every new feature must remember to filter by user permissions -- and inevitably one is missed.

**How to avoid:**
- Model account access as a domain concept: `AccountAccess(userId, accountId, role)` where role = OWNER | SHARED_FULL | SHARED_READ
- Enforce access at the repository/query level using Spring Data's `@Query` with user context, not just at the controller level
- For shared accounts, decide upfront: do both users see the same envelopes, or does each user have their own envelope view of the shared account? (PROJECT.md says "envelopes per account, parametrable" -- clarify this)
- Test with two-user scenarios from day one: User A creates envelope on shared account, User B should/shouldn't see it
- Aggregate queries (dashboard totals, budget summaries) must filter by accessible accounts

**Warning signs:**
- `@PreAuthorize` on controllers but no access filtering in service or repository layers
- No multi-user test scenarios in the test suite
- Dashboard shows data from accounts the user shouldn't see
- No explicit `AccountAccess` or similar join entity -- access is checked via user-account relationship only at the endpoint

**Phase to address:**
Account management phase (before envelopes or dashboard). Access model must exist before any feature builds on top of it.

---

### Pitfall 6: Transaction Reconciliation Between Manual Entry and Plaid Import Has No Matching Strategy

**What goes wrong:**
Users enter a transaction manually (e.g., cash payment, or to track before sync), then Plaid imports the same transaction. Without a reconciliation strategy, the transaction appears twice. Manually deleting duplicates is tedious and error-prone. Users stop trusting the app's balances and abandon it.

**Why it happens:**
Manual transactions and imported transactions live in different conceptual spaces during development. Manual entry is built first (or alongside), bank import is added later, and nobody designs the bridge between them. The "pointage" (reconciliation) feature in PROJECT.md is explicitly manual in v1, but without a clear data model for "this manual entry corresponds to this imported transaction," manual reconciliation is just visual -- it doesn't prevent double-counting in balance calculations.

**How to avoid:**
- Design transaction states from the start: `MANUAL_UNMATCHED`, `IMPORTED_UNMATCHED`, `MATCHED`, `RECONCILED`
- A "matched" transaction links a manual entry to an imported entry (one replaces the other for balance calculation, but both are retained for audit)
- Provide a reconciliation UI that shows unmatched manual entries alongside recent imports, with suggested matches (amount + date proximity)
- Even in v1 (manual pointage), the data model must support the match relationship -- don't just add a boolean `is_reconciled` flag
- Balance calculation must be aware of matching: a matched pair counts once, not twice

**Warning signs:**
- Transaction model has no `status` or `source` field
- No relationship table between manual and imported transactions
- Balance calculation sums all transactions regardless of matching state
- "Pointage" is implemented as a UI-only checkbox with no domain impact

**Phase to address:**
Transaction model design phase (before both manual entry and bank import are built).

---

### Pitfall 7: Money Amounts Stored or Calculated with Floating Point

**What goes wrong:**
Financial amounts are stored as `float` or `double` in the database or calculated with floating-point arithmetic in Java. This leads to rounding errors: 0.1 + 0.2 = 0.30000000000000004. Over thousands of transactions, cents drift. Envelope balances don't add up to the account balance. Users lose trust.

**Why it happens:**
It's the default numeric type in many contexts. JSON deserializes numbers as doubles. JavaScript (and by extension, some frontend frameworks) uses IEEE 754 doubles for all numbers. Database columns default to `NUMERIC` without precision specification.

**How to avoid:**
- Use `BigDecimal` everywhere in Java, never `double` or `float` for money
- PostgreSQL column type: `NUMERIC(15,2)` (or `NUMERIC(19,4)` if sub-cent precision needed for calculations)
- JSON serialization: serialize as string, not number, to avoid JavaScript precision loss
- Define a `Money` value object in the domain layer that wraps `BigDecimal` with currency
- Since the project is EUR-only, currency can be implicit, but the value object pattern still protects against floating-point leaks
- Frontend: use integer cents for all calculations, format to euros only for display

**Warning signs:**
- Any `double` or `float` field in a domain entity related to money
- Database column is `REAL` or `DOUBLE PRECISION` instead of `NUMERIC`
- JSON responses show amounts like `10.100000000000001`
- Balance discrepancies of 1 cent in aggregation queries

**Phase to address:**
Domain model / project setup phase. Must be decided before any entity is created.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip double-entry (single-entry ledger) | Simpler transaction model | Cannot track transfers between accounts accurately, no audit trail for balance discrepancies | Acceptable for v1 personal finance if transfers are modeled as linked transaction pairs |
| Store Plaid raw JSON as-is | Fast integration, no mapping | Schema changes when Plaid updates API, bloated database, can't query efficiently | Never for primary data; acceptable as an audit log alongside normalized data |
| Hardcode EUR currency | No currency handling complexity | Blocks multi-currency forever | Acceptable -- PROJECT.md explicitly scopes to EUR only |
| Envelope balance as cached column | Fast reads, no recalculation | Stale if any transaction update bypasses cache invalidation | Acceptable if recalculated on every write AND a nightly reconciliation job verifies |
| Single admin role (no granular permissions) | Simpler auth model | Can't differentiate "can view" from "can edit" on shared accounts | Acceptable for v1 couple use case, but model the access entity from start |

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Plaid Link | Opening Link without setting `country_codes: ["FR"]` and `language: "fr"` | Always specify country and language for EU institutions; FR institutions may not appear otherwise |
| Plaid Transactions | Using `/transactions/get` instead of `/transactions/sync` | `/transactions/sync` is the recommended approach; it handles pagination, provides added/modified/removed arrays, and supports cursor-based incremental sync |
| Plaid Webhooks | Not verifying webhook signatures | Plaid signs webhooks with JWK; always verify to prevent spoofed transaction injections |
| Plaid Sandbox | Testing only in sandbox and assuming production behaves the same | Sandbox doesn't simulate consent expiry, institution errors, or rate limiting; test in development environment with real (test) bank credentials |
| Plaid Items | Storing `access_token` in plaintext | Encrypt Plaid access tokens at rest; they provide full account access and never expire (unless revoked) |
| Plaid EU | Assuming all Plaid products available in France | Not all products are available in all EU countries; verify via `/institutions/get_by_id` that Transactions product is supported for SG and Banque Populaire specifically |

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Recalculating envelope balances from all transactions on every request | Dashboard loads slowly | Maintain a materialized balance per envelope, update on transaction write, reconcile nightly | 1000+ transactions per envelope (typical after 6-12 months of use) |
| Loading all transactions for a date range without pagination | Memory spikes, timeouts | Cursor-based pagination on transaction list endpoints; limit default page to 50 | 500+ transactions per month (typical for active household) |
| N+1 queries on transaction -> category -> envelope joins | API response time degrades linearly | Use `@EntityGraph` or explicit `JOIN FETCH` in JPA queries | 100+ transactions per page |
| Sync all Plaid Items sequentially | Sync takes minutes for multiple accounts | Parallelize with async jobs per Item; use Spring's `@Async` or a task queue | 3+ linked bank accounts |

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Plaid access tokens stored unencrypted | Full bank account access if DB is compromised | Encrypt at rest with application-level encryption (not just DB-level TDE) |
| Transaction amounts visible in server logs | Financial data leak via log files | Sanitize logging; never log transaction amounts, account numbers, or Plaid tokens |
| No rate limiting on Plaid Link creation | Attacker could exhaust Plaid API quota or create unauthorized bank connections | Rate limit Link token creation per user session; require re-authentication for new bank connections |
| Session cookies without `Secure` flag on self-hosted HTTP | Session hijacking on local network | Even self-hosted, use HTTPS via Caddy; set `Secure`, `HttpOnly`, `SameSite=Strict` on all auth cookies |
| Shared account data accessible via user enumeration | User A guesses User B's account ID and accesses their data | Use UUIDs (not sequential IDs) for account identifiers; enforce access checks at repository level |

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Showing pending transactions mixed with posted without visual distinction | Users see "wrong" amounts, lose trust | Clearly mark pending transactions with visual indicator; show "available" vs "posted" balance separately |
| Requiring category assignment for every transaction | Transaction import becomes a chore; users stop categorizing | Auto-assign Plaid's category as default; let users override; batch-categorize similar transactions |
| No visual feedback during bank sync | User thinks sync is broken, clicks repeatedly | Show sync progress/status; disable sync button during active sync; show last sync timestamp |
| Month-end envelope rollover happens silently | Users don't understand why their budget changed | Show a rollover summary at month boundary; notify when rollover occurs |
| Reconciliation UI shows all transactions unsorted | Finding matches is like searching a haystack | Sort unmatched transactions by date descending; group by similar amounts; highlight likely matches |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Bank sync:** Handles `SYNC_UPDATES_AVAILABLE` webhook but not `TRANSACTIONS_REMOVED` -- verify removed transactions are actually deleted/archived
- [ ] **Envelope budgets:** Rollover works for normal months but not tested for: first month (no previous balance), skip months (user didn't use app for 2 months), negative rollover (overspent last month)
- [ ] **Auth flow:** Login works but CSRF token not regenerated correctly after login -- verify with full SPA end-to-end test (not just Postman)
- [ ] **Shared accounts:** User A can see shared account but verify: can User A see User B's personal accounts? Test the negative case
- [ ] **Transaction import:** Initial Plaid sync imports transactions but doesn't handle: institutions that don't support pending, transactions with modified amounts, transactions that span page boundaries in sync cursor
- [ ] **Pointage/reconciliation:** Manual entry marked as "reconciled" but balance calculation still counts both manual and imported versions
- [ ] **Setup wizard:** Creates admin user but doesn't set up: CSRF token for first post-login request, default categories, initial Plaid Link prompt
- [ ] **Dashboard balances:** Shows current balance but doesn't account for: pending transactions, unreconciled duplicates, envelope allocations vs actual balance

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Floating-point money amounts in DB | HIGH | Write migration to convert columns to NUMERIC(15,2); audit and fix all rounding discrepancies; requires recalculating all derived balances |
| Duplicate transactions from Plaid sync | MEDIUM | Write dedup script matching on Plaid `transaction_id`; merge duplicates preserving user edits (categories, notes); recalculate balances |
| Consent expired, gap in transaction history | LOW-MEDIUM | Reconnect via update mode; use `/transactions/sync` to fetch missed transactions (Plaid retains data during expiry); verify no gap in date coverage |
| CSRF race condition in auth flow | LOW | Add `/api/csrf` endpoint; update Angular HTTP interceptor to fetch CSRF token after login before other requests |
| Access control leak on shared accounts | HIGH | Audit all queries and endpoints for missing access filters; add repository-level `@Query` constraints; write comprehensive multi-user integration tests |
| Envelope balance drift from missing rollover logic | MEDIUM | Write balance recalculation job; run across all envelopes; add monthly reconciliation check that compares computed vs stored balances |
| Reconciliation double-counting | MEDIUM | Add `match_group_id` to transaction model; write migration to link existing matched pairs; recalculate all account balances |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Envelope model too simple | Domain modeling (early) | Unit tests cover: allocate, spend, overspend, rollover, refund, shared account visibility |
| Plaid pending/posted lifecycle | Bank sync integration | Integration test simulates: pending added, pending removed, posted added with `pending_transaction_id`, posted added without match |
| PSD2 consent expiry | Bank sync integration | Store `consent_expiration_time`; webhook handler for `PENDING_EXPIRATION`; admin UI shows connection health |
| CSRF token race condition | Auth / security setup | End-to-end test: Angular login -> immediate API call -> no 403 |
| Shared account access leaks | Account management (before envelopes) | Multi-user integration tests: User A cannot see User B's personal data; User A can see shared account data |
| Reconciliation double-counting | Transaction model design | Balance calculation test: matched manual + imported pair counts once |
| Floating-point money | Project setup / domain model | Code review rule: no `double`/`float` for money; `BigDecimal` only; DB migration uses `NUMERIC(15,2)` |

## Sources

- [Plaid Transaction States Documentation](https://plaid.com/docs/transactions/transactions-data/)
- [Plaid Transaction Troubleshooting](https://plaid.com/docs/transactions/troubleshooting/)
- [Plaid Blog: Distributed Duplicate Detective](https://plaid.com/blog/distributed-duplicate-detective/)
- [Plaid Blog: How Plaid Reconciles Pending and Posted Transactions](https://plaid.com/blog/finding-the-right-fit-how-plaid-reconciles-pending-and-posted-transactions/)
- [Plaid Blog: 90-Day Reauthentication Misconceptions](https://plaid.com/blog/misconceptions-of-authentication-and-authorisation-why-90-day/)
- [Plaid Blog: EU Reauth Update (180 Days)](https://plaid.com/blog/eu-reauth-update/)
- [Plaid European Coverage Documentation](https://plaid.com/docs/institutions/europe/)
- [Plaid Link Update Mode](https://plaid.com/docs/link/update-mode/)
- [Spring Security CSRF Issue #12094](https://github.com/spring-projects/spring-security/issues/12094)
- [Spring Security CSRF Issue #12141](https://github.com/spring-projects/spring-security/issues/12141)
- [Spring Security CSRF Issue #13424](https://github.com/spring-projects/spring-security/issues/13424)
- [Firefly III Pain Points Issue #4040](https://github.com/firefly-iii/firefly-iii/issues/4040)
- [Firefly III Budget Documentation](https://docs.firefly-iii.org/explanation/financial-concepts/budgets/)
- [Actual Budget Envelope Budgeting Docs](https://actualbudget.org/docs/getting-started/envelope-budgeting/)

---
*Pitfalls research for: Prosperity -- self-hosted personal finance management*
*Researched: 2026-03-28*
