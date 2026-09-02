# Codebase Structure

**Analysis Date:** 2026-09-02

## Directory Layout

```
prosperity/
├── alembic/                    # SQLAlchemy migration scripts (Alembic)
│   └── versions/               # Versioned migration files (e.g., 001_initial.py)
├── backend/                    # Python FastAPI backend
│   ├── __init__.py
│   ├── config.py               # Settings, env var handling (Pydantic Settings)
│   ├── main.py                 # FastAPI app entry point, lifespan, event wiring
│   ├── modules/                # Business logic (7-level DAG)
│   │   ├── auth/               # Level 2: User, JWT, roles, invitations, audit
│   │   │   ├── domain.py       # AdminAction enum, constants
│   │   │   ├── models.py       # SQLAlchemy ORM (User, RefreshToken, Invitation)
│   │   │   ├── schemas.py      # Pydantic request/response schemas
│   │   │   ├── public.py       # Public surface (only cross-module import target)
│   │   │   ├── service/        # Internal business logic
│   │   │   │   ├── jwt.py      # Token creation/verification
│   │   │   │   ├── roles.py    # Admin promotion
│   │   │   │   ├── users.py    # User CRUD
│   │   │   │   ├── invitations.py  # Invitation workflow
│   │   │   │   ├── refresh_tokens.py
│   │   │   │   └── audit.py    # Audit trail writing
│   │   │   └── transports/
│   │   │       ├── http.py     # FastAPI routes (/auth, /invitations)
│   │   │       └── dependencies.py  # FastAPI dependency (get_current_user, require_admin)
│   │   ├── accounts/           # Level 3: Household, members, accounts
│   │   │   ├── domain.py       # AccountType enum (PERSONAL, SHARED)
│   │   │   ├── models.py       # Household, Account, Member ORM
│   │   │   ├── schemas.py
│   │   │   ├── public.py       # Access helpers, household CRUD
│   │   │   ├── service/
│   │   │   │   ├── accounts.py
│   │   │   │   ├── household.py
│   │   │   │   └── setup.py    # Bootstrap (S03.2-S03.3)
│   │   │   ├── transports/http.py
│   │   │   ├── repository/
│   │   │   └── handlers/       # Sync write handlers (S13.4)
│   │   ├── transactions/       # Level 4a: Tx CRUD, splits, state machine
│   │   │   ├── domain.py       # TransactionState, is_transfer
│   │   │   ├── models.py       # Transaction, Split ORM
│   │   │   ├── schemas.py
│   │   │   ├── events.py       # TransactionConfirmedEvent, etc.
│   │   │   ├── public.py
│   │   │   ├── service/
│   │   │   │   ├── lifecycle.py   # Draft → Confirm → Void state machine
│   │   │   │   └── queries.py     # Filtering, balances, search
│   │   │   ├── transports/http.py
│   │   │   ├── repository/
│   │   │   └── handlers/       # Sync write handlers
│   │   ├── budget/             # Level 4b: Categories, spending consumption
│   │   │   ├── domain.py       # BudgetState enum
│   │   │   ├── models.py       # Budget, Category ORM
│   │   │   ├── schemas.py
│   │   │   ├── events.py       # BudgetCreatedEvent, BudgetUpdatedEvent
│   │   │   ├── public.py
│   │   │   ├── service/
│   │   │   │   ├── budgets.py     # Budget CRUD
│   │   │   │   ├── categories.py  # Category CRUD
│   │   │   │   ├── consumption.py # Spending tracking, threshold alerts
│   │   │   │   ├── threshold_detector.py  # Alert logic
│   │   │   │   └── budget_crud.py
│   │   │   ├── transports/
│   │   │   │   ├── http.py     # Routes (/budgets, /categories)
│   │   │   │   └── budgets_http.py
│   │   │   ├── repository/
│   │   │   └── handlers/       # Sync write handlers
│   │   ├── banking/            # Level 4c: OFX parsing, bank integrations
│   │   │   ├── domain.py       # ImportState, BankingProvider interface
│   │   │   ├── models.py       # OFXImport, ImportRecord ORM
│   │   │   ├── schemas.py
│   │   │   ├── public.py
│   │   │   ├── service/
│   │   │   │   └── polling.py  # Bank provider polling (S12.4 — OFX import)
│   │   │   ├── providers/      # BankingProvider implementations (OFX parser, etc.)
│   │   │   │   └── ofx.py
│   │   │   ├── transports/http.py  # OFX import upload endpoint
│   │   │   ├── repository/
│   │   │   └── handlers/
│   │   ├── debts/              # Level 5: Balances, settlements, share-requests
│   │   │   ├── domain.py       # SettlementState, DebtType
│   │   │   ├── models.py       # Debt, Settlement, ShareRequest ORM
│   │   │   ├── schemas.py
│   │   │   ├── events.py       # DebtMaterializedEvent (S11.3)
│   │   │   ├── public.py       # Overflow materializer hooks, queries
│   │   │   ├── service/
│   │   │   │   ├── overflow_materializer.py  # Real-time balance compute
│   │   │   │   ├── dashboard.py   # Debt overview queries
│   │   │   │   ├── settlement.py  # Settlement lifecycle
│   │   │   │   ├── share_request.py
│   │   │   │   ├── remaining.py   # Remaining balance queries
│   │   │   └── transports/http.py
│   │   ├── sync/               # Level 6a: PowerSync dispatch, write upload
│   │   │   ├── domain.py
│   │   │   ├── models.py       # Sync state, checkpoint tracking
│   │   │   ├── schemas.py
│   │   │   ├── events.py
│   │   │   ├── public.py       # Upload handler, bucket info
│   │   │   ├── service/
│   │   │   │   ├── dispatcher.py   # RBAC step-1, route to handlers
│   │   │   │   └── upload_handler.py
│   │   │   ├── handlers/       # Per-entity write handlers
│   │   │   │   ├── accounts/
│   │   │   │   ├── transactions/
│   │   │   │   ├── budget/
│   │   │   │   └── debts/
│   │   │   └── transports/http.py  # POST /sync/upload endpoint
│   │   └── sse/                # Level 6b: Server-sent events, real-time broadcast
│   │       ├── domain.py
│   │       ├── models.py       # SSE token tracking
│   │       ├── schemas.py
│   │       ├── events.py       # SSE event types (broadcast targets)
│   │       ├── public.py       # Token issuance, verification
│   │       ├── service/
│   │       │   ├── broadcaster.py  # Event → client subscription mapping
│   │       │   └── delivery.py     # Token lifecycle, post-commit hook
│   │       └── transports/http.py  # GET /sse (EventSource)
│   ├── shared/                 # Level 1: DB, events, shared types
│   │   ├── db.py               # SQLAlchemy async engine, sessionmaker lifecycle
│   │   ├── models.py           # Base SQLAlchemy model
│   │   ├── events.py           # Domain event bus, subscribe_async decorator
│   │   ├── http.py             # HTTP error handling, exception handlers
│   │   ├── money.py            # Money, Currency types (Decimal-backed)
│   │   ├── currency.py         # Currency enums
│   │   ├── bank_labels.py      # Bank name mappings (OFX bank IDs → labels)
│   │   └── text.py             # Text sanitization
│   ├── transports/             # Composition root: cross-module flows
│   │   ├── __init__.py
│   │   └── imports_http.py     # OFX import commit (banking + transactions)
│   └── scripts/                # Utility scripts (not in app)
├── client/                     # React 19 + TypeScript + Vite frontend
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html              # Entry point template (anti-FOUC dark mode script)
│   ├── public/                 # Static assets (favicons, etc.)
│   ├── src/
│   │   ├── main.tsx            # React mount, AuthProvider → RouterProvider
│   │   ├── index.css           # Tailwind @import "tailwindcss"
│   │   ├── vite-env.d.ts
│   │   ├── app/                # Composition root (providers)
│   │   │   ├── auth-provider.tsx     # JWT token-store hydration (cold start)
│   │   │   ├── theme-provider.tsx    # Dark mode toggle
│   │   │   ├── powersync-provider.tsx # PowerSync SDK init
│   │   │   └── router.tsx       # TanStack Router config
│   │   ├── pages/              # TanStack Router file-based routes
│   │   │   ├── __root.tsx       # Root layout (<Outlet />)
│   │   │   ├── _authenticated.tsx  # Guard (beforeLoad: checkAuth)
│   │   │   ├── login.tsx
│   │   │   ├── setup.tsx
│   │   │   ├── accept-invite.tsx
│   │   │   └── _authenticated/  # Protected routes (subtree)
│   │   │       ├── dashboard.tsx
│   │   │       ├── accounts.tsx
│   │   │       ├── transactions.tsx
│   │   │       ├── budgets.tsx
│   │   │       └── ...
│   │   ├── lib/                # Utilities & services
│   │   │   ├── auth/           # JWT token-store (in-memory + SecureStorage)
│   │   │   │   └── token-store.ts
│   │   │   ├── api/            # OpenAPI-generated client + fetch wrapper
│   │   │   │   ├── client.ts   # Fetch hooks (via openapi-fetch)
│   │   │   │   └── schema.d.ts # Generated TypeScript types (from openapi.json)
│   │   │   ├── powersync/      # PowerSync SDK init, local DB schema
│   │   │   │   └── schema.ts   # Mirror of backend schema (Drizzle ORM)
│   │   │   ├── storage/        # SecureStorage (mobile) / localStorage (web)
│   │   │   │   └── secure-storage.ts
│   │   │   ├── sse/            # EventSource wrapper
│   │   │   │   └── sse-client.ts
│   │   │   ├── drizzle/        # Local SQLite schema (PowerSync sync target)
│   │   │   │   └── schema.ts
│   │   │   ├── utils.ts        # Helpers (formatting, validation)
│   │   │   └── form-data.ts
│   │   ├── components/         # React components
│   │   │   ├── ui/             # shadcn/ui primitives (Button, Dialog, Form, etc.)
│   │   │   │   ├── button.tsx
│   │   │   │   ├── dialog.tsx
│   │   │   │   ├── form.tsx    # React Hook Form integration
│   │   │   │   └── ...
│   │   │   ├── business/       # Domain components (tested with Vitest)
│   │   │   │   ├── TransactionForm.tsx
│   │   │   │   ├── BudgetCard.tsx
│   │   │   │   └── ...
│   │   │   └── layout/
│   │   │       ├── Header.tsx
│   │   │       └── Sidebar.tsx
│   │   ├── features/           # Feature modules (login, setup, dashboard flows)
│   │   │   ├── login/
│   │   │   ├── setup/
│   │   │   └── dashboard/
│   │   ├── hooks/              # Custom hooks
│   │   │   ├── useAuth.ts      # Access token, user context
│   │   │   ├── use-theme.ts    # Dark mode toggle
│   │   │   ├── use-sync-status.ts  # PowerSync connection status
│   │   │   ├── use-transactions.ts # Query transactions (PowerSync)
│   │   │   ├── use-account-balance.ts
│   │   │   └── ...
│   │   ├── types/              # Shared TypeScript types
│   │   │   └── index.ts
│   │   ├── config/             # App config
│   │   │   └── branding.ts     # App name, colors, etc.
│   │   └── __probe__/          # Smoke test utilities (NOT in main bundle)
│   ├── tests/
│   │   ├── mocks/              # Mock data factories
│   │   ├── msw/                # MSW handlers (API mocking for tests)
│   │   └── *.test.tsx          # Vitest + Testing Library tests (co-located)
│   ├── drizzle/                # Drizzle migration metadata (auto-generated)
│   │   └── meta/
│   ├── android/                # Capacitor Android native wrapper
│   │   ├── app/src/
│   │   └── gradle/
│   └── public/                 # Static files
├── compose/                    # Docker Compose helpers
│   └── initdb/                 # DB init scripts
│       └── 10_powersync_publication.sql  # PowerSync logical replication setup
├── compose.dev.yml             # Dev Docker Compose (Postgres, PowerSync Service)
├── alembic.ini                 # Alembic config
├── pyproject.toml              # Python project config (uv, pytest, ruff, pyright)
├── .importlinter               # Import graph contracts (7-level DAG enforcement)
├── .env.example                # Env var template (no actual secrets)
├── .nvmrc                       # Node version (22)
├── .python-version             # Python version (3.13)
├── .pre-commit-config.yaml     # Pre-commit hooks (ruff, pyright, import-linter)
├── tests/                      # Backend test suite
│   ├── unit/                   # Unit tests (isolated, no DB)
│   ├── integration/            # Integration tests (real Postgres, testcontainers)
│   │   └── conftest.py         # Fixtures (db_engine, db_session, app, committed_client)
│   └── e2e/                    # End-to-end tests (HTTP client, real backend)
├── docs/                       # Project documentation
│   ├── adr/                    # Architecture Decision Records
│   │   ├── 0001-*.md
│   │   ├── 0002-debts-as-server-projection.md
│   │   ├── 0003-powersync-bucket-design.md
│   │   ├── 0005-directional-import-graph.md
│   │   └── ...
│   ├── ui/                     # UI/UX documentation
│   └── Stratégie de tests.md   # Test strategy (§9 = CI/CD)
├── .github/workflows/
│   ├── push.yml                # On-push lint/unit/integration (< 5 min)
│   └── nightly.yml             # Cron: property tests, pip-audit, coverage
├── .planning/                  # GSD planning
│   ├── codebase/               # Codebase maps (this folder)
│   │   ├── ARCHITECTURE.md
│   │   ├── STRUCTURE.md
│   │   ├── CONVENTIONS.md (quality focus)
│   │   └── ...
│   ├── milestones/
│   └── phases/
├── runbooks/                   # Operational runbooks
│   └── powersync_setup.md      # PowerSync dev setup guide
├── scripts/                    # Utility scripts
│   └── smoke_powersync.sh      # PowerSync health check
├── README.md
├── CONTEXT.md                  # Domain context (data model, flows)
└── CLAUDE.md                   # Agent instructions (issue tracker, domain docs)
```

## Directory Purposes

**`backend/`:**
- Purpose: FastAPI HTTP server + business logic
- Entry: `backend/main.py`
- Key subdivisions: `modules/` (business logic by domain), `shared/` (foundation), `transports/` (composition root)

**`backend/modules/`:**
- Purpose: Organize code into 8 separate modules, each with clear boundary (public.py re-export)
- Layout: Each module has `domain.py`, `models.py`, `schemas.py`, `public.py`, `service/`, `transports/`, `handlers/`, `repository/`
- Modules form a 7-level DAG: auth → accounts → {transactions, budget, banking} → debts → {sync, sse}

**`backend/shared/`:**
- Purpose: Foundation layer (DB engine, events, shared types) — imports nothing from modules
- Key files: `db.py` (SQLAlchemy lifespan), `events.py` (event bus), `models.py` (Base ORM)

**`backend/transports/`:**
- Purpose: Composition root for cross-module HTTP flows (e.g., OFX import orchestration)
- Currently: Only `imports_http.py` (banking + transactions assembly)

**`client/src/`:**
- Purpose: React 19 frontend (web + Capacitor mobile)
- Entry: `main.tsx` (AuthProvider → RouterProvider)
- Key subdivisions: `app/` (providers), `pages/` (file-based routes), `lib/` (services), `components/` (UI + business)

**`client/src/lib/`:**
- Purpose: Service layer (API client, PowerSync, SSE, auth token-store)
- Auth: `auth/token-store.ts` (JWT in-memory + SecureStorage)
- API: `api/client.ts` (OpenAPI-generated, typed fetch), `api/schema.d.ts` (types from openapi.json)
- PowerSync: `powersync/schema.ts` (local SQLite schema), `drizzle/schema.ts` (Drizzle ORM)

**`client/src/components/`:**
- Purpose: UI components (shadcn/ui primitives + business components)
- `ui/`: Radix-based primitives (copied from shadcn, not imported)
- `business/`: Domain-aware components (TransactionForm, BudgetCard — tested with Vitest)

**`tests/`:**
- Purpose: Backend test suite (unit, integration, E2E)
- `conftest.py` (fixtures): db_engine, db_session, app (FastAPI test client), committed_client (with pre-populated DB)
- Marker: e2e tests flagged with `@pytest.mark.e2e`

**`docs/adr/`:**
- Purpose: Architecture Decision Records (rationale for key decisions)
- Example: ADR 0005 (directional graph), ADR 0003 (PowerSync buckets), ADR 0002 (debts as server projection)

**`.planning/codebase/`:**
- Purpose: GSD codebase maps (ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, CONCERNS.md)
- Generated by `/gsd-map-codebase` command; consumed by planner/executor for phase implementation

## Key File Locations

**Entry Points:**
- `backend/main.py`: FastAPI app creation, lifespan, event wiring, router inclusion
- `client/src/main.tsx`: React mount, provider composition (Auth → PowerSync → Router)
- `alembic/versions/*.py`: Database schema migrations (auto-generated by `alembic revision`)

**Configuration:**
- `backend/config.py`: Pydantic Settings (env vars, defaults)
- `client/vite.config.ts`: Vite + TanStack Router plugin
- `.importlinter`: Import-linter layer contracts (7-level DAG enforcement)

**Core Logic:**
- `backend/modules/*/service/`: Business logic per module (lifecycle, queries, calculations)
- `backend/modules/*/public.py`: Module API boundary (re-exports)
- `backend/shared/events.py`: Event bus (subscribe_async, publish)
- `client/src/lib/api/client.ts`: OpenAPI-generated API client (typed fetch)

**Testing:**
- `tests/integration/conftest.py`: Fixtures (app, db_session)
- `tests/unit/`: Unit tests (no DB, isolated)
- `client/src/**/*.test.tsx`: Component tests (Vitest + Testing Library)

## Naming Conventions

**Files:**
- Backend Python files: `snake_case.py` (e.g., `lifecycle.py`, `overflow_materializer.py`)
- Client TypeScript files: `camelCase.tsx|ts` for components (e.g., `TransactionForm.tsx`, `useAuth.ts`); `snake_case.ts` for utilities
- Database migrations: `001_initial.py`, `002_add_audit_log.py` (auto-numbered by Alembic)
- Environment: `.env.example` (template), `.env*` (git-ignored actuals)

**Directories:**
- Module structure: Always `domain.py`, `models.py`, `schemas.py`, `public.py`, `service/`, `transports/`, `handlers/`
- Client features: `features/[feature_name]/` (e.g., `features/login/`, `features/setup/`)
- Shared: `shared/`, `lib/` (backend vs client naming, same concept)

## Where to Add New Code

**New Backend Feature (e.g., Forecasting Module):**
- Create `backend/modules/forecasting/` with standard structure:
  - `__init__.py`, `domain.py` (enums, constants), `models.py` (SQLAlchemy ORM)
  - `schemas.py` (Pydantic request/response), `public.py` (re-export)
  - `service/` (queries, CRUD, calculations), `transports/http.py` (FastAPI routes)
  - `handlers/` (sync write handlers, if any)
- Update `.importlinter`: Add contract `2-forecasting` (forbidden imports of peer internals) + update `contract:1` layers to position forecasting in DAG
- Register routers in `backend/main.py` (include_router)
- If forecasting consumes events from other modules, wire subscribers in `main.py` (compose at root)
- Write tests in `tests/unit/forecasting/` and `tests/integration/forecasting/`

**New Client Page/Feature:**
- Create route file in `client/src/pages/` (e.g., `_authenticated/forecasting/index.tsx`)
- TanStack Router will auto-generate `routeTree.gen.ts` (commit this)
- Create feature folder `client/src/features/forecasting/` if flow is complex
- Business components in `client/src/components/business/forecasting/` (test with Vitest)
- UI primitives via shadcn copy-paste into `client/src/components/ui/` (e.g., `npx shadcn@latest add select`)
- Query hook in `client/src/hooks/use-forecasting.ts` (wraps PowerSync query or API fetch)

**New Shared Type/Utility:**
- Backend: `backend/shared/[domain].py` (e.g., `forecasting_types.py`)
- Client: `client/src/lib/[domain].ts` or `client/src/types/index.ts`
- Ensure backend doesn't import client types; client can generate types from backend OpenAPI schema (`gen:api`)

**New API Endpoint:**
- Create route handler in module's `transports/http.py` (e.g., `backend/modules/forecasting/transports/http.py`)
- Use `@router.get|post("/endpoint")` decorator
- Import dependencies (auth.public.get_current_user, accounts.public.account_is_accessible) freely
- Call service layer (forecasting.service.queries, forecasting.service.crud)
- Register router in `backend/main.py`
- Generate client types: `npm run gen:api` (from OpenAPI schema)

**New Database Table/Migration:**
- Add SQLAlchemy ORM model in `backend/modules/[module]/models.py`
- Run `uv run alembic revision -m "Add [table_name]"` → auto-detects changes
- Edit `alembic/versions/[new_revision].py` to add migration logic (drop, rename, etc.)
- Run `uv run alembic upgrade head` to apply
- Update local Drizzle schema (`client/src/lib/drizzle/schema.ts`) to mirror Postgres
- Run `npm run db:generate` to update local migration metadata

## Special Directories

**`.planning/codebase/`:**
- Purpose: Generated codebase maps (ARCHITECTURE.md, STRUCTURE.md, etc.)
- Generated by: `/gsd-map-codebase` skill
- Committed: Yes (part of repo)
- Role: Reference for planner/executor in subsequent `/gsd-plan-phase` and `/gsd-execute-phase`

**`alembic/versions/`:**
- Purpose: Database schema evolution
- Generated by: `alembic revision -m "..."` (auto-detects SQLAlchemy model changes)
- Committed: Yes (immutable once created)
- Manual edits: Rare (usually auto-generated is sufficient)

**`client/src/lib/api/`:**
- Purpose: OpenAPI-generated client + types
- Generated by: `npm run gen:api` (from `openapi.json` published by backend)
- Committed: Yes (schema.d.ts)
- Stability: Regenerate after backend API changes

**`client/src/routeTree.gen.ts`:**
- Purpose: TanStack Router file-based route tree (auto-generated)
- Generated by: Vite + @tanstack/router-plugin (automatic on file changes)
- Committed: Yes (required for type-safe routing)

**`htmlcov/` (coverage reports):**
- Purpose: Test coverage HTML (from `pytest --cov`)
- Generated by: `uv run pytest --cov`
- Committed: No (git-ignored)
- View: Open `htmlcov/index.html` in browser

---

*Structure analysis: 2026-09-02*
