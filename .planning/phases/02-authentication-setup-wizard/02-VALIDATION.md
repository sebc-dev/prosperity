---
phase: 2
slug: authentication-setup-wizard
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-30
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (backend)** | JUnit 5 + AssertJ + Spring Boot Test (via `spring-boot-starter-test`) |
| **Framework (frontend)** | Vitest 4.x (via `@angular/build:unit-test`) |
| **Config file (backend)** | Maven Surefire (default) |
| **Config file (frontend)** | Vitest config embedded in Angular build |
| **Quick run (backend)** | `./mvnw test -Dtest=AuthControllerTest,AuthServiceTest,SecurityConfigTest` |
| **Quick run (frontend)** | `cd frontend && pnpm test` |
| **Full suite command** | `./mvnw verify && cd frontend && pnpm test` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `./mvnw test -Dtest=AuthControllerTest,AuthServiceTest,SecurityConfigTest`
- **After every plan wave:** Run `./mvnw verify && cd frontend && pnpm test`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | AUTH-01 | integration | `./mvnw test -Dtest=AuthControllerTest#setup*` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | AUTH-01 | integration | `./mvnw test -Dtest=AuthControllerTest#setup*already*` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | AUTH-02 | integration | `./mvnw test -Dtest=AuthControllerTest#login*` | ❌ W0 | ⬜ pending |
| 02-01-04 | 01 | 1 | AUTH-02 | integration | `./mvnw test -Dtest=AuthControllerTest#login*invalid*` | ❌ W0 | ⬜ pending |
| 02-01-05 | 01 | 1 | AUTH-03 | integration | `./mvnw test -Dtest=AuthControllerTest#logout*` | ❌ W0 | ⬜ pending |
| 02-01-06 | 01 | 1 | AUTH-04 | integration | `./mvnw test -Dtest=AuthControllerTest#me*` | ❌ W0 | ⬜ pending |
| 02-01-07 | 01 | 1 | AUTH-05 | integration | `./mvnw test -Dtest=SecurityConfigTest#csrf*` | ❌ W0 | ⬜ pending |
| 02-01-08 | 01 | 1 | AUTH-01 | unit | `./mvnw test -Dtest=AuthServiceTest#setup*password*` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 2 | AUTH-02 | unit (Vitest) | `cd frontend && pnpm test` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `AuthControllerTest.java` — integration tests for login/logout/setup/me endpoints (MockMvc + `@SpringBootTest`)
- [ ] `AuthServiceTest.java` — unit tests for setup logic, password validation
- [ ] `SecurityConfigTest.java` — CSRF enforcement, unauthenticated access returns 401
- [ ] `CustomUserDetailsServiceTest.java` — user loading, not-found case
- [ ] Frontend: `auth.service.spec.ts` — login/logout/checkSession
- [ ] Frontend: `auth.guard.spec.ts` — guard redirect logic
- [ ] `spring-security-test` dependency needed in pom.xml

*Note: Test stubs created in Wave 0, implementations filled during execution.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Session persists after browser refresh | AUTH-04 | Requires real browser session | 1. Login 2. Refresh page 3. Verify still authenticated |
| XSRF-TOKEN cookie visible in browser | AUTH-05 | Cookie inspection | 1. Login 2. Open DevTools > Application > Cookies 3. Verify XSRF-TOKEN present |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
