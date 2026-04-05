---
phase: 3
slug: accounts-access-control
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-05
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | JUnit 5 (backend) + Jasmine/Jest (frontend) |
| **Config file** | `pom.xml` (backend) / `angular.json` (frontend) |
| **Quick run command** | `./mvnw test -pl . -Dtest="Account*,AccountAccess*" -q` |
| **Full suite command** | `./mvnw verify -q && pnpm test --run` |
| **Estimated runtime** | ~30 seconds (backend unit) / ~60 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run `./mvnw test -Dtest="Account*,AccountAccess*" -q`
- **After every plan wave:** Run `./mvnw verify -q && pnpm test --run`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-xx-01 | DB/Entities | 1 | ACCT-01 | unit | `./mvnw test -Dtest="AccountRepositoryTest"` | ❌ W0 | ⬜ pending |
| 03-xx-02 | Service | 1 | ACCT-01,ACCS-01 | unit | `./mvnw test -Dtest="AccountServiceTest"` | ❌ W0 | ⬜ pending |
| 03-xx-03 | Controller | 2 | ACCT-02,ACCS-02 | integration | `./mvnw test -Dtest="AccountControllerTest"` | ❌ W0 | ⬜ pending |
| 03-xx-04 | Access Mgmt | 2 | ACCS-01,ACCS-03 | integration | `./mvnw test -Dtest="AccountAccessTest"` | ❌ W0 | ⬜ pending |
| 03-xx-05 | Frontend | 3 | ACCT-03,ACCT-04 | unit | `pnpm test --run --reporter=verbose` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `src/test/java/.../account/AccountRepositoryTest.java` — stubs ACCT-01, ACCS-01
- [ ] `src/test/java/.../account/AccountServiceTest.java` — stubs ACCT-01 à ACCT-05
- [ ] `src/test/java/.../account/AccountControllerTest.java` — stubs ACCS-01 à ACCS-04
- [ ] `src/app/features/accounts/*.spec.ts` — stubs Angular component tests

*Existing test infrastructure (JUnit 5 + Spring Boot Test) already in place from Phase 2.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| UI access control visual (badges permission) | ACCS-02 | CSS/visual, non automatisable | Vérifier que les badges READ/WRITE/ADMIN s'affichent correctement dans la liste comptes |
| Archive masquage UI | ACCT-05 | État UI conditionnel | Vérifier que les comptes archivés n'apparaissent pas dans la liste par défaut |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
