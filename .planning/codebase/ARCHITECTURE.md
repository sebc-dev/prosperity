<!-- refreshed: 2026-09-02 -->
# Architecture

**Analysis Date:** 2026-09-02

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│              FastAPI Application (main.py)                  │
│         Composition Root / Event Subscription Wiring         │
└────────────┬────────────────────────────────────────────────┘
             │
    ┌────────┴────────────────────────────────────────────┐
    │                                                     │
┌───▼───────────────────────────┐  ┌────────────────────▼───┐
│   Module Layer                │  │  Transports Layer     │
│  `backend.modules.*`          │  │  `backend.transports` │
│                               │  │                       │
│ ┌─────────────────────────┐   │  │ ┌─────────────────┐   │
│ │ Auth (public.py)        │   │  │ │ OFX Import      │   │
│ │ `backend.modules.auth`  │   │  │ │ (composition    │   │
│ └─────────────────────────┘   │  │ │  across         │   │
│         ▲                      │  │ │  modules)       │   │
│         │ (lower layer)        │  │ └─────────────────┘   │
│ ┌─────────────────────────┐   │  └─────────────────────────┘
│ │ Accounts (public.py)    │   │
│ │ `backend.modules.accounts`  │
│ └─────────────────────────┘   │
│         ▲                      │
│         │ (lower layer)        │
│ ┌──────────────────────────────────────┐
│ │ Transactions | Budget | Banking      │
│ │ (peer modules, each with public.py)  │
│ └──────────────────────────────────────┘
│         ▲                      │
│         │ (lower layer)        │
│ ┌──────────────────────────────────────┐
│ │ Debts (public.py)                    │
│ │ `backend.modules.debts`              │
│ └──────────────────────────────────────┘
│         ▲                      │
│         │ (lower layer)        │
│ ┌───────────────────────────────────────┐
│ │ Sync | SSE (top layer, public.py)    │
│ │ `backend.modules.sync`                │
│ │ `backend.modules.sse`                 │
│ └───────────────────────────────────────┘
│         ▲                      │
└─────────┼──────────────────────┘
          │
┌─────────▼─────────────────────────────┐
│ Shared Foundation Layer               │
│ `backend.shared` (db, events, http)   │
│ (imports nothing from modules)        │
└───────────────────────────────────────┘
          │
          ▼
  ┌───────────────────┐
  │  Postgres 17      │
  │  (SQLAlchemy 2    │
  │   async stack)    │
  └───────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Auth | User identity, JWT tokens, roles, invitations, audit log | `backend/modules/auth/public.py` |
| Accounts | Household members, personal/shared bank accounts, roles | `backend/modules/accounts/public.py` |
| Transactions | Transaction CRUD, splits, state machine (draft/pending/confirmed) | `backend/modules/transactions/public.py` |
| Budget | Budget categories, spending consumption, threshold alerts | `backend/modules/budget/public.py` |
| Banking | OFX parsing, bank provider integrations, import hashes | `backend/modules/banking/public.py` |
| Debts | Debt tracking, settlements, share requests (inter-member balance) | `backend/modules/debts/public.py` |
| Sync | PowerSync bucket dispatch, write upload handler, RBAC step-1 | `backend/modules/sync/public.py` |
| SSE | Server-sent events for real-time client updates (post-commit) | `backend/modules/sse/public.py` |
| Shared | DB engine, session lifecycle, event bus, money types, HTTP helpers | `backend/shared/` |
| Transports | Composition root for cross-module flows (OFX commit) | `backend/transports/` |

## Pattern Overview

**Overall:** Directional acyclic import graph (DAG) with public surfaces per module

**Key Characteristics:**
- **7-level directional graph:** Enforced by `import-linter` contracts (`.importlinter`)
- **Public-only cross-module imports:** Each module exports a `public.py` re-export surface; peers may NOT import internals (service, models, transports)
- **Mini-bus for cross-module events:** Synchronous in-process event dispatch (`backend.shared.events`) — modules publish domain events without importing subscribers
- **Composition root at top:** `backend.main` wires event subscribers + router inclusion at startup; `backend.transports` holds cross-module HTTP flows
- **Encapsulation by layer:** Lower modules (auth, accounts) provide foundational services; higher modules (debts, sync) depend downward only

## Layers

**Level 1 — Shared Foundation:**
- Purpose: DB engine lifecycle, async session management, event bus primitives, shared types (Money, Currency)
- Location: `backend/shared/`
- Contains: `db.py` (SQLAlchemy + Alembic), `events.py` (sync event dispatch), `models.py` (base SQLAlchemy model), `money.py` (Decimal-backed currency), `http.py` (error handlers), `text.py` (text sanitization)
- Depends on: Postgres 17, SQLAlchemy, Pydantic
- Used by: All modules

**Level 2 — Auth Module:**
- Purpose: User identity, JWT token lifecycle (access/refresh/SSE), roles (admin/member), invitations, audit trail
- Location: `backend/modules/auth/`
- Contains: `domain.py` (AdminAction enum), `models.py` (User, RefreshToken, Invitation ORM), `service/` (JWT, roles, invitations, users, audit), `transports/` (FastAPI routes + dependencies)
- Public surface: `public.py` re-exports User, UserRole, token funcs, RBAC guards (require_admin, require_member), invitation management
- Depends on: backend.shared
- Used by: accounts (setup flow), budget, transactions, debts, sync, sse (auth guards in routes)

**Level 3 — Accounts Module:**
- Purpose: Household setup, member lifecycle, personal/shared bank account ownership, member role per account
- Location: `backend/modules/accounts/`
- Contains: `domain.py` (AccountType enum), `models.py` (Household, Account, Member ORM), `service/` (bootstrap, household CRUD, account CRUD), `transports/` (setup, account routes)
- Public surface: `public.py` re-exports account-access helpers (account_is_accessible, owned_personal_account_ids, shared_account_ids_with_members_subset), setup flow
- Depends on: backend.shared, auth.public
- Used by: transactions, budget, debts, sync (RBAC, account ownership checks)

**Level 4 — Transactions | Budget | Banking (Peer Modules):**
- Purpose: Core financial data — transactions (with splits), budgets (with categories), banking integrations (OFX import)
- Locations: `backend/modules/transactions/`, `backend/modules/budget/`, `backend/modules/banking/`
- Each contains: `domain.py`, `models.py` (ORM), `service/` (queries, CRUD, state transitions), `transports/` (HTTP routes)
- Transaction state machine: Draft → Pending (bank posting) → Confirmed (reconciled) | Voided (soft-delete)
- Transaction events: TransactionConfirmedEvent, TransactionVoidedEvent, TransactionEditableFieldsChangedEvent (driven by budget materializer)
- Public surfaces: Expose CRUD, state queries, event types; internals (service details, ORM model internals) are private
- Depend on: backend.shared, auth.public, accounts.public
- Cannot import each other (peers); use SQLAlchemy Core reads at composition root if cross-read needed

**Level 5 — Debts Module:**
- Purpose: Inter-member balance tracking, settlements (debt resolution), share-request workflow (transaction split confirmations)
- Location: `backend/modules/debts/`
- Contains: `domain.py` (SettlementState), `models.py` (Debt, Settlement, ShareRequest ORM), `service/` (materialization, queries, settlement lifecycle)
- Subscription: Listens to TransactionConfirmedEvent, TransactionVoidedEvent, TransactionEditableFieldsChangedEvent, BudgetCreatedEvent, BudgetUpdatedEvent (materializes overflow debts in real-time)
- Public surface: `public.py` re-exports materializer hooks + query services; overflow-debt re-computation is event-driven, not explicit
- Depends on: backend.shared, auth.public, accounts.public, transactions.public, budget.public
- Used by: sync (write validation), sse (broadcast), main (event wiring)

**Level 6 — Sync | SSE (Top Layers):**
- Purpose: PowerSync bucket dispatch per household, write upload handler (RBAC step-1), real-time event broadcast
- Locations: `backend/modules/sync/`, `backend/modules/sse/`
- Sync: `service/dispatcher.py` (routes writes to handlers), `handlers/` (per-entity write handlers), `service/` (upload validation, bucket resolution)
- SSE: `service/broadcaster.py` (event → client mapping), `service/delivery.py` (SSE token lifecycle), `transports/http.py` (EventSource endpoint)
- Public surfaces: Upload handler, bucket info queries (sync); SSE token funcs (sse)
- Depend on: All lower modules via .public surfaces
- Used by: main (composition root), client (PowerSync endpoint, SSE stream)

## Data Flow

### Primary Request Path — Transaction Create/Confirm

1. Client POST `/transactions` with splits → `backend/modules/transactions/transports/http.py` (route handler)
2. Handler validates account access via `auth.public.get_current_user` + `accounts.public.account_is_accessible`
3. Creates draft transaction via `transactions.service.lifecycle.create_draft` (ORM insert + return)
4. Confirms via `transactions.service.lifecycle.confirm_transaction` → publishes `TransactionConfirmedEvent` (via `backend.shared.events.publish`)
5. Event subscribers (registered at composition root in `main.py`):
   - `budget.public.on_transaction_confirmed` → recomputes consumption, publishes `BudgetUpdatedEvent`
   - `debts.public.materialize_overflow` → re-materializes overflow debts (splits owed to other members)
6. Response returns the confirmed transaction to client
7. SSE delivery broadcasts updates to all connected clients (via `sse.service.broadcaster` post-commit hook)

### PowerSync Write Upload Path

1. Client writes locally (Drizzle ORM on local SQLite) → calls `POST /sync/upload` (batched change stream)
2. `backend/modules/sync/transports/http.py` dispatches to `sync.service.dispatcher`
3. Dispatcher step-1: RBAC check via `auth.public.verify_access_token` + `accounts.public.account_is_accessible`
4. Step-2: Routes each write to entity-specific handler in `sync.handlers/` (e.g., `handlers/accounts/insert.py`)
5. Handler validates + calls service layer (e.g., `transactions.service.lifecycle` for transaction inserts)
6. Service publishes domain events (TransactionConfirmedEvent, etc.) → triggers same flow as direct HTTP
7. Upload response includes write results + new PowerSync checkpoint → client updates local cursor
8. Subsequent downloads filter via PowerSync bucket (household isolation via `sync.service.dispatcher.bucket_for_user`)

### State Management & Persistence

- **Server-of-truth model:** Postgres 17 is the canonical source for derived state (debts, budget consumption, balance projections)
- **Async ORM:** SQLAlchemy 2 with asyncpg for non-blocking DB queries (Uvicorn worker pool)
- **Transaction isolation:** All writes wrapped in SQLAlchemy transactions; domain events fire within the same DB transaction (synchronous dispatch)
- **Client sync:** PowerSync buckets pull changes incrementally (subscription-based replication publication → PowerSync Service → client)

## Key Abstractions

**Domain Event System:**
- Purpose: Decouple modules while maintaining synchronous transactional guarantees
- Examples: `TransactionConfirmedEvent` (transactions.events), `BudgetCreatedEvent` (budget.events), `SharedAccountCreatedEvent` (accounts.events)
- Pattern: Pydantic BaseModel subclass; published via `backend.shared.events.subscribe_async` at composition root; sync dispatch within DB transaction
- File: `backend/shared/events.py`

**Public Surface (Module Export):**
- Purpose: Explicit API boundary per module; import-linter enforces that only .public.py may be imported cross-module
- Examples: `backend/modules/auth/public.py`, `backend/modules/transactions/public.py`
- Pattern: Re-exports (via __all__) selected service functions, models (User, Transaction), error types (UserNotFoundError), event types
- Design: Each module writes its public.py _before_ internals, forcing an API-first mindset

**Household/Account Ownership Model:**
- Purpose: Multi-tenant isolation within single Postgres DB (per ADR 0003)
- Key helpers: `accounts.public.account_is_accessible(user_id, account_id)` (RBAC check), `owned_personal_account_ids(user_id)` (filter), `shared_account_ids_with_members_subset(user_id)` (filter)
- Pattern: Query filters use `account.household_id == user.household_id` + role-based access (personal accounts visible only to owner; shared accounts to all household members)

**Overflow Debt Materialization:**
- Purpose: Real-time computation of inter-member balances (who owes whom for split transactions)
- Examples: Transaction split [$50 personal from Alice, $30 from joint] → creates Debt [Bob owes Alice $30] if Bob is co-owner of joint account
- Pattern: Event-driven; materializer (`debts.service.overflow_materializer`) re-runs on TransactionConfirmedEvent, TransactionVoidedEvent, BudgetCreatedEvent, BudgetUpdatedEvent
- Files: `backend/modules/debts/service/overflow_materializer.py`, `backend/modules/debts/public.py` (subscribers wired in main.py)

## Entry Points

**HTTP Server:**
- Location: `backend.main:app` (FastAPI instance)
- Triggers: `uv run uvicorn backend.main:app --reload` (dev) or Uvicorn in prod
- Responsibilities: Lifespan management (db_lifespan, event subscriber registration, admin bootstrap), route inclusion, OpenAPI schema

**Database Migrations:**
- Location: `alembic/versions/` (Alembic revision scripts)
- Triggers: `uv run alembic upgrade head` (apply), `alembic downgrade` (rollback)
- Responsibilities: Schema evolution (table defs, migrations apply ORM model changes)

**PowerSync Service (External):**
- Location: Docker service (compose.dev.yml) in dev; managed separately in prod
- Triggers: Logical replication publication (`compose/initdb/10_powersync_publication.sql`); PowerSync Service subscribes and pushes to clients
- Responsibilities: Download sync (read-only replication of Postgres changes to client)

**Write Upload Handler:**
- Location: `backend/modules/sync/transports/http.py:POST /sync/upload`
- Triggers: Client batches local changes, sends upload request
- Responsibilities: Validate writes (RBAC step-1), dispatch to handlers, publish events, return confirmation

## Architectural Constraints

- **Threading:** Single-threaded async event loop (Uvicorn worker). All DB access via asyncpg (non-blocking). CPU-bound work (OFX parsing, password hashing) does NOT block the loop (offloaded to ThreadPoolExecutor if needed — currently not done; OFX parse is negligible in scope).
- **Global state:** `app.state.sessionmaker` (SQLAlchemy async sessionmaker) set by db_lifespan; `sse.service.broadcaster` is a module-level singleton Broadcaster instance
- **Circular imports:** None (directional graph enforced by import-linter); peer modules (transactions, budget, banking) cannot import each other directly
- **Event dispatch:** Synchronous within same DB transaction; eventual consistency NOT supported (all subscribers fire before response). If a subscriber raises, the entire write rolls back
- **No distributed transactions:** All operations within single Postgres connection; no Saga pattern (overkill for solo-dev scope)
- **PowerSync isolation:** Per-household bucket isolation enforced by dispatcher step-1 (account_is_accessible check + bucket ID derived from household_id)

## Anti-Patterns

### Reach into Peer Internals (Forbidden)

**What happens:** A module imports `backend.modules.transactions.service.lifecycle` from outside the transactions module (e.g., `budget.service.something → transactions.service`)
**Why it's wrong:** Violates the DAG contract; transactions and budget are peers (same layer 4). If budget relied on transactions internals, and later debts relied on budget, we'd have a 3-module chain that's fragile — a change to transactions.service internals could cascade
**Do this instead:** Transactions publishes `TransactionConfirmedEvent`; budget subscribes to it (via event bus). No direct import. Example: `backend/modules/budget/public.py` line 28 wires subscription in main.py, not inside budget module

### Importing from a Peer's Public Surface When Directionality Forbids It

**What happens:** A lower-layer module tries to import from a higher-layer module's .public (e.g., `auth → sync.public`)
**Why it's wrong:** Breaks the directional graph; lower layers should not know about higher-level features
**Do this instead:** If lower-layer logic needs higher-layer behavior, move the logic to the composition root (main.py or transports/). Example: OFX import commit (S12.4) lives in `backend/transports/imports_http.py`, not in banking.service, so it can safely compose banking.public + transactions.public

### Skipping the Public Surface Re-export

**What happens:** A module imports directly from internals (e.g., `from backend.modules.auth.service.users import create_user` instead of `from backend.modules.auth.public import create_user`)
**Why it's wrong:** Breaks encapsulation; future refactorings of auth.service internals will leave loose pointers everywhere. The public surface acts as a versioning contract
**Do this instead:** Always import from .public. Example: `backend/modules/accounts/service/setup.py` imports `auth.public.create_user`, not auth.service.users directly (though both resolve to the same func; the former is the documented API)

---

*Architecture analysis: 2026-09-02*
