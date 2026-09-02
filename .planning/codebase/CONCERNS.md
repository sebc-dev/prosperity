# Codebase Concerns

**Analysis Date:** 2026-09-02

## Tech Debt

### Missing Rate Limiting on Auth Endpoints

**Issue:** Three authentication endpoints lack rate limiting by client IP, creating a vector for brute force attacks and spam.

**Files:** `backend/modules/auth/transports/http.py` (lines 104, 157, 190)

**Impact:** 
- `/auth/login` can be attacked with credential stuffing
- `/auth/refresh` can be exploited to spam token rotation 
- `/auth/logout` can be abused to revoke tokens in a denial-of-service pattern

**Fix approach:** Implement rate limiting middleware using client IP + endpoint identifier. Consider per-email rate limits for login (harder to DOS individual accounts) and per-IP/token-hash for refresh/logout. Story S02.5 planned for this.

---

### Budget Period Carryover Unimplemented

**Issue:** The `Budget.carry_over_remainder` flag is stored in the DB but never read by consumption calculations.

**Files:** `backend/modules/budget/models.py` (line 140)

**Impact:** Budget remainder from one period is lost when a new period begins instead of rolling forward. Users cannot track unused budget allocations across months.

**Fix approach:** Implement rollover logic in budget consumption calculator (`budget.service.consumption`). Story E11+ tracks this. Until then, users cannot use this feature and the column is effectively dead code.

---

### Frontend Coverage Thresholds Disabled

**Issue:** Vite coverage configuration has commented-out thresholds that should be enforced when test folders mature.

**Files:** `client/vite.config.ts` (lines 56-60)

**Impact:** No automated enforcement of test coverage targets. Coverage can regress silently. Business and layout components need 75% lines coverage; features need 65%.

**Fix approach:** Uncomment thresholds in S14.7 once test coverage reaches targets. Until then, coverage is advisory only.

---

### Incomplete Backend Public Surfaces

**Issue:** Some dependency-injection guards (`require_admin`, `require_member`) were not re-exported from `auth.public`, forcing cross-module code to import from internals (`auth.dependencies`).

**Files:** `backend/modules/auth/public.py`

**Impact:** Import-linter contracts require using `.public` surfaces, but the contracts must explicitly whitelist internal imports. This creates brittle `ignore_imports` rules and couples other modules to auth internals.

**Fix approach:** Re-export guards from `auth.public` (S19.3). Reduces import-linter complexity and clarifies the public API surface.

---

## Known Bugs

### Offline-First Sync Convergence Edge Cases

**Issue:** PowerSync sync rules for multi-bucket scenarios with column-level filtering (debt visibility masking, budget contributor routing) may have untested edge cases under concurrent operations.

**Files:** `backend/modules/sync/handlers/` (sync processors), `powersync/sync_rules.yaml` (bucket definitions)

**Impact:** Offline-first models can diverge from server ground-truth if client and server conflict on bucket routing, especially with shared-account overflow debts where visibility rules differ between channels (REST masking vs. sync delta).

**Workaround:** S13.9 added property-based testing with Hypothesis to validate sync invariants (convergence, idempotence, isolation). Continue fuzzing with edge cases around debt visibility and account member changes.

---

## Security Considerations

### 2FA Reset Access Control

**Issue:** 2FA recovery codes and TOTP reset require physical DB access or secrets management, but the architectural decision to forbid admin-initiated 2FA resets via the app creates friction for users who lose both codes and access.

**Files:** `backend/modules/auth/models.py`, docs/adr/0013-2fa-totp-and-pat-stepup.md

**Impact:** User lockout is permanent without manual database intervention. No self-service recovery path beyond recovery codes.

**Current mitigation:** 
- 10 recovery codes generated at 2FA enrollment (single-use, user-displayable once)
- Recovery codes can reset TOTP
- Documented manual reset procedure in runbook for admin access

**Recommendations:** 
- Ensure recovery codes are printed/backed up during enrollment (UX check)
- Build user-initiated TOTP re-enrollment flow (requires re-validation of password/2FA context)
- Monitor for "forgot recovery codes" support requests post-launch

---

### Offline-First Data Exposure via Sync Channels

**Issue:** PowerSync's column-level filtering masks `source_transaction_id` and `account_id` from debtors viewing personal-account share requests, but the two-channel approach (REST + sync delta) assumes perfect column-list enforcement.

**Files:** `backend/modules/sync/handlers/`, `powersync/sync_rules.yaml`, ADR 0003 decision notes

**Impact:** If Postgres publication column-list is misconfigured or sync rules diverge from REST masking logic, debtors could leak sensitive account/transaction IDs via the sync channel.

**Current mitigation:**
- Column-list on Postgres publication (`materialization_trace` explicitly excluded)
- GRANT table-level (column-level GRANT breaks PowerSync's initial snapshot)
- Sync rules use explicit `NULL AS` projections to avoid exposing masked columns
- REST (`/debts` endpoint) independently masks both columns

**Recommendations:**
- Test: write end-to-end scenario where debtor syncs personal share requests and verify masked columns stay NULL
- Integration test: trigger column-list mismatch and verify sync rule still masks correctly
- Monitor: audit logs for any attempts to access masked columns via REST or sync

---

### Password Hash Timing Attack Mitigation

**Issue:** Login endpoint uses a pre-computed dummy hash to equalize timing between "user not found" and "wrong password" cases, but the dummy value is process-local and regenerated per deployment.

**Files:** `backend/modules/auth/transports/http.py` (lines 72-86)

**Impact:** The approach is sound (constant hash within a process, random across processes), but an attacker could potentially fingerprint hash values if memory is dumped and correlate with process uptime.

**Current mitigation:**
- Pre-computed Argon2id hash of random `secrets.token_urlsafe(32)` per process
- Hash regenerated on each process restart
- Timing verified to match real password hash verification

**Recommendations:**
- Document this in security runbook as "user enumeration resistant"
- Test: measure login response times for user-not-found vs. wrong-password to confirm parity (already in `test_auth_routes_login.py`)

---

## Performance Bottlenecks

### Large Test Files

**Issue:** Several integration test files exceed 1000 lines, creating maintenance friction and slow test discovery/execution.

**Files:**
- `tests/integration/test_overflow_materializer.py` (1408 lines)
- `tests/integration/test_budget_reclassement.py` (1273 lines)
- `tests/integration/test_settlement_routes.py` (1076 lines)
- `tests/strategies.py` (1083 lines — property-based test strategies)

**Impact:** 
- Hard to navigate and understand test intent
- Slow test collection/run in CI
- Increased chance of test pollution between unrelated scenarios

**Improvement path:**
- Split by feature/scenario (overflow materialization has budget context + debt calc + settlement — 3 concerns)
- Extract `strategies.py` scenarios into smaller helper modules per domain
- Consider pytest parametrization or hypothesis composite strategies to reduce duplication

---

### Budget Consumption Query Complexity

**Issue:** Budget consumption calculation (`budget.service.consumption`) aggregates splits across transaction trees with category inheritance and contributor filtering—queries may not scale to large transaction volumes without proper indexing.

**Files:** `backend/modules/budget/service/consumption.py`, `backend/modules/budget/domain.py`

**Impact:** Dashboard and budget detail views execute complex aggregations; large households with years of history may see slow load times.

**Current mitigation:**
- Indexes exist on `splits.account_id`, `splits.category_id`, `splits.transaction_id`
- Partial indexes on active (non-voided) transactions

**Recommendations:**
- Query plan review when transaction count exceeds 50K
- Consider materialized view or read-model table for common aggregations
- Monitor slow query logs in production

---

### PowerSync Snapshot Latency on Large Datasets

**Issue:** PowerSync's initial sync snapshot (`SELECT * FROM [bucket tables]`) fetches entire table contents for a user. With millions of splits across shared accounts and years of history, snapshot latency could exceed acceptable limits.

**Files:** `backend/modules/sync/handlers/`, PowerSync backend configuration

**Impact:** First-time login or app reinstall could stall client if household has large transaction history.

**Current mitigation:**
- Bucket partitioning by account and user reduces per-bucket size
- Partial indexes help reduce rows scanned
- Test fixtures use small datasets (< 1000 transactions)

**Recommendations:**
- Load test: sync snapshot latency with 100K+ transactions per account
- Consider delta-only sync after initial snapshot (requires tracking client checkpoint)
- Paginate snapshots if latency exceeds 5 seconds

---

## Fragile Areas

### Budget-Transactions Cycle (Partially Fixed)

**Issue:** The budget module imports from transactions indirectly to calculate consumption (splits belong to transactions), and transactions may import categories from budget. This creates a latent circular dependency managed only by careful service-layer isolation.

**Files:** 
- `backend/modules/budget/service/consumption.py` (queries transactions.splits)
- `backend/modules/transactions/models.py` (links to categories)

**Impact:** Future refactoring to expose budget queries or tighten module boundaries could reintroduce the cycle if import discipline isn't maintained.

**Fix approach:** S19.1 extracted `_budget_queries.py` to centralize split/transaction reads in the budget module, reducing reliance on service-layer imports. The cycle is no longer imported at module load time (only at query execution), but remains a structural concern.

**Safe modification:** When adding new budget × transaction interactions:
1. Route reads through `budget.service.queries` functions only
2. Never import `transactions.service` or `transactions.models` from budget (except in queries)
3. Verify with `lint-imports` before committing

---

### PowerSync Column Masking Maintenance

**Issue:** The sync rules apply column-level filtering to mask sensitive debt fields from debtors, but the logic lives in two places (YAML sync rules + REST endpoint masking). Divergence could expose data.

**Files:**
- `powersync/sync_rules.yaml` (sync rule projections)
- `backend/modules/debts/transports/http.py` (REST masking logic)

**Impact:** If sync rules are updated without updating REST endpoints (or vice versa), the two channels could return different data for the same query, breaking client assumptions.

**Safe modification:**
1. Treat sync rules and REST masking as co-dependents—test both channels return identical results
2. Add integration test: fetch same data via REST and sync, compare masked fields
3. Document masking decision in code comments (why `NULL AS account_id` vs. omitting the column)

---

### Migration-Heavy Operations on Household Creation

**Issue:** Initial admin bootstrap (S03.1) creates user, account, household, and sets up categories in a single transaction. If any step fails, the entire setup rolls back, requiring manual intervention.

**Files:** `backend/modules/accounts/service/setup.py`, `backend/modules/auth/transports/http.py` (POST /setup)

**Impact:** Setup failures leave partial state in DB (no recovery or retry flow). Users cannot recover without admin intervention.

**Workaround:** Web UI handles errors gracefully and guides retry. Env var bootstrap for restore-from-backup is not exposed via app (manual SQL only).

**Recommendations:**
- Add idempotency keys to POST /setup (detect replayed requests)
- Document setup state machine (uninitialized → partial → complete)
- Test: force failure at each step and verify rollback is clean

---

## Scaling Limits

### Single Household Per Deployment

**Issue:** The design mandates one foyer per deployment (`household` singleton with CHECK constraint on UUID). Multi-household architectures would require significant refactoring.

**Files:** `backend/modules/accounts/models.py`, CONTEXT.md ("Foyer" section)

**Impact:** Scaling beyond one household requires separate database/deployment per household. SaaS multi-tenancy is not supported by current architecture.

**Scaling path:** Post-V1 multi-tenancy would require:
1. Remove CHECK constraint and add `household_id` to all tables (migration)
2. Refactor auth context to include household + user
3. Rebuild sync rules and PowerSync routing
4. Redeploy as SaaS with isolated schemas or row-level security

---

### OFX Import Transaction Size Cap

**Issue:** OFX file parsing loads the entire import into memory before deduplication and preview. Large files (100K+ transactions) could exhaust memory or timeout.

**Files:** `backend/modules/banking/service/import_ofx.py`

**Impact:** Bulk imports of historical data (e.g., 5 years of monthly bank exports) could fail if aggregated into a single file.

**Workaround:** Split imports into monthly chunks manually.

**Improvement path:**
- Stream OFX parsing (avoid loading entire document in memory)
- Paginate preview/preview API (fetch results in chunks)
- Add import size limit with helpful error message

---

## Dependencies at Risk

### `ofxparse` Maintenance

**Issue:** `ofxparse` is a low-maintenance package (last release 2021) used for OFX parsing. No major issues, but library risk is moderate.

**Files:** `backend/modules/banking/service/import_ofx.py`, `pyproject.toml`

**Impact:** If ofxparse breaks with Python 3.13+ updates or bank OFX format changes, switching libraries would require rewriting OFX parsing logic.

**Migration plan:** 
- Monitor for ofxparse issues on GitHub
- Keep test fixtures for OFX parsing robust (already done in S12.5)
- Alternative: OFXpy (more recent), but API is different

---

### PowerSync Self-Hosted Complexity

**Issue:** PowerSync backend is self-hosted via Docker Compose in development, but production deployment complexity and scaling are not yet tested.

**Files:** `backend/modules/sync/` (handler), `compose.yml` (dev setup)

**Impact:** Production sync failures could lock users out of offline-first updates. Debugging production PowerSync issues requires access to both PostgreSQL replication logs and PowerSync broker logs.

**Current mitigation:** S13.1 validates basic self-hosted setup in dev. E16+ deployment work will test scaling.

**Recommendations:**
- Document PowerSync monitoring setup (replication lag, broker health)
- Set up alerts for sync lag > 30s
- Test failover scenario (restart PowerSync broker without data loss)

---

## Missing Critical Features

### Admin-Initiated 2FA Recovery

**Issue:** No in-app mechanism for admins to reset a user's TOTP or provide new recovery codes. Users who lose access to both TOTP device and recovery codes are permanently locked out.

**Files:** `backend/modules/auth/models.py`, ADR 0013

**Impact:** Blocks real household usage in production (family members will forget recovery codes).

**Workaround:** Manual database reset (documented in runbook, requires admin access).

**Blocks:** Production deployment without documented recovery procedure and user education.

---

### Bulk Transaction Categorization

**Issue:** No batch endpoint to reclassify multiple transactions at once. Users must click-to-edit each transaction individually.

**Files:** `backend/modules/transactions/transports/http.py`

**Impact:** Recategorizing 50+ transactions after linking a new bank account is tedious.

**Blocks:** User experience friction post-import (workflows like "recategorize all groceries from Aug–Sep").

---

## Test Coverage Gaps

### Backend Coverage Not Enforced

**What's not tested:** While integration test coverage is extensive (124 test files, 1900+ test cases), no enforced threshold prevents regressions.

**Files:** `pyproject.toml` (coverage config), `tests/`

**Risk:** Refactoring critical paths (auth, settlement, debt calculation) without test coverage could introduce bugs silently.

**Priority:** HIGH

**Mitigation approach:**
- Measure actual coverage baseline
- Set threshold to current baseline + 2% (enforce upward trajectory)
- Run coverage CI gate on PR

---

### Reconciliation Module Empty (Stub)

**What's not tested:** Full reconciliation flow (bank transaction matching, multi-match scoring) is designed (ADR 0006) but not implemented. Stub module exists in import graph but contributes nothing.

**Files:** `backend/modules/reconciliation/` (empty except `__init__.py`)

**Risk:** Reconciliation logic will be built without tests or may be implemented incorrectly when E12+ delivers it.

**Blocks:** E08.5 (canonical expense reconciliation).

---

### PowerSync Edge Cases Under Concurrency

**What's not tested:** Scenarios where two clients upload mutations to the same transaction/budget concurrently, or where a user is removed from a shared account while sync is in flight.

**Files:** `backend/modules/sync/handlers/`, `tests/integration/sync/`

**Risk:** Race conditions could corrupt sync state or cause divergence between clients.

**Priority:** MEDIUM (S13.9 addressed idempotence; edge cases remain).

**Approach:**
- Add property-based tests for concurrent bucket mutations
- Add integration test: remove user from account while client syncs that account's mutations
- Verify PowerSync handles conflict resolution correctly (server wins)

---

### Offline-First Conflict Resolution

**What's not tested:** PowerSync conflict resolution when client and server have conflicting writes to the same row (LWW = server wins, but client state may be stale).

**Files:** `client/src/lib/powersync/` (client hooks), `backend/modules/sync/handlers/` (server-side)

**Risk:** UI could show outdated values after a conflict, confusing users.

**Priority:** MEDIUM

**Approach:**
- Write integration test: client edits transaction while server voids it
- Verify client receives server version and UI reflects correct state
- Test with multiple clients editing same budget concurrently

---

## Architectural Observations

### Module Stub Cleanup Complete

**Status:** RESOLVED (S19.2)

Five stub modules (`forecasting`, `mcp`, `notifications`, `reconciliation`, `savings`) have been removed from the import graph. These were placeholders to satisfy layer contracts but were never implemented. Their removal simplified the directional graph and reduced noise in import-linter configuration.

---

### Import-Linter Contracts Well-Maintained

**Status:** HEALTHY

Seven `forbidden` contracts + three `layers` contracts + reader/provider split actively prevent modules from reaching into internals. Coverage test (`test_importlinter_coverage.py`) ensures all modules are accounted for. Unmatched ignore imports trigger errors, preventing silent contract rot.

---

---

*Concerns audit: 2026-09-02*
