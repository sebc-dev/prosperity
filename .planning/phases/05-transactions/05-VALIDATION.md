---
phase: 5
slug: transactions
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-07
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | JUnit 5 (backend) + Jasmine/Karma (frontend Angular) |
| **Config file** | `pom.xml` (Maven Surefire) / `karma.conf.js` |
| **Quick run command** | `./mvnw test -pl . -Dtest="Transaction*" -q` |
| **Full suite command** | `./mvnw verify -q && pnpm test --watch=false` |
| **Estimated runtime** | ~45 seconds |

---

## Sampling Rate

- **After every task commit:** Run `./mvnw test -pl . -Dtest="Transaction*" -q`
- **After every plan wave:** Run `./mvnw verify -q && pnpm test --watch=false`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 45 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | TXNS-01 | unit | `./mvnw test -Dtest=TransactionServiceTest -q` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | TXNS-01 | integration | `./mvnw test -Dtest=TransactionControllerIT -q` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 1 | TXNS-02 | unit | `./mvnw test -Dtest=RecurringTemplateServiceTest -q` | ❌ W0 | ⬜ pending |
| 05-03-01 | 03 | 2 | TXNS-03 | unit | `./mvnw test -Dtest=TransactionSplitServiceTest -q` | ❌ W0 | ⬜ pending |
| 05-04-01 | 04 | 2 | TXNS-04 | unit | `./mvnw test -Dtest=TransactionReconciliationTest -q` | ❌ W0 | ⬜ pending |
| 05-05-01 | 05 | 3 | TXNS-05 | integration | `./mvnw test -Dtest=TransactionSearchIT -q` | ❌ W0 | ⬜ pending |
| 05-FE-01 | FE | 3 | TXNS-06 | component | `pnpm test --watch=false --include="**/transaction*"` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `src/test/java/.../transaction/TransactionServiceTest.java` — stubs for TXNS-01, TXNS-02
- [ ] `src/test/java/.../transaction/TransactionControllerIT.java` — stubs for TXNS-01 (CRUD REST)
- [ ] `src/test/java/.../transaction/RecurringTemplateServiceTest.java` — stubs for TXNS-02
- [ ] `src/test/java/.../transaction/TransactionSplitServiceTest.java` — stubs for TXNS-03
- [ ] `src/test/java/.../transaction/TransactionReconciliationTest.java` — stubs for TXNS-04
- [ ] `src/test/java/.../transaction/TransactionSearchIT.java` — stubs for TXNS-05
- [ ] `src/app/features/transactions/*.spec.ts` — stubs for TXNS-06 (Angular components)

*Existing Testcontainers + @DataJpaTest infrastructure from Phase 3/4 covers fixtures.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Reconciliation visual indicator (pointer) | TXNS-04 | UI feedback requires human validation | Create tx A manual, tx B imported, reconcile via UI, verify matched pair icon visible |
| Split transaction display in total | TXNS-03 | Balance rollup logic spans UI + backend | Create tx with 3 splits, verify account balance accounts for full amount once |
| Pagination scroll UX | TXNS-05 | p-table lazy loading feel | Search with 50+ transactions, verify smooth page transitions and filter persistence |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 45s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
