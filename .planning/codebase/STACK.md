# Technology Stack

**Analysis Date:** 2026-09-02

## Languages

**Primary:**
- **Python 3.13** - Backend application, API logic, database management
- **TypeScript 5.7** - Client application with strict type checking
- **JavaScript (ES2022+)** - Runtime for client/browser

## Runtime

**Environment:**
- **Python 3.13** (via `.python-version`) - Backend execution
- **Node.js 22+** (via `.nvmrc`) - Client development and build

**Package Manager:**
- **uv (Python)** - Latest version, locked via `uv.lock`
  - Lockfile: `uv.lock` present and committed
  - Config: `tool.uv.package = false` (application, not installable package)
- **npm (Node.js)** - Latest stable
  - Lockfile: `package-lock.json` present and committed

## Frameworks

**Core Web:**
- **FastAPI 0.118+** - Async-first HTTP framework, automatic OpenAPI schema generation
- **Uvicorn 0.38+** - ASGI server for FastAPI
- **React 19.0.0** - Client UI framework
- **Vite 8.0.16** - Client build tool and dev server

**Client Routing & State:**
- **TanStack Router 1.170.15** - File-based routing (routes in `src/pages/`), type-safe search params
- **@tanstack/router-plugin** - Vite plugin for route generation
- **PowerSync (@powersync/react 1.10.0, @powersync/web 1.38.3)** - Real-time sync client

**Database & ORM:**
- **SQLAlchemy 2.0.49 with asyncio** - Backend async ORM for Postgres
- **asyncpg 0.31.0** - Async PostgreSQL driver
- **Alembic 1.18.4** - Database migration management
- **Drizzle ORM 0.45.2** - Client-side SQLite schema mirror for sync
- **better-sqlite3 11.10.0** - Client SQLite driver (dev/test)

**UI & Styling:**
- **Tailwind CSS 4.3.1** - Utility-first CSS framework
- **shadcn/ui** - Copy-pasted component library (Radix UI primitives)
- **Lucide React 1.18.0** - Icon library
- **class-variance-authority 0.7.1** - Component variant system
- **Sonner 2.0.7** - Toast notifications
- **Radix UI 1.5.0** - Headless UI primitives (via shadcn)

## Testing Frameworks

**Backend:**
- **pytest 8.3+** - Test runner with async support
- **pytest-asyncio 1.3.0** - Async test support
- **pytest-cov 7.1.0** - Coverage reporting
- **pytest-xdist 3.8.0** - Parallel test execution
- **testcontainers[postgres] 4.14.2** - Container-based test fixtures (integration tests)
- **hypothesis 6.152.9** - Property-based testing
- **factory-boy 3.3.3** - Test data factories
- **httpx 0.28+** - HTTP client for test requests
- **psycopg2-binary 2.9.10** - Postgres adapter for testing

**Client:**
- **Vitest 4.1.8** - Fast unit test runner
- **@testing-library/react 16.3.2** - React component testing
- **@testing-library/jest-dom 6.9.1** - DOM matchers
- **@testing-library/user-event 14.6.1** - User interaction simulation
- **MSW 2.14.6** - Mock Service Worker for API mocking
- **jsdom 29.1.1** - DOM simulation for tests

## Quality & Linting Tools

**Python:**
- **Ruff 0.14.0** - Linter and formatter
  - Rules: E, F, I, UP, B, PL
  - Line length: 100 characters
- **Pyright 1.1.405+** - Strict type checking
  - Mode: strict on `backend/`, standard on `tests/`
  - Reports missing imports as error
- **import-linter 2.3+** - Architecture enforcement (5 contracts, ADR 0005)
- **pre-commit 4.0+** - Git hooks (ruff, pyright, import-linter, pytest)

**Client:**
- **ESLint 9.0.0** - JavaScript linting
- **typescript-eslint 8.0.0** - TypeScript linting rules
- **eslint-plugin-react-hooks 5.0.0** - React hooks rules
- **eslint-plugin-react-refresh 0.4.0** - React refresh compatibility
- **Prettier 3.0.0** - Code formatter

## Key Dependencies

**Critical (Backend):**
- **sqlalchemy[asyncio] 2.0.49** - Async database access and query building
- **asyncpg 0.31.0** - High-performance async Postgres driver
- **fastapi 0.118+** - Web framework with built-in validation
- **pydantic 2.x** - Data validation and serialization (via FastAPI)
- **pydantic-settings 2.14.2** - Environment configuration management
- **uvicorn[standard] 0.38+** - Production ASGI server

**Authentication & Security (Backend):**
- **pyjwt[crypto] 2.10** - JWT token signing/verification
- **pwdlib[argon2] 0.2.1** - Password hashing with Argon2id
- **email-validator 2.2** - Email format validation
- **SecretStr** (Pydantic) - Secret value masking in logs

**Data Processing (Backend):**
- **ofxparse 0.21** - OFX (Open Financial Exchange) file parsing
- **pyyaml 6.0** - YAML parsing (dev/config)

**Infrastructure (Backend):**
- **alembic 1.18.4** - Database schema versioning
- **python-multipart 0.0.9** - Multipart form data handling (file uploads)

**Client SDK & Sync:**
- **@powersync/react 1.10.0** - React hooks for PowerSync integration
- **@powersync/web 1.38.3** - PowerSync web client library
- **@powersync/drizzle-driver 0.7.3** - Drizzle ORM integration with PowerSync
- **drizzle-orm 0.45.2** - Lightweight SQLite ORM
- **drizzle-kit 0.28.1** - Schema migration and generation tools

**Client Mobile & Capacitor:**
- **@capacitor/core 8.4.0** - Cross-platform app framework
- **@capacitor/android 8.4.0** - Android runtime
- **@capacitor/cli 8.4.0** - CLI tools
- **@aparajita/capacitor-secure-storage 8.0.0** - Secure credential storage

**Client API & Networking:**
- **openapi-fetch 0.17.0** - Typed REST client from OpenAPI schema
- **openapi-typescript 7.13.0** - OpenAPI schema to TypeScript types
- **@microsoft/fetch-event-source 2.0.1** - Server-Sent Events (SSE) client

**Client Utilities:**
- **uuid 11.1.1** - UUID generation
- **tailwind-merge 3.6.0** - Tailwind class merging utility
- **clsx 2.1.1** - Class name merging

## Configuration

**Environment:**
- **Backend:** `.env` file with `pydantic-settings` (case-insensitive env vars)
- **Client:** `VITE_*` prefixed variables (inlined at build time, public only)
- Dev secrets: `.env.example` (credentials are git-ignored)

**Build:**
- **Backend:** No build step; runs directly via `uv run uvicorn`
- **Client:** `vite build` → static bundle in `dist/`
- **Docker Compose:** `compose.dev.yml` for local dev (Postgres + PowerSync)

**Database Migrations:**
- **Tool:** Alembic (`alembic/` directory)
- **Commands:**
  - `uv run alembic upgrade head` - Apply migrations
  - `uv run alembic revision -m "<message>"` - Create new migration
- **Postgres WAL Level:** Set to `logical` for PowerSync replication (in compose)

## Platform Requirements

**Development:**
- Python 3.13.x
- Node.js 22+
- Postgres 17 (via Docker/Podman for local dev)
- Podman or Docker (for compose services)
- Git with pre-commit hook support

**Build:**
- uv (Python 3.13+)
- npm (Node.js 22+)
- TypeScript compiler (via npm)
- Vite (via npm)

**Production:**
- Python 3.13 runtime (ASGI-compatible)
- Postgres 17 (persistent source DB + bucket-storage DB)
- PowerSync Service (self-hosted, Open Edition)
- Reverse proxy (Caddy, referenced in compose notes)
- TLS/SSL (Cloudflare Tunnel for E16)
- Logical replication WAL setup on Postgres

---

*Stack analysis: 2026-09-02*
