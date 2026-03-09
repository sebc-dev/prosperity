# Architecture Research

**Domain:** Self-hosted personal finance app for couples (multi-user, offline-first, bank sync)
**Researched:** 2026-03-09
**Confidence:** HIGH

## System Overview

The existing architecture document (`docs/architecture.md`) is thorough and well-designed. This research validates those decisions and digs deeper into the five areas that need architectural clarity: multi-user data isolation, Plaid integration patterns, PWA offline-first sync, dual-user conflict resolution, and the SvelteKit-to-Spring Boot API boundary.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Client Layer                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │
│  │  SvelteKit   │  │  Service     │  │  IndexedDB               │   │
│  │  (UI + SSR)  │  │  Worker      │  │  (offline store + queue) │   │
│  └──────┬───────┘  └──────┬───────┘  └────────────┬─────────────┘   │
│         │                 │                        │                 │
│         └────────┬────────┘────────────────────────┘                 │
│                  │ online: fetch API                                 │
│                  │ offline: queue to IndexedDB                       │
├──────────────────┼──────────────────────────────────────────────────┤
│                  │         API Boundary                              │
│         ┌────────▼────────┐                                         │
│         │  SvelteKit      │  server-side load/actions                │
│         │  Server Hooks   │  (proxies to Spring Boot)               │
│         └────────┬────────┘                                         │
├──────────────────┼──────────────────────────────────────────────────┤
│                  │         Backend Layer                             │
│  ┌───────────────▼──────────────────────────────────────────────┐   │
│  │              Spring Boot REST API                             │   │
│  │  ┌──────┐ ┌───────────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌─────┐ │   │
│  │  │ auth │ │transaction│ │budget│ │ debt │ │ plaid│ │sync │ │   │
│  │  └──┬───┘ └─────┬─────┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬──┘ │   │
│  │     └────────────┴──────────┴────────┴────────┴────────┘     │   │
│  │                    shared/ (kernel)                           │   │
│  │          security  |  persistence  |  domain  |  config      │   │
│  └──────────────────────────┬───────────────────────────────────┘   │
├─────────────────────────────┼───────────────────────────────────────┤
│                             │         Data Layer                    │
│  ┌──────────────────────────▼──────────┐  ┌─────────────────────┐   │
│  │  PostgreSQL 16                       │  │  Plaid API          │   │
│  │  (RLS policies + optimistic locking) │  │  (webhooks + sync)  │   │
│  └─────────────────────────────────────┘  └─────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| SvelteKit UI | Rendering, client-side routing, offline detection, IndexedDB reads | Svelte 5 components + runes stores |
| Service Worker | Asset caching, API response caching, Background Sync trigger | SvelteKit `$service-worker`, cache-first for assets, network-first for API |
| IndexedDB | Offline data store, operation queue persistence | idb library (typed wrapper), mirrors server state for read, queues writes |
| SvelteKit Server | SSR, `load` functions, form actions, API proxy to Spring Boot | `hooks.server.ts` adds auth headers, proxies to `http://prosperity-api:8080` |
| Spring Boot API | Business logic, authorization, data persistence, event bus | Vertical Slice architecture with shared kernel |
| Sync Feature | Conflict detection, batch operation processing, reconciliation | Server-authoritative with explicit user conflict resolution |
| Plaid Feature | Bank connection, webhook receipt, cursor-based transaction sync | Webhook-driven with scheduled fallback polling |
| PostgreSQL | Data persistence, row-level security, optimistic locking | RLS policies per user_id, `@Version` on entities |

## Architectural Patterns

### Pattern 1: Multi-User Data Isolation (Permission-Based + RLS)

**What:** For a couple's finance app, data isolation is not traditional multi-tenancy (separate data per tenant). Instead, it is a permission-based access model where accounts are either PERSONAL (visible only to owner) or SHARED (visible to both). The existing `permissions` table in the architecture doc handles this correctly.

**When to use:** Always -- this is the foundation of the entire access model.

**Trade-offs:** Application-level permission checks (`@PreAuthorize`) are sufficient for 2 users but are error-prone (one missed check = data leak). Adding PostgreSQL Row-Level Security (RLS) as a defense-in-depth layer eliminates this risk class entirely.

**Recommendation: Add RLS as defense-in-depth.** The application already has `@PreAuthorize` on services. Add RLS policies on PostgreSQL so that even a buggy query cannot leak data across users. For 2 users, the performance impact is negligible.

```sql
-- Set current user context on each connection (Spring sets this via connection init)
-- In a @Transactional method interceptor or connection pool initializer:
SET app.current_user_id = '<uuid>';

-- RLS policy on transactions: user sees only transactions on accounts they have permission to
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY transactions_access ON transactions
    USING (
        account_id IN (
            SELECT account_id FROM permissions
            WHERE user_id = current_setting('app.current_user_id')::uuid
              AND revoked_at IS NULL
        )
    );

-- RLS policy on accounts: user sees only accounts they own or have permission on
ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;

CREATE POLICY accounts_access ON accounts
    USING (
        owner_id = current_setting('app.current_user_id')::uuid
        OR id IN (
            SELECT account_id FROM permissions
            WHERE user_id = current_setting('app.current_user_id')::uuid
              AND revoked_at IS NULL
        )
    );
```

```java
// Spring: Set RLS context on each request via a HikariCP connection customizer
// or a TransactionSynchronization that runs SET before each transaction
@Component
public class RlsConnectionCustomizer implements ConnectionCustomizer {
    @Override
    public void customize(Connection connection, String userId) throws SQLException {
        try (var stmt = connection.prepareStatement("SET app.current_user_id = ?")) {
            stmt.setString(1, userId);
            stmt.execute();
        }
    }
}
```

**Key insight:** RLS is not a replacement for application-level permission checks -- it is a safety net. The `@PreAuthorize` annotations remain the primary access control mechanism. RLS catches bugs where a query accidentally touches rows the user should not see.

### Pattern 2: Plaid Webhook-Driven Cursor Sync

**What:** Plaid's `/transactions/sync` endpoint uses a cursor-based model. The server stores the last cursor per `PlaidItem`. When Plaid sends a `SYNC_UPDATES_AVAILABLE` webhook, the app calls `/transactions/sync` with the stored cursor, receives `added`, `modified`, and `removed` arrays, and processes them. The cursor advances with each call. Pagination continues until `has_more` is `false`.

**When to use:** This is the only recommended approach for Plaid transaction integration. The older `/transactions/get` endpoint is legacy.

**Trade-offs:** Webhook-driven is efficient but webhooks can be lost. A scheduled fallback (daily cron) ensures eventual consistency even if webhooks fail.

**Architecture flow:**

```
Plaid Cloud                       Spring Boot
    │                                  │
    │  SYNC_UPDATES_AVAILABLE webhook  │
    │ ─────────────────────────────────>│
    │                                  │  1. Verify webhook signature
    │                                  │  2. Enqueue sync job (Spring @Async)
    │                                  │
    │    /transactions/sync?cursor=X   │
    │ <────────────────────────────────│  3. Call with stored cursor
    │                                  │
    │  {added:[], modified:[],         │
    │   removed:[], next_cursor, ...}  │
    │ ─────────────────────────────────>│  4. Process response:
    │                                  │     - INSERT new transactions
    │                                  │     - UPDATE modified transactions
    │                                  │     - DELETE removed transactions
    │                                  │     - Detect duplicates vs manual entries
    │                                  │  5. Store next_cursor
    │                                  │  6. If has_more: repeat from step 3
    │                                  │  7. Publish PlaidSyncCompleted event
    │                                  │
    │                     @Scheduled   │
    │    /transactions/sync?cursor=X   │
    │ <────────────────────────────────│  Fallback: daily cron for missed webhooks
```

**Critical implementation details:**

1. **Webhook receiver must be thin.** Accept the webhook, verify the signature, enqueue an async job, return 200 immediately. Plaid retries with exponential backoff if no 200 within 10 seconds.

2. **Store both current cursor and pagination-start cursor.** If `TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION` error occurs mid-pagination, restart from the pagination-start cursor, not the latest one.

3. **Deduplication against manual entries.** When Plaid imports a transaction, check for manual entries within a +/- 10% amount window and +/- 5 day date window on the same account. Flag as potential conflict rather than auto-merging -- let the user decide.

4. **Plaid access tokens must be encrypted at rest.** AES-256-GCM with the `ENCRYPTION_KEY` environment variable. The existing `PlaidItem` entity design handles this.

### Pattern 3: Offline-First Sync with Operation Queue

**What:** The client maintains a local copy of data in IndexedDB and an operation queue for writes made while offline. When connectivity returns, the queue is drained to the server via `POST /api/sync`. The server processes operations, detects conflicts, and returns results.

**When to use:** For all write operations in the PWA. Reads are served from IndexedDB when offline, from API (cached in IndexedDB) when online.

**Recommendation: Operation Queue + Server-Authoritative + Explicit Conflict Resolution.** CRDTs are overkill for 2 users editing financial data -- the conflict surface is small and financial data demands correctness over automatic merging. An operation log with server-side validation is the right pattern.

**Architecture:**

```
┌─────────── Client (SvelteKit PWA) ────────────┐
│                                                 │
│  User Action (create/update/delete transaction) │
│       │                                         │
│       ▼                                         │
│  ┌─────────────┐     ┌──────────────────┐       │
│  │ Optimistic   │────>│ IndexedDB        │       │
│  │ Local Apply  │     │ (local mirror)   │       │
│  └──────┬──────┘     └──────────────────┘       │
│         │                                       │
│         ▼                                       │
│  ┌─────────────┐                                │
│  │ Operation    │  {type, data, clientId,        │
│  │ Queue (IDB)  │   timestamp, version}          │
│  └──────┬──────┘                                │
│         │                                       │
│    online?──── NO ──> wait for connectivity     │
│         │                                       │
│        YES                                      │
│         │                                       │
│         ▼                                       │
│  POST /api/sync  {operations: [...]}            │
│         │                                       │
└─────────┼───────────────────────────────────────┘
          │
          ▼
┌─────── Server (Spring Boot) ─────────┐
│                                       │
│  SyncService.processOperations()      │
│       │                               │
│       ▼                               │
│  For each operation:                  │
│  1. Check version (optimistic lock)   │
│  2. Validate business rules           │
│  3. Apply or flag conflict            │
│       │                               │
│       ▼                               │
│  Response:                            │
│  {                                    │
│    applied: [...],                    │
│    conflicts: [...],                  │
│    serverState: {...}                 │
│  }                                    │
└───────────────────────────────────────┘
```

**Key design decisions:**

1. **Client-generated UUIDs.** The client generates transaction IDs (UUID v7 for time-ordering). This prevents duplicate creation when the same operation is replayed after a network failure.

2. **Optimistic locking via `version` column.** Each entity has a `version` (already in `BaseEntity`). The client sends the version it last saw. If the server version is different, it is a conflict.

3. **Operation types are explicit.** Each queued operation is `{type: 'CREATE_TRANSACTION' | 'UPDATE_TRANSACTION' | 'DELETE_TRANSACTION' | ..., data: {...}, clientTimestamp: string, entityVersion: number}`.

4. **Batch sync endpoint.** `POST /api/sync` accepts an array of operations and returns an array of results. This is more efficient than individual API calls and allows the server to process operations in dependency order.

### Pattern 4: Dual-User Conflict Resolution

**What:** Two users (the couple) can both be offline and make conflicting changes. The most common scenarios: both edit the same transaction, both create a transaction that looks like a duplicate, or one deletes a transaction the other modified.

**When to use:** Whenever the sync endpoint detects a version mismatch or a potential duplicate.

**Recommendation: Server-authoritative with 3-option user resolution.** Financial data is too sensitive for automatic merging. When a conflict is detected, the server stores both versions and presents them to the user for resolution.

**Conflict types and resolution strategies:**

| Conflict Type | Detection | Resolution |
|---------------|-----------|------------|
| Same entity, different edits | `version` mismatch (client sends v2, server has v3) | Show both versions, user picks one or merges manually |
| Manual entry vs Plaid import | Amount within 10%, date within 5 days, same account | Show both, user picks: keep manual, keep import, or keep both |
| Delete vs modify | Client deletes entity at version N, server has version N+1 | Show modification, user confirms delete or keeps modified |
| Duplicate creation | Two offline creates with similar data | Show both, user picks: merge into one or keep both |

**Resolution flow:**

```
Conflict Detected (server-side)
    │
    ▼
Store in conflict_resolutions table
    │
    ▼
Return conflict in sync response
    │
    ▼
Client shows conflict resolution UI
(side-by-side comparison: local vs server)
    │
    ▼
User picks: KEEP_LOCAL | KEEP_REMOTE | KEEP_BOTH | MANUAL_MERGE
    │
    ▼
POST /api/sync/resolve {conflictId, resolution, mergedData?}
    │
    ▼
Server applies resolution
    │
    ▼
24h undo window (conflict_resolutions.expires_at)
```

**Key insight for couples:** Most conflicts will be benign -- both added a coffee expense, one manually and one got it from Plaid. The UI should make this obvious with a side-by-side view showing amounts, dates, and descriptions. The "keep both" option should be prominent because they are usually genuinely different transactions.

### Pattern 5: SvelteKit-to-Spring Boot API Boundary

**What:** SvelteKit runs as a Node.js server that proxies API calls to Spring Boot. The boundary between them needs clear conventions for auth forwarding, error handling, and data types.

**When to use:** Every API interaction.

**Recommendation: SvelteKit server hooks as API gateway.** All API calls from the browser go through SvelteKit's server-side `load` functions and form actions, which proxy to Spring Boot. The browser never talks directly to Spring Boot.

**Architecture:**

```
Browser                  SvelteKit Server              Spring Boot
   │                          │                            │
   │  GET /dashboard          │                            │
   │ ─────────────────────>   │                            │
   │                          │  GET /api/dashboard        │
   │                          │  Authorization: Bearer JWT │
   │                          │ ───────────────────────>   │
   │                          │                            │
   │                          │  200 {accounts, budgets..} │
   │                          │ <───────────────────────   │
   │  HTML (SSR rendered)     │                            │
   │ <─────────────────────   │                            │
   │                          │                            │
   │  POST /transactions/new  │                            │
   │  (form action)           │                            │
   │ ─────────────────────>   │                            │
   │                          │  POST /api/transactions    │
   │                          │ ───────────────────────>   │
   │                          │                            │
   │  303 redirect            │  201 {transaction}         │
   │ <─────────────────────   │ <───────────────────────   │
```

**Implementation in `hooks.server.ts`:**

```typescript
// src/hooks.server.ts
import type { Handle } from '@sveltejs/kit';

export const handle: Handle = async ({ event, resolve }) => {
    // Extract JWT from cookie (httpOnly, secure)
    const token = event.cookies.get('auth_token');

    if (token) {
        // Make token available to load functions and form actions
        event.locals.token = token;

        // Optionally decode to get user info for SSR
        event.locals.user = decodeJwtPayload(token);
    }

    return resolve(event);
};
```

```typescript
// src/lib/api/client.ts -- server-side API client
const API_BASE = process.env.API_URL || 'http://prosperity-api:8080';

export async function apiRequest(
    path: string,
    token: string,
    options: RequestInit = {}
): Promise<Response> {
    return fetch(`${API_BASE}${path}`, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
            ...options.headers,
        },
    });
}
```

**Key conventions:**

1. **JWT stored in httpOnly cookie**, not localStorage. SvelteKit server reads it from the cookie and forwards as Bearer token to Spring Boot. This prevents XSS from stealing tokens.

2. **Error mapping.** SvelteKit server translates Spring Boot error responses into SvelteKit `error()` or `fail()` responses with user-friendly messages. Spring Boot returns structured `ApiError` records; SvelteKit maps these to form validation errors or error pages.

3. **Type sharing.** TypeScript types in `$lib/api/types.ts` mirror the Java record DTOs. These are manually maintained (not auto-generated) to keep the build simple. A mismatch is caught by integration tests.

4. **Client-side direct API calls for offline scenarios.** When the Service Worker intercepts a failed API call (offline), it queues the operation. When online, the Service Worker or the SyncStore replays directly to the SvelteKit server, which proxies to Spring Boot. The browser never bypasses SvelteKit.

## Data Flow

### Flow 1: Online Transaction Creation

```
User taps "add" on mobile
    ↓
Quick-Add component → amount → category → confirm
    ↓
SvelteKit form action (POST /transactions/quick-add)
    ↓
+page.server.ts validates, calls apiRequest('POST', '/api/transactions', ...)
    ↓
Spring Boot TransactionController → TransactionService
    ↓
TransactionService: save to DB, publish TransactionCreated event
    ↓
BudgetService @EventListener: update budget spent amount
DebtService @EventListener: check if shared account → create debt entry
    ↓
Response flows back: 201 → SvelteKit redirect → dashboard
```

### Flow 2: Offline Transaction Creation + Sync

```
User taps "add" while offline
    ↓
Quick-Add component detects offline (syncStore.isOnline === false)
    ↓
Generate UUID v7 for transaction, save to IndexedDB (local mirror)
Queue operation to IndexedDB (operation queue)
Show optimistic UI update immediately
    ↓
... time passes, connectivity returns ...
    ↓
SyncStore.processQueue() triggered by 'online' event
    ↓
POST /api/sync {operations: [{type: CREATE_TRANSACTION, data: {...}, ...}]}
    ↓
SyncService processes each operation:
  - Validates (account exists, user has WRITE permission)
  - Checks for duplicates (Plaid may have imported same transaction)
  - If no conflict: INSERT, return in applied[]
  - If duplicate detected: return in conflicts[]
    ↓
Client receives response:
  - applied[]: update local IndexedDB with server-confirmed versions
  - conflicts[]: show conflict resolution UI
```

### Flow 3: Plaid Bank Sync

```
Plaid sends SYNC_UPDATES_AVAILABLE webhook
    ↓
PlaidWebhookHandler: verify signature, enqueue async job
Return 200 immediately
    ↓
PlaidSyncJob (async): load PlaidItem, get stored cursor
    ↓
Loop: call /transactions/sync with cursor
  - Process added[]: match against manual entries (dedup check)
  - Process modified[]: update existing Plaid-imported transactions
  - Process removed[]: soft-delete or mark removed
  - Store next_cursor
  - Continue if has_more === true
    ↓
On TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION: restart from saved start cursor
    ↓
Publish PlaidSyncCompleted event
    ↓
BudgetService updates spending totals
DashboardService invalidates cached aggregations
WebSocket notifies connected clients of new transactions
```

### Flow 4: Dual-User Conflict

```
User A (offline): edits transaction T1 description to "Groceries"
User B (online): edits transaction T1 amount from 50 to 55

User B's edit succeeds immediately (T1 version 1 → 2)

User A comes back online, sync queue drains:
  POST /api/sync {operations: [{type: UPDATE_TRANSACTION, id: T1,
                                 data: {description: "Groceries"},
                                 entityVersion: 1}]}

SyncService detects: client version 1 != server version 2
  → Creates conflict_resolutions entry
  → Returns: conflicts: [{id: C1, local: {desc: "Groceries", amount: 50},
                           remote: {desc: "Coffee Shop", amount: 55}}]

User A sees conflict UI:
  "Your edit: Groceries (50 EUR)"    vs    "Current: Coffee Shop (55 EUR)"
  [Keep mine] [Keep theirs] [Both are right - merge manually]

User A picks "merge": sets description="Groceries", amount=55
  POST /api/sync/resolve {conflictId: C1, resolution: MANUAL_MERGE,
                           mergedData: {description: "Groceries", amount: 55}}
```

## Recommended Project Structure

The existing structure from `docs/architecture.md` is well-designed. The additions below address gaps identified during research.

```
prosperity/
├── backend/                          # Spring Boot application
│   └── src/main/java/.../prosperity/
│       ├── shared/
│       │   ├── domain/               # Value objects, events
│       │   ├── security/             # JWT, permissions, RLS context setter
│       │   ├── persistence/          # BaseEntity, audit, RLS connection customizer
│       │   ├── web/                  # Exception handler, rate limiting
│       │   └── config/              # Async, Jackson, CORS
│       ├── auth/                     # Login, refresh tokens
│       ├── user/                     # User CRUD
│       ├── account/                  # Accounts + permissions
│       ├── transaction/              # Manual + Plaid transactions
│       ├── budget/                   # Monthly budgets
│       ├── debt/                     # Internal debts
│       ├── plaid/                    # Plaid integration (webhook, sync job)
│       ├── sync/                     # Offline sync processing, conflict detection
│       └── dashboard/                # Aggregated views
│
├── frontend/                         # SvelteKit application
│   └── src/
│       ├── routes/                   # File-based routing (as documented)
│       ├── lib/
│       │   ├── api/
│       │   │   ├── client.ts         # Server-side: proxy to Spring Boot
│       │   │   ├── client-browser.ts # Client-side: for offline queue replay
│       │   │   └── types.ts          # TypeScript mirrors of Java DTOs
│       │   ├── components/           # UI components
│       │   ├── stores/               # Svelte 5 rune-based stores
│       │   ├── sync/
│       │   │   ├── idb-store.ts      # IndexedDB schema + typed access (via idb)
│       │   │   ├── offline-queue.ts  # Operation queue (write to IDB)
│       │   │   ├── sync-manager.ts   # Orchestrates drain on reconnect
│       │   │   └── conflict-detector.ts  # Client-side pre-checks
│       │   └── utils/
│       ├── service-worker.ts         # Cache strategies + Background Sync
│       └── hooks.server.ts           # Auth cookie → Bearer token forwarding
│
└── docker-compose.yml                # db + api + web
```

### Structure Rationale

- **`shared/security/` gains RLS context setter:** A `ConnectionCustomizer` that sets `app.current_user_id` on each DB connection, enabling RLS policies as defense-in-depth.
- **`lib/api/` splits server vs browser clients:** Server-side client proxies with full auth headers. Browser client is only used by the sync manager for queue replay.
- **`lib/sync/` is the offline engine:** `idb-store.ts` wraps IndexedDB with typed access via the `idb` library. `offline-queue.ts` manages the operation log. `sync-manager.ts` orchestrates draining the queue when connectivity returns.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 2 users (MVP) | Current architecture is ideal. In-memory Spring cache, no Redis, RLS for safety, simple conflict resolution. |
| 5-10 users (family/friends) | Add Redis for cache and session store. Add WebSocket rooms per household. Permission model already supports this. |
| 10+ users | Out of scope per PROJECT.md. Would need true multi-tenancy (schema-per-household or discriminator column). |

### Scaling Priorities

1. **First bottleneck: Plaid rate limits.** Plaid has per-Item rate limits on `/transactions/sync`. With 2 users this is not an issue, but batching and respecting rate limits is good practice from day one.
2. **Second bottleneck: IndexedDB storage.** Browsers limit IndexedDB to ~50-100MB typically. For a couple with 5 years of transactions (~50k records), this is approximately 10-20MB -- well within limits. Implement a pruning strategy (keep last 2 years locally, older data is server-only) as a safety measure.

## Anti-Patterns

### Anti-Pattern 1: Browser Talks Directly to Spring Boot

**What people do:** Expose Spring Boot on a public port and have the browser call it directly, bypassing SvelteKit's server.
**Why it is wrong:** Loses SSR capability, forces JWT into localStorage (XSS vulnerability), makes CORS configuration complex, and splits auth logic between two servers.
**Do this instead:** All browser requests go through SvelteKit. SvelteKit server-side code proxies to Spring Boot via internal Docker network. JWT lives in httpOnly cookie, never exposed to JavaScript.

### Anti-Pattern 2: Auto-Merging Financial Conflicts

**What people do:** Use CRDTs or Last-Writer-Wins to automatically resolve all conflicts.
**Why it is wrong:** Financial data has business invariants (budget limits, debt calculations) that automatic merge cannot validate. LWW can silently lose a partner's manual transaction entry. CRDTs solve data structure conflicts, not business logic conflicts.
**Do this instead:** Detect conflicts server-side, store both versions, present to the user for explicit resolution. The UI should make resolution fast (3 taps: see both, pick one, confirm).

### Anti-Pattern 3: Polling Plaid Instead of Webhook-Driven Sync

**What people do:** Set up a cron job that calls `/transactions/sync` every 5 minutes regardless of whether new data exists.
**Why it is wrong:** Wastes API calls against rate limits, adds unnecessary load, and introduces latency (up to 5 minutes) when webhooks would notify in near-real-time.
**Do this instead:** Primary: webhook-driven sync (`SYNC_UPDATES_AVAILABLE` triggers async sync job). Fallback: daily scheduled sync to catch missed webhooks. On-demand: user can trigger manual refresh via `/transactions/refresh`.

### Anti-Pattern 4: Storing Full Dataset in IndexedDB

**What people do:** Mirror the entire PostgreSQL database into IndexedDB for "complete offline access."
**Why it is wrong:** IndexedDB has storage limits, initial sync takes too long on mobile, and most historical data is never accessed offline.
**Do this instead:** Store in IndexedDB: last 3 months of transactions, current month's budgets, current debt balances, account summaries. Older data is fetched from the server on demand and not cached locally.

### Anti-Pattern 5: Treating Plaid Webhooks as Data Delivery

**What people do:** Parse transaction data directly from the webhook payload.
**Why it is wrong:** Plaid webhooks contain only notification metadata (item_id, webhook_type), not transaction data. The `SYNC_UPDATES_AVAILABLE` webhook is a signal to call `/transactions/sync`, not a data payload.
**Do this instead:** Webhook receiver verifies signature, extracts item_id, enqueues an async job that calls `/transactions/sync` with the stored cursor.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Plaid API | Webhook-driven cursor sync via `/transactions/sync` | Webhook receiver must return 200 within 10s. Plaid retries for 24h with exponential backoff. |
| Plaid Link | Client-side JavaScript SDK in SvelteKit | Generates `link_token` server-side, initializes Plaid Link client-side, exchanges `public_token` server-side |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| SvelteKit SSR ↔ Spring Boot | HTTP REST via internal Docker network | SvelteKit uses `fetch` in `load`/actions to `http://prosperity-api:8080`. No public exposure of Spring Boot. |
| Browser ↔ SvelteKit | HTTP + Service Worker intercept | Service Worker caches GET responses. Offline writes queue to IndexedDB. |
| Feature ↔ Feature (backend) | Spring ApplicationEvents | TransactionCreated → BudgetService, DebtService. PlaidSyncCompleted → DashboardService. No direct feature-to-feature injection. |
| Feature ↔ Shared Kernel | Direct dependency | Features import from `shared/` package. Shared kernel never imports from features. One-way dependency. |

## Build Order Implications

Based on the architectural dependencies, the suggested build order is:

1. **Shared Kernel + Auth + User** -- Everything depends on security and user context. RLS setup, JWT, and the 2-user model must exist first.
2. **Account + Permission** -- Accounts are the container for all financial data. Permissions gate all access. Nothing else works without accounts.
3. **Transaction (manual)** -- Core data entity. Budgets, debts, and dashboard all depend on transactions existing.
4. **Budget + Debt** -- These consume TransactionCreated events. They can be built in parallel once transactions exist.
5. **Plaid Integration** -- Depends on accounts and transactions existing. Adds automatic transaction import on top of manual entry.
6. **Sync + Offline Queue** -- Depends on all write features existing. Adds the offline layer on top of working online features. This is the riskiest component and benefits from all other features being stable.
7. **Dashboard** -- Aggregates all other features. Build last when all data sources are available.
8. **PWA Shell + Service Worker** -- Polish layer. Cache strategies and install prompts on top of a working application.

**Rationale:** Build online-first, add offline layer after. The sync system is the most complex component and touches every feature. Building it last means all features are tested and stable in the online path before adding offline complexity. The Plaid integration comes before sync because Plaid-imported transactions are a major source of conflicts that the sync system must handle.

## Sources

- [Plaid Transactions API Documentation](https://plaid.com/docs/api/products/transactions/)
- [Plaid Transactions Webhooks](https://plaid.com/docs/transactions/webhooks/)
- [Plaid Transactions Sync Introduction](https://plaid.com/docs/transactions/)
- [Plaid Blog: Transactions Sync paradigm](https://plaid.com/blog/transactions-sync/)
- [Plaid Sync Migration Guide](https://plaid.com/docs/transactions/sync-migration/)
- [Offline Sync & Conflict Resolution Patterns (Feb 2026)](https://www.sachith.co.uk/offline-sync-conflict-resolution-patterns-architecture-trade%E2%80%91offs-practical-guide-feb-19-2026/)
- [Offline-First Frontend Apps in 2025 - LogRocket](https://blog.logrocket.com/offline-first-frontend-apps-2025-indexeddb-sqlite/)
- [AWS: Multi-tenant data isolation with PostgreSQL RLS](https://aws.amazon.com/blogs/database/multi-tenant-data-isolation-with-postgresql-row-level-security/)
- [Crunchy Data: Row Level Security for Tenants](https://www.crunchydata.com/blog/row-level-security-for-tenants-in-postgres)
- [CRDTs Overview](https://crdt.tech/)
- [Plaid Webhooks Implementation Best Practices](https://www.fintegrationfs.com/post/plaid-webhooks-implementation-why-most-teams-get-it-wrong-and-how-to-fix-it)

---
*Architecture research for: Prosperity -- self-hosted personal finance for couples*
*Researched: 2026-03-09*
