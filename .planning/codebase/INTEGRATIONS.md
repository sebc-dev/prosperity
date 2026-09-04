# External Integrations

**Analysis Date:** 2026-09-02

## APIs & External Services

**PowerSync (Real-time Sync Service):**
- **Service:** PowerSync Service (self-hosted, Open Edition)
- **Purpose:** Live synchronization of data to mobile/web clients, offline-first support
  - Download flow: PowerSync Service pushes data to clients via buckets (configured in `powersync/sync_rules.yaml`)
  - Upload flow: Client writes go to FastAPI `POST /sync/upload` handler, NOT through PowerSync Service
- **SDK/Client:**
  - Backend: No direct client; uses Postgres logical replication
  - Client: `@powersync/web@1.38.3`, `@powersync/react@1.10.0`, `@powersync/drizzle-driver@0.7.3`
- **Config:** `powersync/config.yaml` (mounted in compose)
  - Authentication: JWT via JWKS endpoint (`PS_JWKS_URI`)
  - Audience: `prosperity-api` (pinned in client auth configuration)
- **Transport:** HTTP API on configurable port (`PS_PORT`), local admin token for diagnostics

**OFX (Open Financial Exchange) File Import:**
- **Purpose:** Bank account statement import and transaction parsing
- **SDK/Client:** `ofxparse@0.21` (Python library)
- **Implementation:** `backend.modules.banking.public.parse_ofx()`
- **Route:** `POST /imports/ofx/preview`, `/imports/ofx/commit`, `/imports/ofx/link-account`
- **File size limit:** 25 MB OFX + multipart envelope (~26 MB total, `MAX_REQUEST_BYTES` in `backend/transports/imports_http.py`)

**OpenAPI (REST API Schema):**
- **Purpose:** Type-safe REST client generation and API documentation
- **Generation:** FastAPI auto-generates OpenAPI at `/openapi.json`
- **SDK/Client:**
  - Backend: FastAPI (automatic)
  - Client: `openapi-typescript@7.13.0` (schema to TypeScript), `openapi-fetch@0.17.0` (typed client)
- **Command:** `npm run gen:api` generates `src/lib/api/schema.d.ts` from `openapi.json`
- **Validation:** `npm run gen:api:check` ensures schema is up-to-date

## Data Storage

**Databases:**

**Postgres 17 (Source of Truth):**
- **Connection:** `postgresql+asyncpg://` (async driver)
- **Role:** Single source of truth for all app state (transactions, accounts, debts, budgets)
- **Environment Variable:** `DATABASE_URL`
- **Default Dev:** `postgresql+asyncpg://prosperity:prosperity@localhost:5432/prosperity`
- **Client:** SQLAlchemy 2.0+ async ORM
- **Features:**
  - Logical replication (WAL level=logical) for PowerSync sync
  - Alembic for schema versioning and migrations
  - Roles: `prosperity` (app user), `powersync` (replication user), `ps_storage` (bucket storage)

**PostgreSQL `powersync_storage` Database:**
- **Role:** Dedicated bucket-storage database for PowerSync service
- **Connection:** `PS_STORAGE_URI` environment variable
- **Owner:** `ps_storage` role (CREATE privilege for PowerSync schema)
- **Deployment:** Separate DB on same Postgres instance (dev) or separate host (prod, E16)

**SQLite (Client-Side):**
- **Purpose:** Local sync cache for offline-first operation
- **Client Library:** `drizzle-orm@0.45.2` with `better-sqlite3@11.10.0` (dev/test)
- **Driver:** PowerSync web SDK handles WASM SQLite in production
- **Schema Mirror:** `lib/drizzle/schema.ts` mirrors backend Postgres tables
- **Scope:** Read-only downloaded data (writes go back to backend via PowerSync)

**File Storage:**

- **OFX Files:** Uploaded via multipart to `/imports/ofx/preview` and `/imports/ofx/commit`
  - Not persisted to disk; parsed in-memory
  - Size limit enforced at HTTP layer (`_enforce_size_cap`, max 26 MB)
- **Secure Storage (Mobile):** `@aparajita/capacitor-secure-storage@8.0.0`
  - Stores JWT tokens securely on iOS/Android
  - Web fallback: `localStorage` (see `backend/lib/storage/` and S14.5 notes)

**Caching:**

- **Server-side:** None detected (no Redis/Memcached)
- **Client-side:** PowerSync local SQLite database serves as cache
- **HTTP layer:** No HTTP caching headers configured (stateless auth via JWT)

## Authentication & Identity

**Auth Provider:**
- **Type:** Custom JWT-based (no external IdP in current scope)
- **Implementation:** `backend.modules.auth.*`

**JWT (JSON Web Tokens):**
- **Signing Algorithm:** HS256 (HMAC SHA256) by default
- **Secret:** `JWT_SECRET` environment variable
  - Dev default (published): `dev-secret-change-me` (rejected in prod, ADR 0016)
  - Must be overridden in production
- **Audience Pinning:** `JWT_AUDIENCE` (default `prosperity-api`)
  - Distinguishes access tokens from refresh-token HMAC (ADR 0016)
- **Issuer:** `JWT_ISSUER` (default `prosperity-auth`)
- **Access Token TTL:** `JWT_ACCESS_TTL_SECONDS` (default 900 seconds = 15 min)
- **Refresh Token TTL:** `REFRESH_TOKEN_TTL_SECONDS` (default 30 days)
- **SSE Token Audience:** `JWT_SSE_AUDIENCE` (default `prosperity-sse`, TTL 5 min for short-lived stream tokens)
- **Implementation:** `backend.modules.auth.service.refresh_tokens`, `pyjwt[crypto]@2.10`

**Password Hashing:**
- **Algorithm:** Argon2id (via `pwdlib[argon2]@0.2.1`)
- **Scheme:** Secure password storage, no plaintext or MD5
- **Environment Bootstrap:** `INITIAL_ADMIN_PASSWORD_HASH` (pre-computed hash, never plaintext)

**Session Management:**
- **Store:** Refresh tokens persisted in `refresh_tokens` table
- **Rotation:** JWT secret rotation invalidates all persisted refresh tokens (planned forced re-login)
- **Security:** Refresh token hash stored as HMAC pepper, ADR 0016

## Monitoring & Observability

**Error Tracking:**
- **Service:** None detected (no Sentry, Rollbar, or similar integration)

**Logging:**
- **Approach:** Standard Python logging + FastAPI built-in
- **Access Logs:** Uvicorn default ASGI access logging
- **Application Logs:** Python stdlib `logging` module
- **PowerSync Logs:** Controlled via `PS_LOG_LEVEL` environment variable
  - Development: `info` level (never `debug` in prod — logs contain PII/payloads)
- **Format:** Plain text (no structured JSON logging detected)

**Monitoring:**
- **Health Check Endpoint:** `GET /healthz` (simple "ok" response, `backend/main.py`)
- **PowerSync Probes:** Liveness check via HTTP health probe in compose
- **Database Connectivity:** Testcontainers used in CI to verify DB availability

## CI/CD & Deployment

**Hosting:**

- **Planned Production:** Quadlet + Caddy + Cloudflare Tunnel (E16, not yet implemented)
- **Current Dev:** Local Docker Compose (`compose.dev.yml`) or Podman
- **Platform:** Linux container (Alpine Postgres image: `postgres:17-alpine`)

**CI Pipeline:**

**GitHub Actions (`.github/workflows/`)**
- **Push Workflow:** `.github/workflows/push.yml` (on PR, push to main, or `workflow_dispatch`)
  - Path-filtered jobs: `backend-lint`, `backend-unit`, `backend-integration`, `backend-sync`, `backend-migrations`
  - Status checks: `ci-required` is the single required check (stable even when jobs skip)
  - Concurrency: Cancels in-progress runs for the same branch/PR
- **Nightly Workflow:** `.github/workflows/nightly.yml` (daily cron + manual dispatch)
  - Property tests with `HYPOTHESIS_PROFILE=nightly` (500 examples)
  - `pip-audit` for dependency vulnerabilities
  - Full test coverage upload
  - Placeholders: Playwright E2E, Enable Banking level C
- **Action Helpers:** `.github/actions/setup-node-cached/` (caches npm dependencies)

**Job Details:**

| Job | Triggers | Commands |
|-----|----------|----------|
| `backend-lint` | Backend changes | `ruff check`, `ruff format --check`, `pyright`, `lint-imports` |
| `backend-unit` | Backend changes | `pytest` (unit tests only) |
| `backend-integration` | Backend changes | `pytest` (integration with testcontainers Postgres) |
| `backend-migrations` | DB/migrations changes | `alembic upgrade head` verification |
| `ci-selftest` | All pushes | `actionlint`, YAML validation, `decide.sh` unit tests |

**Versioning:**
- **Application:** No explicit version field (uses commit SHAs)
- **PowerSync Service Image:** Pinned via `PS_IMAGE_TAG` (manifest test asserts no `:latest`)
- **Database Migrations:** Alembic versioning (sequential, tracked in DB)

## Environment Configuration

**Required Environment Variables:**

**Backend (Python):**
- `APP_ENV` - Runtime env (`dev`, `test`, `prod`); prod mode forbids dev defaults
- `DATABASE_URL` - Async SQLAlchemy DSN (must override in prod)
- `JWT_SECRET` - HS256 signing key (must override in prod)
- `JWT_AUDIENCE` - Access token audience (default `prosperity-api`)
- `JWT_ISSUER` - Token issuer claim (default `prosperity-auth`)
- `JWT_ACCESS_TTL_SECONDS` - Access token lifetime in seconds (default 900)
- `JWT_SSE_AUDIENCE` - SSE stream token audience (default `prosperity-sse`)
- `SSE_HEARTBEAT_SECONDS` - SSE server heartbeat period (default 30.0)
- `REFRESH_TOKEN_TTL_SECONDS` - Refresh token lifetime in seconds (default 2,592,000 = 30 days)
- `APP_BASE_URL` - Public base URL for invitation links (default `http://localhost:8000`)
- `INITIAL_ADMIN_EMAIL` - Email for auto-bootstrap admin (optional, pairs with password hash)
- `INITIAL_ADMIN_PASSWORD_HASH` - Argon2id hash for bootstrap admin (never plaintext)
- `INITIAL_ADMIN_DISPLAY_NAME` - Display name for bootstrap admin (default `Admin`)
- `INITIAL_HOUSEHOLD_NAME` - Household name for bootstrap (default `Foyer`)
- `TRUSTED_PROXY_IPS` - CSV of CIDR networks whose X-Forwarded-For is trusted (empty by default)

**PowerSync (Dev/Docker):**
- `PS_IMAGE_TAG` - PowerSync Service Docker image tag (pinned, never `latest`)
- `PS_PORT` - PowerSync API server port (e.g., 8080)
- `PS_SOURCE_URI` - PostgreSQL replication connection (e.g., `postgresql://powersync@localhost:5432/prosperity`)
- `PS_STORAGE_URI` - PowerSync bucket storage DB connection (e.g., `postgresql://ps_storage@localhost:5432/powersync_storage`)
- `PS_JWKS_URI` - Client JWT JWKS endpoint (dev placeholder, real one in S13.8/E14)
- `PS_ADMIN_TOKEN` - Local admin API token for PowerSync diagnostics (dev only)
- `PS_LOG_LEVEL` - Log level for PowerSync Service (`info` recommended, never `debug` in prod)

**Client (JavaScript/Environment Variables):**
- `VITE_*` prefixed only (inlined at build time, public values only)
- No secret API keys should be in client environment

**Secrets Location:**
- **Development:** `.env` file (git-ignored, see `.gitignore`)
- **Production:** Environment variables injected at runtime (managed by container orchestration)
- **Postgres credentials:** In `DATABASE_URL` (secret); replicated role password in `PS_SOURCE_URI` (secret)
- **JWT secret:** In `JWT_SECRET` (secret)

## Webhooks & Callbacks

**Incoming Webhooks:**
- PowerSync bucket updates: PowerSync Service pushes via WebSocket-like channel (not traditional HTTP webhooks)
- No external webhook subscriptions detected

**Outgoing Webhooks:**
- None detected
- OFX import is pull-based (client uploads file), not push from banks

**Real-Time Updates:**
- **SSE (Server-Sent Events):** `backend.modules.sse.transports.http.sse_router`
  - Route: `GET /sync/subscribe` with short-lived JWT token
  - Purpose: Push transaction confirmations and sync events to connected clients
  - Token Format: `Authorization: Bearer <JWT_TOKEN>`
  - TTL: 5 minutes (shorter than access token to limit token exposure in query string)
  - Heartbeat: Every 30 seconds (below Cloudflare's 100-second idle timeout, ADR 0012)

---

*Integration audit: 2026-09-02*
