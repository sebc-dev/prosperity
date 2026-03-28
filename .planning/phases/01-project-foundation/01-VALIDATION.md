---
phase: 1
slug: project-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
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

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | INFR-02 | integration | `docker compose up -d && curl localhost:8080/api/health` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | INFR-04 | unit | `./mvnw test` | ❌ W0 | ⬜ pending |
| 01-01-03 | 01 | 1 | INFR-05 | integration | `./mvnw spring-boot:run` (Flyway auto-migrate) | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 2 | INFR-06 | build | `./mvnw verify` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 2 | INFR-07 | build | `pnpm lint && pnpm format:check` | ❌ W0 | ⬜ pending |
| 01-02-03 | 02 | 2 | INFR-08 | build | `./mvnw verify` (JaCoCo report) | ❌ W0 | ⬜ pending |
| 01-02-04 | 02 | 2 | INFR-09 | hook | `git commit --allow-empty -m test` (lefthook triggers) | ❌ W0 | ⬜ pending |
| 01-02-05 | 02 | 2 | INFR-10 | CI | GitHub Actions workflow validation | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Backend project scaffolded with `spring-boot-starter-test` dependency
- [ ] Frontend project scaffolded with test runner configured
- [ ] Domain model test stubs for Money, Account, Transaction, Envelope

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Docker Compose full stack | INFR-02 | Requires Docker runtime | Run `docker compose up -d`, verify all 3 containers healthy, curl /api/health |
| Pre-commit hook fires | INFR-09 | Requires git commit trigger | Make a formatting violation, attempt `git commit`, verify hook blocks it |
| CI blocks merge on failure | INFR-10 | Requires GitHub Actions runner | Push branch with lint violation, verify PR check fails |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
