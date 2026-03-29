---
phase: 1
slug: project-foundation
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-28
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | JUnit 5/6 (via spring-boot-starter-test) + Karma/Jest (Angular) |
| **Config file** | `pom.xml` (backend) / `angular.json` (frontend) |
| **Quick run command** | `./mvnw test -pl backend` |
| **Full suite command** | `./mvnw verify && pnpm test && pnpm lint` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `./mvnw test -pl backend`
- **After every plan wave:** Run `./mvnw verify && pnpm test && pnpm lint`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| 01-01 T1 | 01 | 1 | INFR-04, INFR-05, INFR-06, INFR-07, INFR-08, INFR-09 | build | `cd backend && ./mvnw verify -q 2>&1 \| tail -10` | pending |
| 01-02 T1 | 02 | 2 | INFR-07 | build | `cd backend && ./mvnw compile -q 2>&1 \| tail -5` | pending |
| 01-03 T1 | 03 | 3 | INFR-07 | build | `cd backend && ./mvnw compile -q 2>&1 \| tail -5` | pending |
| 01-04 T1 | 04 | 4 | INFR-07 | build | `cd backend && ./mvnw compile -q 2>&1 \| tail -5` | pending |
| 01-05 T1 | 05 | 5 | INFR-07 | build | `cd backend && ./mvnw compile -q 2>&1 \| tail -5` | pending |
| 01-06 T1 | 06 | 1 | INFR-04, INFR-05 | build | `cd frontend && pnpm lint 2>&1 \| tail -3 && pnpm format:check 2>&1 \| tail -3 && pnpm build 2>&1 \| tail -5` | pending |
| 01-07 T1 | 07 | 5 | INFR-07 | build | `cd backend && ./mvnw compile -q 2>&1 \| tail -5` | pending |
| 01-08 T1 | 08 | 6 | INFR-06 | config | `ls -la backend/src/main/resources/db/migration/V00*.sql 2>&1 && wc -l backend/src/main/resources/db/migration/V00*.sql` | pending |
| 01-09 T1 | 09 | 6 | INFR-07 | unit | `cd backend && ./mvnw test -pl . -Dtest="MoneyTest,TransactionStateTest,EnvelopeTest" -q 2>&1 \| tail -10` | pending |
| 01-10 T1 | 10 | 6 | INFR-07 | unit | `cd backend && ./mvnw test -pl . -Dtest="ArchitectureTest" -q 2>&1 \| tail -10` | pending |
| 01-11 T1 | 11 | 6 | INFR-07 | unit | `cd backend && ./mvnw test -pl . -Dtest="ProsperityApplicationTest" -q 2>&1 \| tail -10` | pending |
| 01-12 T1 | 12 | 2 | INFR-02 | config | `docker compose config 2>&1 \| tail -3` | pending |
| 01-13 T1 | 13 | 3 | INFR-10 | config | `test -f lefthook.yml && grep -q "pre-commit" lefthook.yml && grep -q "java-format" lefthook.yml && grep -q "frontend-lint" lefthook.yml && echo "lefthook.yml: valid" && test -f .github/workflows/ci.yml && grep -q "mvnw verify" .github/workflows/ci.yml && grep -q "pnpm lint" .github/workflows/ci.yml && grep -q "pnpm build" .github/workflows/ci.yml && echo "ci.yml: valid"` | pending |

*Status: pending / green / red / flaky*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Docker Compose full stack | INFR-02 | Requires Docker runtime | Run `docker compose up -d`, verify all 3 containers healthy, curl /api/health |
| Pre-commit hook fires | INFR-10 | Requires git commit trigger | Make a formatting violation, attempt `git commit`, verify hook blocks it |
| CI blocks merge on failure | INFR-10 | Requires GitHub Actions runner | Push branch with lint violation, verify PR check fails |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 not needed -- scaffolding phase creates test infrastructure
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
