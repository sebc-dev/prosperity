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
| 01-01 T1 | 01 | 1 | INFR-04, INFR-05, INFR-06, INFR-07, INFR-08 | build | `cd backend && ./mvnw verify -B` | pending |
| 01-02 T1 | 02 | 2 | INFR-06 | build | `cd backend && ./mvnw compile` | pending |
| 01-03 T1 | 03 | 3 | INFR-06 | build | `cd backend && ./mvnw compile` | pending |
| 01-04 T1 | 04 | 4 | INFR-06 | integration | `cd backend && ./mvnw flyway:validate` | pending |
| 01-05 T1 | 05 | 4 | INFR-07 | unit | `cd backend && ./mvnw test` | pending |
| 01-06 T1 | 06 | 1 | INFR-04, INFR-05 | build | `cd frontend && pnpm build && pnpm lint` | pending |
| 01-07 T1 | 07 | 2 | INFR-02 | config | `docker compose config` | pending |
| 01-07 T2 | 07 | 2 | INFR-10 | config | `grep -q "pre-commit" lefthook.yml && grep -q "mvnw verify" .github/workflows/ci.yml` | pending |

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
