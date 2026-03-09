---
phase: 1
slug: foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-09
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (backend)** | JUnit 5 + Testcontainers (via Spring Boot Test) |
| **Framework (frontend)** | Vitest + @testing-library/svelte |
| **Config file (backend)** | `pom.xml` (spring-boot-starter-test) -- Wave 0 |
| **Config file (frontend)** | `vite.config.ts` + `vitest.config.ts` -- Wave 0 |
| **Quick run command (backend)** | `cd prosperity-api && mvn test -pl . -Dtest=AuthServiceTest,AccountServiceTest -q` |
| **Quick run command (frontend)** | `cd prosperity-web && npx vitest run --reporter=verbose` |
| **Full suite command** | `cd prosperity-api && mvn verify -q && cd ../prosperity-web && npx vitest run` |
| **Estimated runtime** | ~30 seconds (backend) + ~10 seconds (frontend) |

---

## Sampling Rate

- **After every task commit:** Backend: `mvn test -q` / Frontend: `npx vitest run`
- **After every plan wave:** Full suite: `mvn verify && npx vitest run`
- **Before `/gsd:verify-work`:** Full suite must be green + Docker Compose smoke test
- **Max feedback latency:** 40 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | INFR-01 | smoke | `docker compose up -d && curl http://localhost:8080/actuator/health` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | INFR-03 | integration | `mvn test -Dtest=SecurityHeadersTest` | ❌ W0 | ⬜ pending |
| 01-01-03 | 01 | 1 | INFR-04 | unit | `mvn test -Dtest=UserServiceTest#passwordBcrypted` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 1 | AUTH-01 | integration | `mvn test -Dtest=AuthControllerTest#loginSuccess` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 1 | AUTH-01 | integration | `mvn test -Dtest=AuthControllerTest#loginFailure` | ❌ W0 | ⬜ pending |
| 01-02-03 | 02 | 1 | AUTH-02 | integration | `mvn test -Dtest=AuthControllerTest#refreshToken` | ❌ W0 | ⬜ pending |
| 01-02-04 | 02 | 1 | AUTH-02 | integration | `mvn test -Dtest=AuthControllerTest#expiredRefresh` | ❌ W0 | ⬜ pending |
| 01-02-05 | 02 | 1 | AUTH-03 | integration | `mvn test -Dtest=AuthorizationTest#adminAccess` | ❌ W0 | ⬜ pending |
| 01-02-06 | 02 | 1 | AUTH-03 | integration | `mvn test -Dtest=AuthorizationTest#standardDenied` | ❌ W0 | ⬜ pending |
| 01-03-01 | 03 | 2 | AUTH-04 | unit | `mvn test -Dtest=UserServiceTest#updateProfile` | ❌ W0 | ⬜ pending |
| 01-03-02 | 03 | 2 | AUTH-05 | unit | `mvn test -Dtest=UserServiceTest#updatePreferences` | ❌ W0 | ⬜ pending |
| 01-03-03 | 03 | 2 | ACCT-01 | integration | `mvn test -Dtest=AccountControllerTest#createPersonal` | ❌ W0 | ⬜ pending |
| 01-03-04 | 03 | 2 | ACCT-01 | integration | `mvn test -Dtest=AccountControllerTest#createShared` | ❌ W0 | ⬜ pending |
| 01-03-05 | 03 | 2 | ACCT-02 | integration | `mvn test -Dtest=AccountControllerTest#personalVisibility` | ❌ W0 | ⬜ pending |
| 01-03-06 | 03 | 2 | ACCT-03 | integration | `mvn test -Dtest=AccountControllerTest#sharedVisibility` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `prosperity-api/pom.xml` -- Maven project with spring-boot-starter-test, Testcontainers PostgreSQL
- [ ] `prosperity-api/src/test/java/.../auth/AuthControllerTest.java` -- covers AUTH-01, AUTH-02
- [ ] `prosperity-api/src/test/java/.../auth/AuthorizationTest.java` -- covers AUTH-03
- [ ] `prosperity-api/src/test/java/.../user/UserServiceTest.java` -- covers AUTH-04, AUTH-05, INFR-04
- [ ] `prosperity-api/src/test/java/.../account/AccountControllerTest.java` -- covers ACCT-01, ACCT-02, ACCT-03
- [ ] `prosperity-api/src/test/java/.../SecurityHeadersTest.java` -- covers INFR-03
- [ ] `prosperity-web/vitest.config.ts` -- Vitest configuration
- [ ] `prosperity-web/src/routes/(auth)/login/login.test.ts` -- Login page component test

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CI pipeline runs on push | INFR-02 | GitHub Actions workflow requires actual push | Check `.github/workflows/` exists with valid CI config |
| Docker Compose starts all services | INFR-01 | Requires Docker runtime | Run `docker compose up -d`, verify all containers healthy |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 40s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
