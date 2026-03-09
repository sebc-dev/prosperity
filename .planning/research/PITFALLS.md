# Pitfalls Research

**Domain:** Self-hosted personal finance app for couples (PWA offline-first, Plaid bank sync, internal debt tracking)
**Researched:** 2026-03-09
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: Floating-Point Money Arithmetic

**What goes wrong:**
Using `double` or `float` for financial calculations causes silent rounding errors. `0.1 + 0.2` yields `0.30000000000000004`. Over thousands of transactions, balances drift by cents or euros. Debt tracking between partners shows incorrect "who owes whom" amounts, causing exactly the disputes the app is designed to prevent.

**Why it happens:**
Java's `double` type cannot represent decimal fractions exactly in IEEE 754 binary. Developers use `double` by default because it is simpler, and errors are invisible until balances are compared against bank statements.

**How to avoid:**
- Use `BigDecimal` everywhere for monetary values. Never `double` or `float`.
- Always use `new BigDecimal("0.10")` (String constructor), never `new BigDecimal(0.10)` (double constructor introduces the very imprecision you are avoiding).
- Define a `Money` value object (record) wrapping `BigDecimal` + `Currency`, enforcing scale=2 and `RoundingMode.HALF_EVEN` (banker's rounding).
- PostgreSQL columns: `NUMERIC(15,2)` -- explicit precision and scale.
- Round only at the final display/persistence step, never in intermediate calculations.
- Consider the Moneta library (JSR 354 implementation) if custom Money class becomes complex.

**Warning signs:**
- Any `double` or `float` field in entity/DTO classes representing money
- Missing `RoundingMode` in any `BigDecimal` division or multiplication
- Balance reconciliation tests off by 0.01

**Phase to address:**
Phase 1 (Infrastructure & Foundations) -- establish the Money value object and DB column conventions before any transaction code is written.

---

### Pitfall 2: Plaid EU/France Re-Authentication and Coverage Gaps

**What goes wrong:**
Under PSD2 regulation, Plaid access tokens in Europe expire after 180 days. Users must re-authenticate with their bank through Strong Customer Authentication (SCA). If the app does not handle this gracefully, bank sync silently stops working. The couple thinks transactions are being imported but they are not, leading to missing data and broken budgets.

Additionally, not all French banks are covered by Plaid, and not all Plaid products (Transactions, Auth, Balance) are available at every European institution. The app may work perfectly in sandbox but fail when connecting to actual French banks.

**Why it happens:**
Developers test exclusively in Plaid's sandbox (US-centric, no re-auth flows). They assume tokens are permanent like US integrations. European coverage is not uniform and changes quarterly.

**How to avoid:**
- Store token expiry date. Proactively notify users 7-14 days before re-authentication is needed.
- Implement a clear re-authentication flow: detect `PENDING_EXPIRATION` webhook, show in-app banner, guide user through Plaid Link update mode.
- Use `/institutions/get` at setup to verify the user's specific French bank supports the `transactions` product before connecting.
- Always maintain manual transaction entry as a first-class feature, not a fallback afterthought. The app must be fully usable without Plaid.
- Use Plaid's `/transactions/sync` endpoint (not the older `/transactions/get`) for simpler state management.
- Handle webhooks idempotently -- Plaid may send duplicates or out-of-order.

**Warning signs:**
- No webhook handler for `PENDING_EXPIRATION` or `CONSENT_EXPIRING`
- No UI for re-authentication state
- Manual entry feels like a second-class citizen in the UX
- Testing only with sandbox institutions

**Phase to address:**
Phase with Plaid integration -- but manual transaction entry must be built and polished first (separate earlier phase). Plaid is an enhancement, not a prerequisite.

---

### Pitfall 3: Offline-First Sync Conflict Explosion

**What goes wrong:**
Two users (the couple) both add transactions offline. When both devices sync, conflicts arise: duplicate transactions, inconsistent debt calculations, budget amounts that do not add up. The conflict resolution UI becomes a constant nuisance, eroding trust in the app. Worse, silent last-write-wins causes data loss.

**Why it happens:**
Offline-first is architecturally hard. Most tutorials cover single-user offline caching, not multi-user concurrent offline edits. IndexedDB has no built-in conflict resolution. The "happy path" demo works, but real-world usage (both partners entering expenses at the grocery store) creates edge cases immediately.

**How to avoid:**
- Assign UUIDs client-side for all new entities (transactions, debts). Server never generates IDs for offline-created data. This prevents duplicate creation on retry.
- Implement an operation queue (not state sync). Each offline action is an immutable operation (e.g., "create transaction X", "mark debt Y as paid") queued in IndexedDB and replayed on reconnect.
- Server is the source of truth. After sync, client fetches canonical state.
- Conflict detection for the couple: same amount (+/- 10%), same timeframe (5 min window), different devices -- flag as potential duplicate rather than auto-merging.
- Keep conflict resolution UI dead simple: side-by-side comparison, "Keep A / Keep B / Keep Both" -- nothing more.
- Limit what can be done offline: creating transactions YES, editing budgets or deleting accounts NO (require online).

**Warning signs:**
- Auto-increment IDs on the server for entities that can be created offline
- No operation queue -- trying to sync full IndexedDB state
- Conflict resolution UI has more than 3 options
- No integration test simulating two devices creating transactions simultaneously offline

**Phase to address:**
PWA/Offline phase -- but the decision to use UUIDs and operation queues must be made in Phase 1 (data model design). Retrofitting is extremely painful.

---

### Pitfall 4: Scope Creep Leading to Project Abandonment

**What goes wrong:**
The MVP scope already includes: multi-user auth, Plaid integration, PWA offline-first with conflict resolution, budgeting (two modes), internal debt tracking, dashboard with charts, accessibility WCAG 2.2 AA, full CI/CD pipeline with SonarQube/SpotBugs/PIT/ArchUnit, Docker deployment. This is an enormous scope for a solo developer learning two new frameworks simultaneously (Spring Boot and Svelte 5). The project stalls at 60% complete and joins the graveyard of abandoned side projects.

**Why it happens:**
Every feature individually feels essential. The PRD was written aspirationally. Learning two new stacks (Spring Boot + Svelte 5) multiplies development time by 2-3x versus a familiar stack. AI-assisted development helps with boilerplate but not with architectural decisions or debugging subtle framework interactions.

**How to avoid:**
- Ruthlessly phase the MVP. True MVP = auth + manual transactions + basic dashboard + Docker. That is it. No Plaid, no PWA offline, no budgets, no debt tracking in v0.1.
- Timebox each phase to 2-4 weeks. If a phase is not done in 4 weeks, ship what works and move on.
- The "daily usage for 3 months" success metric starts counting from v0.1, not from "feature complete MVP."
- CI/CD quality gates: start with build + test + lint only. Add SonarQube, PIT, SpotBugs incrementally as phases complete (the PRD already suggests this -- follow through).
- Track velocity honestly. If Phase 1 takes 3x the estimate, re-scope subsequent phases.

**Warning signs:**
- Phase 1 (infrastructure) takes more than 3 weeks
- Adding "just one more thing" to the current phase before shipping
- Not using the app yourself within the first month of development
- Perfectionism on code quality tooling before core features work

**Phase to address:**
Pre-Phase 1 (planning) -- define a v0.1 that is shippable in 4-6 weeks. Every subsequent phase adds one major capability.

---

### Pitfall 5: JWT Token Storage and Security in a PWA Context

**What goes wrong:**
Storing JWT access tokens in `localStorage` exposes them to XSS attacks. Storing refresh tokens in `localStorage` is even worse -- a single XSS vulnerability gives an attacker persistent access. In a finance app, this means full access to all financial data. Alternatively, using HttpOnly cookies with a SvelteKit frontend served from a different origin than the Spring Boot API creates CORS/cookie issues that are painful to debug.

**Why it happens:**
Most JWT tutorials store tokens in `localStorage` because it is simple. The SvelteKit (Node container) + Spring Boot (Java container) architecture means two different origins, making HttpOnly cookie auth complicated. Developers defer security to "later" and ship insecure token storage.

**How to avoid:**
- SvelteKit server-side handles auth. The browser never sees the JWT directly.
- Flow: Browser -> SvelteKit server (session cookie, HttpOnly, Secure, SameSite=Strict) -> SvelteKit server -> Spring Boot API (JWT in Authorization header, server-to-server).
- The SvelteKit server acts as a BFF (Backend For Frontend). It holds the JWT/refresh token in server-side session or encrypted cookie, never exposing it to client-side JavaScript.
- For offline PWA: store a limited offline session token in IndexedDB (not the API JWT). This token only unlocks read access to cached data. Full write sync requires online re-authentication.
- Implement refresh token rotation: each refresh issues a new refresh token and invalidates the old one. Detect reuse (attacker + legitimate user both try to use same refresh token) and invalidate the entire session.

**Warning signs:**
- `localStorage.setItem('token', jwt)` anywhere in frontend code
- JWT visible in browser DevTools Application tab
- No BFF pattern -- frontend calls Spring Boot API directly from the browser with JWT in headers
- Refresh token with expiry > 7 days without rotation

**Phase to address:**
Phase 1 (Auth & Security) -- this architecture must be decided before any API call is made from the frontend.

---

### Pitfall 6: Database Schema Rigidity from Day One

**What goes wrong:**
The initial Liquibase schema is designed to perfectly match the final PRD features (budgets with two modes, debt tracking with settlements, Plaid token storage, conflict resolution metadata). When features evolve during development (they always do), schema changes require complex Liquibase migrations that break existing data. Worse, developers modify already-applied changesets, causing Liquibase checksum errors that block application startup.

**Why it happens:**
Temptation to design the "perfect" schema upfront based on the PRD. Liquibase enforces immutability of applied changesets (by design, for safety), but developers unfamiliar with this try to edit existing changesets instead of adding new ones.

**How to avoid:**
- Start with minimal schema: `users`, `accounts`, `transactions`, `categories`. Add tables for budgets, debts, Plaid tokens only when those features are being built.
- Never modify an applied changeset. Always add a new changeset for schema changes.
- Use meaningful changeset IDs (e.g., `001-create-users`, `002-create-accounts`) not auto-generated ones.
- Write rollback blocks for every changeset from the start. Rollbacks are painful to add retroactively.
- One changeset per logical change (not one giant changeset per phase).
- Test migrations against a clone of production data before deploying, even if "production" is just your personal server.

**Warning signs:**
- Liquibase checksum validation errors on startup
- Schema has tables for features not yet implemented
- Changesets without rollback blocks
- Single large changeset files

**Phase to address:**
Phase 1 (Infrastructure) -- establish Liquibase conventions. Each subsequent phase adds only the schema it needs.

---

### Pitfall 7: Internal Debt Calculation Edge Cases

**What goes wrong:**
The debt tracking system produces incorrect balances because edge cases are not handled: partial payments, split transactions where one partner pays for both but the split is not 50/50, refunds on shared expenses, transactions on shared accounts that should not create debt, and currency rounding in debt calculations. The couple loses trust in the "who owes whom" number -- the core value proposition of the app.

**Why it happens:**
Debt tracking seems simple (sum of advances minus sum of repayments) but real-life financial interactions are messy. The happy path works, but edge cases accumulate and each one requires specific business logic.

**How to avoid:**
- Define clear business rules upfront: Does a transaction on a shared account create debt? (Probably not -- it is shared money.) Does a personal purchase paid from a shared account create debt? (Yes, to the shared pool.) What about groceries where one person buys something personal mixed in?
- Model debt as a ledger of operations, not a running balance. Each operation (advance, repayment, adjustment) is immutable. The balance is always computed from the full ledger.
- Allow manual debt adjustments ("We agreed to call it even") with audit trail.
- Provide a "debt history" view so both partners can verify how the balance was calculated.
- Write extensive unit tests for edge cases before building the UI.

**Warning signs:**
- Debt balance stored as a single mutable field rather than computed from a ledger
- No test cases for: partial repayment, refund on shared expense, manual adjustment, 60/40 splits
- Both partners get different debt amounts due to rounding

**Phase to address:**
Phase with debt tracking feature -- but business rules must be defined during planning, not discovered during implementation.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip offline-first, add later | Ship faster, simpler architecture | Retrofitting offline requires rewriting data layer, ID generation, and sync logic | Acceptable for v0.1 if you design for it (UUIDs, operation queue interface) even if not implemented |
| Use `double` for money in early prototyping | Faster to write, no BigDecimal ceremony | Silent precision errors compound; migration requires touching every entity, DTO, and query | Never -- use BigDecimal from day one, the cost is trivial upfront |
| Store Plaid tokens unencrypted in dev | Faster development cycle | Habit carries to production; tokens grant bank access | Only in Plaid sandbox (sandbox tokens are fake); encrypt from day one in any real environment |
| Skip Liquibase rollbacks | Write changesets faster | Cannot safely roll back failed deployments; stuck with broken schema | Never -- rollbacks take 2 minutes to write and save hours in recovery |
| Single monolithic SvelteKit load function | Quick to get data flowing | Load functions become slow, hard to cache, hard to test | Only for initial prototype; refactor before second feature uses same pattern |
| Hardcode budget calculation logic in SQL | Fast, single query for dashboard | Business logic split between Java and SQL; hard to test, hard to change | Acceptable for read-only dashboard aggregations; mutations always in Java |

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Plaid `/transactions/sync` | Using the older `/transactions/get` endpoint which requires manual pagination and date management | Use `/transactions/sync` with cursor-based pagination; listen for `SYNC_UPDATES_AVAILABLE` webhook |
| Plaid webhooks | Processing webhooks synchronously, causing timeout (Plaid expects response in 10s) | Write webhook payload to a queue/table immediately, process asynchronously; return 200 within seconds |
| Plaid webhooks | Assuming webhooks arrive exactly once and in order | Design idempotent handlers; use webhook `item_id` + `webhook_type` + `webhook_code` for deduplication |
| Plaid EU tokens | Treating access tokens as permanent (works in US sandbox) | Store consent expiry, handle `PENDING_EXPIRATION` webhook, implement re-auth flow via Plaid Link update mode |
| Plaid currency | Assuming all amounts are in euros with 2 decimal places | Plaid returns ISO currency codes and amounts may have >2 decimal places (crypto); normalize on receipt |
| Plaid sandbox vs production | Testing only with sandbox institutions which always succeed | Test error flows: `ITEM_LOGIN_REQUIRED`, `INSTITUTION_NOT_RESPONDING`, `TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION` |

## Performance Traps

Patterns that work at small scale but fail as data grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Loading all transactions for budget calculation | Dashboard loads in <100ms with 50 transactions | Pre-compute monthly aggregates in a `budget_summary` table, updated on transaction create/update/delete | >5,000 transactions (year 2 of daily use for a couple) |
| No pagination on transaction history | Works fine during development | Implement cursor-based pagination from day one; never load unbounded lists | >500 transactions per account |
| IndexedDB full table scans | Offline mode slows down imperceptibly at first | Create proper IndexedDB indexes on `date`, `accountId`, `syncStatus` | >2,000 cached transactions on mobile |
| N+1 queries on dashboard (account -> transactions -> category for each) | Invisible with 2 accounts | Use `@EntityGraph` or explicit `JOIN FETCH` in repository queries; test with 10 accounts and 1000 transactions | >5 accounts with >200 transactions each |
| Service Worker cache growing unbounded | Works for months, then PWA storage quota exceeded (Safari: 50MB limit) | Implement cache eviction: keep last 30 days of transactions in cache, purge older; track cache size | ~6 months of cached API responses on iOS Safari |

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Plaid access tokens stored in plaintext in DB | Anyone with DB access (backup theft, SQL injection) can pull live bank transaction data | AES-256 encrypt tokens at rest; encryption key in environment variable, not in codebase or DB |
| Account permission bypass: shared account logic relies on frontend hiding UI | Partner A can access Partner B's personal account via direct API call | `@PreAuthorize` on every endpoint checking account ownership; integration tests verifying 403 on unauthorized access |
| Debt settlement amount not validated server-side | Malicious or buggy client could settle debts with incorrect amounts | Server recomputes debt balance before accepting settlement; reject if client amount differs |
| Audit log gaps on financial mutations | Cannot trace who modified what, when -- critical for trust between partners | Log every create/update/delete on transactions, debts, budgets with user ID, timestamp, old/new values |
| Backup files unencrypted | `pg_dump` output contains all financial data in plaintext; if backup storage is compromised, all data is exposed | GPG-encrypt backups (PRD already specifies this -- ensure it is actually implemented and tested) |
| CORS misconfiguration allowing any origin | XSS on any site could make authenticated requests to the API | Whitelist only the SvelteKit origin; reject all others; test with `curl` from unauthorized origin |

## UX Pitfalls

Common user experience mistakes in personal finance apps.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Requiring category for every transaction at entry time | Slows down quick-add to >3 taps; partner stops entering transactions | Allow "Uncategorized" by default; batch-categorize later from desktop; suggest categories based on merchant name |
| Showing sync conflicts as technical errors | Non-technical partner feels app is broken, stops using it | Show conflicts as friendly questions: "Did you both buy groceries today? Tap to review" with clear visual diff |
| Dashboard information overload | Too many numbers, charts, widgets; non-technical partner cannot find what matters | Default dashboard: 3 things only -- total balance, budget status (green/yellow/red), debt summary. Progressive disclosure for details |
| Debt balance shown without context | Partner sees "-45 EUR" but does not know if that is recent or accumulated over months | Always show debt with recent history: "You owe 45 EUR (3 advances this week)" with link to full ledger |
| Forcing desktop setup before mobile use | Non-technical partner cannot start using the app until admin completes setup on desktop | Pre-configure sensible defaults (common categories, default currency); partner can start entering transactions immediately after login, even before Plaid setup |
| No positive reinforcement | Finance apps feel punishing (over budget, debt owed) | Show wins: "Budget on track this month", "Debt settled -- you're even!" -- especially visible to the non-technical partner |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Authentication:** Login works but refresh token rotation is not implemented -- sessions break after access token expires (15 min) or refresh tokens can be reused after theft
- [ ] **Plaid integration:** Sandbox works but no error handling for `ITEM_LOGIN_REQUIRED`, institution downtime, or EU re-authentication expiry
- [ ] **Offline mode:** Transactions save to IndexedDB but no sync queue, no conflict detection, no retry on failure -- data is silently lost on reconnect
- [ ] **Budget tracking:** Monthly totals calculate correctly but do not handle mid-month category changes, budget rollover, or transactions that span midnight in different timezones
- [ ] **Debt tracking:** Simple advances work but partial repayments, refunds on shared expenses, and manual adjustments are not handled
- [ ] **Dashboard:** Looks good with test data but N+1 queries make it slow with real data volume; no loading states, no error states, no empty states
- [ ] **Docker deployment:** `docker-compose up` works locally but missing health checks, restart policies, volume mounts for persistence, and `.env` management for secrets
- [ ] **Accessibility:** Semantic HTML in place but no keyboard navigation testing, no screen reader testing, no focus management on route changes in SvelteKit
- [ ] **Backup:** `pg_dump` script exists but never tested a restore; backup encryption not verified; no monitoring for backup failures

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Floating-point money (used `double`) | HIGH | Create BigDecimal Money VO; migrate all entities/DTOs; write Liquibase migration to recast columns; re-verify all financial calculations; recalculate all balances from transaction ledger |
| Plaid token expired silently | LOW | Detect via failed sync; trigger re-auth flow; no data loss (Plaid retains history); re-sync from last cursor |
| Offline sync data loss | HIGH | If operation queue was not implemented, lost transactions cannot be recovered; must rebuild from bank import + user memory; implement queue and UUID generation before next offline use |
| Scope creep / burnout | MEDIUM | Cut scope to what is working today; deploy it; use it daily; rebuild motivation from actual usage; defer remaining features indefinitely |
| Schema migration mess | MEDIUM | Export all data as JSON; drop and recreate schema with clean Liquibase changelog; re-import data; painful but possible for 2 users |
| JWT in localStorage (XSS vulnerability) | HIGH | Rotate all tokens immediately; implement BFF pattern in SvelteKit; audit for any token exfiltration in logs; reset Plaid tokens as precaution |
| Incorrect debt balances | MEDIUM | Rebuild debt ledger from transaction history; both partners manually verify; add audit trail and reconciliation tests |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Floating-point money | Phase 1: Infrastructure | Code review: zero `double`/`float` in money contexts; ArchUnit rule banning `double` fields in `*Transaction*`, `*Budget*`, `*Debt*` classes |
| Plaid EU re-auth | Plaid Integration Phase | Integration test simulating `PENDING_EXPIRATION` webhook; manual test with real French bank account |
| Offline sync conflicts | Phase 1 (design) + PWA Phase (implementation) | Integration test: two clients create transactions offline, sync, verify no data loss and conflicts detected |
| Scope creep | Pre-Phase 1 (planning) | Deployed and personally used within 6 weeks of starting development |
| JWT security | Phase 1: Auth | Penetration test: verify JWT not accessible via `document.cookie` or `localStorage` in browser console |
| Schema rigidity | Phase 1: Infrastructure | Every Liquibase changeset has a rollback block; no tables for unbuilt features |
| Debt edge cases | Debt Tracking Phase | Unit tests covering: partial repayment, refund, manual adjustment, 60/40 split, zero-balance settlement |
| Plaid webhook reliability | Plaid Integration Phase | Load test: send 100 duplicate webhooks; verify no duplicate transactions created |
| Dashboard performance | Dashboard Phase | Performance test with 10,000 transactions; dashboard loads in <500ms |
| PWA cache growth | PWA Phase | Test on iOS Safari: verify cache eviction after simulated 6 months of data |

## Sources

- [Plaid European Coverage Documentation](https://plaid.com/docs/institutions/europe/)
- [Plaid EU Re-Authentication Update (180 days)](https://plaid.com/blog/eu-reauth-update/)
- [Plaid Transactions Webhooks](https://plaid.com/docs/transactions/webhooks/)
- [Plaid Transactions Sync Migration Guide](https://plaid.com/docs/transactions/sync-migration/)
- [Plaid Error Documentation](https://plaid.com/docs/errors/)
- [Java BigDecimal Best Practices for Financial Calculations](https://dev.to/luke_tong_d4f228249f32d86/beyond-double-essential-bigdecimal-practices-for-accurate-financial-calculations-52m1)
- [Mastering Monetary Operations in Java (Altimetrik)](https://www.altimetrik.com/blog/modeling-money-in-java-pitfalls-solutions)
- [Rounding Numbers in the Financial Domain (Founding Minds)](https://www.foundingminds.com/rounding-numbers-in-the-financial-domain/)
- [Data Synchronization in PWAs: Offline-First Strategies](https://gtcsys.com/comprehensive-faqs-guide-data-synchronization-in-pwas-offline-first-strategies-and-conflict-resolution/)
- [Offline-First Frontend Apps in 2025 (LogRocket)](https://blog.logrocket.com/offline-first-frontend-apps-2025-indexeddb-sqlite/)
- [SvelteKit Service Workers Documentation](https://kit.svelte.dev/docs/service-workers)
- [Spring Boot JWT Refresh Token Rotation (NashTech)](https://blog.nashtechglobal.com/jwt-expiration-refresh-tokens-and-security-best-practices-with-spring-boot/)
- [Liquibase with Spring Boot (Reflectoring)](https://reflectoring.io/database-migration-spring-boot-liquibase/)
- [How to Actually Finish Your Side Projects (Super Productivity)](https://super-productivity.com/blog/finish-side-projects-developer-guide/)
- [Scope Creep: The Silent Killer of Solo Development (Wayline)](https://www.wayline.io/blog/scope-creep-solo-indie-game-development)
- [Firefly III Pain Points (GitHub Issue #4040)](https://github.com/firefly-iii/firefly-iii/issues/4040)
- [Firefly III Missing Features Documentation](https://docs.firefly-iii.org/explanation/more-information/what-its-not/)
- [Shopify: 8 Tips for Dealing with Hanging Pennies](https://shopify.engineering/eight-tips-for-hanging-pennies)
- [Offline Data Best Practices (web.dev)](https://web.dev/learn/pwa/offline-data/)

---
*Pitfalls research for: Self-hosted personal finance app for couples*
*Researched: 2026-03-09*
