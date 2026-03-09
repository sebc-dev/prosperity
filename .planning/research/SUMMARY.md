# Project Research Summary

**Project:** Prosperity
**Domain:** Self-hosted personal finance web app for couples
**Researched:** 2026-03-09
**Confidence:** MEDIUM-HIGH

## Executive Summary

Prosperity is a self-hosted personal finance app designed for couples, combining bank sync (Plaid), offline-first PWA, internal debt tracking, and budgeting into a single product. No existing solution covers this exact combination: Firefly III is self-hosted but has no real couples support, Honeydue is built for couples but is SaaS-only, and Splitwise handles debt tracking but is not a finance manager. The gap is real and the technical approach is sound -- Java 21 + Spring Boot 3.5 on the backend, Svelte 5 + SvelteKit 2 on the frontend, PostgreSQL 16 for persistence, all containerized with Docker and fronted by Caddy.

The recommended approach is to build online-first and layer offline capabilities on top. The stack is well-researched with high-confidence version choices (Spring Boot 3.5.11, not 4.0; Tailwind v4, not v3; shadcn-svelte for components; LayerChart for visualizations). The architecture follows Vertical Slice with a shared kernel, SvelteKit acting as a BFF (Backend For Frontend) so the browser never talks directly to Spring Boot, and PostgreSQL Row-Level Security as defense-in-depth for data isolation. The most important architectural decision is that financial data conflicts are never auto-merged -- they are presented to the user for explicit resolution.

The single greatest risk is scope creep leading to abandonment. The MVP as currently scoped (auth, Plaid, PWA offline-first, budgeting with two modes, debt tracking, dashboard, CI/CD with advanced tooling, accessibility) is enormous for a solo developer learning two new frameworks simultaneously. The roadmap must ruthlessly phase delivery so that a usable app is deployed within 4-6 weeks. Secondary risks include Plaid EU re-authentication complexity (180-day token expiry under PSD2), offline sync conflict management for two concurrent users, and floating-point arithmetic in financial calculations.

## Key Findings

### Recommended Stack

The stack is constrained by learning goals (Java 21, Spring Boot, Svelte 5) but the specific version and library choices are well-researched. Spring Boot 3.5.11 is recommended over 4.0 -- Boot 4.0 brings Jakarta EE 11 and Jackson 3.x breaking changes with no benefit for this project. Tailwind CSS v4.2 is required by shadcn-svelte 1.0+. All frontend state management uses Svelte 5 runes (no external state libraries needed).

**Core technologies:**
- **Java 21 + Spring Boot 3.5.11**: Virtual threads, records, pattern matching. Stable, well-documented, 3+ months of runway before EOL.
- **Svelte 5 + SvelteKit 2**: Runes-based reactivity, file-based routing, SSR. SvelteKit server acts as BFF.
- **PostgreSQL 16**: JSONB for flexible data, pgcrypto for token encryption, RLS for data isolation.
- **shadcn-svelte + Bits UI**: Copy-paste component model, full styling control, Svelte 5 native.
- **Dexie 4 + @vite-pwa/sveltekit**: IndexedDB with live queries for offline storage, zero-config PWA plugin.
- **JJWT 0.12.6**: JWT token generation (Spring Security's Nimbus handles validation).
- **Plaid Java SDK 39.1.0**: Official SDK, pin version at project start.

**Critical version constraint:** LayerChart must be installed via `@next` tag for Svelte 5 support.

### Expected Features

**Must have (table stakes):**
- Multi-user with separate logins (Admin + Standard roles)
- Personal + shared accounts with visibility controls
- Manual transaction entry with categorization
- Bank sync via Plaid Link
- Monthly budgets by category with progress tracking
- Transaction history with search/filters
- Dashboard (balances, budgets, debts, recent transactions)
- Mobile-responsive design
- Dark/light theme
- Docker deployment
- Data export (JSON/CSV) -- self-hosted users expect this from day one

**Should have (differentiators):**
- Native internal debt tracking (core differentiator vs all competitors)
- Couple-native architecture (not bolted-on multi-user)
- Quick-add mobile entry (3 taps)
- Offline-first PWA with conflict resolution
- Dual budget modes (envelope + goal)

**Defer (v2+):**
- MCP/AI integration (Phase 2 learning goal)
- Push/email notifications
- Investment/net worth tracking
- Multi-currency support
- Receipt scanning
- Recurring transaction management (simple templates in v1.x, not MVP)

### Architecture Approach

The system is a three-tier architecture: SvelteKit PWA (client + SSR server) communicating via internal Docker network to a Spring Boot REST API backed by PostgreSQL. SvelteKit acts as a BFF -- the browser never calls Spring Boot directly. JWT is stored in httpOnly cookies, forwarded server-to-server as Bearer tokens. The backend uses Vertical Slice architecture with features (auth, transaction, budget, debt, plaid, sync) importing from a shared kernel but never from each other, enforced by ArchUnit tests. Spring ApplicationEvents decouple feature communication (e.g., TransactionCreated triggers budget and debt updates).

**Major components:**
1. **SvelteKit BFF** -- SSR, auth cookie management, API proxy, offline detection
2. **Spring Boot API** -- Business logic, authorization, Plaid integration, sync processing
3. **PostgreSQL + RLS** -- Persistence with Row-Level Security as defense-in-depth
4. **IndexedDB + Operation Queue** -- Client-side offline storage and write queue
5. **Service Worker** -- Asset caching, API response caching, Background Sync trigger
6. **Plaid Webhook Handler** -- Thin receiver that enqueues async sync jobs

### Critical Pitfalls

1. **Scope creep / project abandonment** -- The MVP scope is too large for a solo developer learning two new frameworks. Ruthlessly phase: deploy a usable v0.1 (auth + manual transactions + basic dashboard) within 4-6 weeks. Add capabilities incrementally.

2. **Floating-point money arithmetic** -- Use `BigDecimal` with String constructor and `HALF_EVEN` rounding from day one. Create a `Money` value object in the shared kernel. Use `NUMERIC(15,2)` in PostgreSQL. Never use `double` or `float` for monetary values. Recovery cost is HIGH if missed.

3. **JWT token storage in a PWA** -- Never store JWT in localStorage. SvelteKit server handles auth via httpOnly cookies and forwards tokens server-to-server. For offline mode, use a limited offline session token in IndexedDB that only unlocks cached read access.

4. **Plaid EU re-authentication** -- Tokens expire after 180 days under PSD2. Handle `PENDING_EXPIRATION` webhook, notify users proactively, implement re-auth via Plaid Link update mode. Manual entry must be a first-class feature, not a fallback.

5. **Offline sync conflict explosion** -- Use client-generated UUIDs (v7), operation queues (not state sync), server-authoritative resolution. Limit offline capabilities: create transactions yes, edit budgets or delete accounts no. Keep conflict UI to 3 options maximum.

## Implications for Roadmap

Based on combined research, the following phase structure respects dependency ordering, groups related features, and addresses pitfalls at the right time.

### Phase 1: Foundation (Infrastructure + Auth + Core Data Model)
**Rationale:** Everything depends on the shared kernel, security model, and base entities. RLS, JWT/BFF pattern, Money value object, and Liquibase conventions must be established before any feature code.
**Delivers:** Running Spring Boot + SvelteKit + PostgreSQL in Docker. Login/logout for 2 users. Account CRUD with personal/shared visibility. Minimal Liquibase schema (users, accounts, categories, permissions).
**Addresses:** Authentication, account management, Docker deployment
**Avoids:** Floating-point money (Money VO from day one), JWT in localStorage (BFF pattern from day one), schema rigidity (minimal schema, conventions established), scope creep (deploy something real early)

### Phase 2: Core Financial Data (Transactions + Budgets + Debt)
**Rationale:** These three features form the core value loop. Transactions feed budgets and debt calculations. They share the TransactionCreated event pattern and can be built together. This is where the app becomes usable daily.
**Delivers:** Manual transaction entry with categorization, transaction history with filters, monthly budgets (envelope + goal modes) with progress alerts, internal debt tracking with settlement suggestions, basic dashboard.
**Addresses:** Manual transactions, categorization, budgets, budget alerts, debt tracking, dashboard, data export
**Avoids:** Debt calculation edge cases (define business rules upfront, test extensively), dashboard N+1 queries (use JOIN FETCH from the start)

### Phase 3: Bank Sync (Plaid Integration)
**Rationale:** Plaid depends on accounts and transactions existing. It is high-complexity and benefits from the core data model being stable. Plaid-imported transactions are also a major source of conflicts that Phase 4 (offline) must handle.
**Delivers:** Plaid Link connection flow, webhook-driven cursor sync, transaction deduplication against manual entries, re-authentication flow for EU tokens, error handling for institution downtime.
**Addresses:** Bank sync, transaction import, deduplication
**Avoids:** Plaid EU re-auth issues (handle from day one), webhook reliability (idempotent handlers, daily fallback cron), treating webhooks as data delivery (thin receiver + async processing)

### Phase 4: Mobile Experience (Quick-Add + PWA Offline)
**Rationale:** Offline-first must be layered on top of working online features. The sync system touches every feature and is the riskiest component. All write paths must be stable before adding offline complexity. Quick-add is a streamlined UI for existing transaction creation.
**Delivers:** Quick-add mobile entry (3 taps), PWA shell with service worker, IndexedDB caching of recent data, operation queue for offline writes, sync endpoint with conflict detection, conflict resolution UI.
**Addresses:** Quick-add, PWA offline-first, conflict resolution, mobile-responsive polish
**Avoids:** Offline sync conflicts (operation queue + UUIDs designed in Phase 1, implemented here), IndexedDB storage growth (cache last 3 months only), auto-merging financial data (explicit user resolution)

### Phase 5: Polish and Hardening
**Rationale:** Quality tooling, advanced CI/CD, performance optimization, and accessibility hardening. These are important but should not block core feature delivery.
**Delivers:** SonarQube integration, SpotBugs, PIT mutation testing, WCAG 2.2 AA compliance, performance optimization (pre-computed aggregates for dashboard), automated backups with encryption, monitoring via Actuator.
**Addresses:** CI/CD pipeline completion, accessibility, backup, monitoring
**Avoids:** Perfectionism on tooling before features work (tooling added last)

### Phase Ordering Rationale

- **Phases 1-2 deliver a usable app in the shortest time.** A couple can start tracking finances manually within ~6 weeks, validating the core value proposition before investing in Plaid or offline.
- **Phase 3 before Phase 4** because Plaid-imported transactions create the most common conflict type (manual entry vs bank import). The sync system in Phase 4 must handle this.
- **Phase 4 is the riskiest phase** and benefits from all other features being stable. The design decisions it requires (UUIDs, operation queue interface) are made in Phase 1, but implementation is deferred.
- **Phase 5 is explicitly last** to prevent the scope creep pitfall of perfecting tooling before shipping features.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (Plaid Integration):** Complex third-party API with EU-specific behavior. Needs research on specific French bank coverage, webhook testing strategies, and sandbox-to-production differences. The Plaid SDK version may need updating at implementation time.
- **Phase 4 (PWA Offline):** Offline-first with multi-user conflict resolution is architecturally novel. Needs research on IndexedDB size limits across browsers (especially iOS Safari), Background Sync API reliability, and Svelte 5 integration patterns with Dexie liveQuery.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** Spring Boot + SvelteKit setup, JWT auth, Docker Compose are thoroughly documented with established patterns.
- **Phase 2 (Core Financial Data):** CRUD operations, event-driven updates, budgeting logic are standard application patterns. The debt tracking business rules need definition but not technical research.
- **Phase 5 (Polish):** SonarQube, accessibility testing, backup scripts are well-documented operational concerns.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Core technologies are constrained and verified. Library versions confirmed against npm/Maven. Some versions (LayerChart, Dexie Svelte 5 integration) need validation at install time. Spring Boot 3.5.11 EOL is 2026-06-30 -- tight but sufficient. |
| Features | HIGH | Comprehensive competitor analysis across 7 products. Clear differentiation identified. MVP scope is well-defined with sensible deferral decisions. |
| Architecture | HIGH | Patterns are well-documented with concrete code examples. Plaid cursor sync, offline operation queue, RLS defense-in-depth, and BFF proxy are all industry-proven approaches. Build order implications are clear. |
| Pitfalls | HIGH | Pitfalls are specific, actionable, and mapped to phases. Recovery strategies included. The scope creep warning is the most important finding across all research. |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Plaid French bank coverage:** Research confirmed EU support exists but specific coverage for French banks must be verified at Plaid account setup. Use `/institutions/get` to check before committing to specific banks.
- **Dexie + Svelte 5 runes integration:** Dexie's `liveQuery` works with Svelte but needs a wrapper for Svelte 5 reactivity. No production examples found -- will need experimentation in Phase 4.
- **Spring Boot 3.5 EOL (2026-06-30):** Only 3+ months of runway. Migration to 4.0 should be planned but is straightforward. Not a blocker but worth tracking.
- **LayerChart stability:** Using the `@next` tag (2.x) for Svelte 5 support. API may change. Pin the version and test chart components early if dashboard is critical path.
- **Debt business rules:** The technical implementation is straightforward, but the business rules for edge cases (partial payments, mixed personal/shared purchases, non-50/50 splits) must be defined with both partners before implementation.

## Sources

### Primary (HIGH confidence)
- [Spring Boot releases](https://github.com/spring-projects/spring-boot/releases) -- Boot 3.5.11 version and EOL confirmation
- [Plaid Transactions API](https://plaid.com/docs/api/products/transactions/) -- Cursor sync pattern, webhook types
- [Plaid Webhooks](https://plaid.com/docs/transactions/webhooks/) -- Implementation requirements
- [Spring Security JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html) -- Built-in Nimbus support
- [shadcn-svelte](https://shadcn-svelte.com/) -- Component library compatibility
- [AWS: PostgreSQL RLS](https://aws.amazon.com/blogs/database/multi-tenant-data-isolation-with-postgresql-row-level-security/) -- RLS patterns
- [Svelte npm](https://www.npmjs.com/package/svelte) / [SvelteKit npm](https://www.npmjs.com/package/@sveltejs/kit) -- Version confirmation

### Secondary (MEDIUM confidence)
- [LayerChart](https://next.layerchart.com/) -- Svelte 5 charting with @next tag
- [Dexie.js Svelte docs](https://dexie.org/docs/Tutorial/Svelte) -- v4.0 integration patterns
- [Offline Sync Patterns (2026)](https://www.sachith.co.uk/offline-sync-conflict-resolution-patterns-architecture-trade%E2%80%91offs-practical-guide-feb-19-2026/) -- Operation queue vs CRDT analysis
- [Plaid EU Re-Authentication](https://plaid.com/blog/eu-reauth-update/) -- 180-day token expiry
- Competitor analysis: Honeydue, Monarch, YNAB, Firefly III, Actual Budget, Splitwise -- feature landscape

### Tertiary (LOW confidence)
- [Testcontainers 2.0](https://github.com/testcontainers/testcontainers-java/releases) -- Module rename confirmed but integration with Boot 3.5.11 needs validation
- [@vite-pwa/sveltekit](https://github.com/vite-pwa/sveltekit) -- SvelteKit 2 compatibility stated but limited production reports

---
*Research completed: 2026-03-09*
*Ready for roadmap: yes*
