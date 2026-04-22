---
phase: 6
slug: envelope-budgets
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-22
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | JUnit 5 / Testcontainers 2.0 (backend) + Vitest (frontend) |
| **Config file** | `backend/pom.xml`, `frontend/vitest.config.ts` |
| **Quick run command** | `./mvnw -pl backend test -Dtest='Envelope*Test'` (backend) / `pnpm -C frontend test -- envelope` (frontend) |
| **Full suite command** | `./mvnw verify` + `pnpm -C frontend test` + `pnpm -C frontend lint` |
| **Estimated runtime** | ~45s backend slice, ~15s frontend slice, ~180s full verify |

---

## Sampling Rate

- **After every task commit:** Run the quick slice for the affected surface (`mvnw -Dtest='...'` or `pnpm test -- ...`)
- **After every plan wave:** Run the full module suite (`./mvnw -pl backend test` or `pnpm -C frontend test`)
- **Before `/gsd:verify-work`:** Full suite must be green (`./mvnw verify` + frontend tests + lint)
- **Max feedback latency:** 45 seconds for quick slice, 180 seconds for full verify

---

## Per-Task Verification Map

*To be filled by planner — every `<task>` in PLAN.md must map to a row here with automated command and file status.*

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | ENVL-01 | migration | `./mvnw -pl backend test -Dtest=FlywayMigrationTest` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` — stubs for ENVL-01..ENVL-07 (CRUD, scope derivation, access control, D-01 uniqueness, consumed, rollover, status)
- [ ] `backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java` — Testcontainers integration stubs (403 vs 404, DTO serialization, access inheritance)
- [ ] `backend/src/test/java/com/prosperity/envelope/EnvelopeAllocationServiceTest.java` — stubs for D-08/D-10 overrides
- [ ] `backend/src/test/java/com/prosperity/envelope/EnvelopeConsumedAggregationTest.java` — stubs for recursive CTE consumed (D-11, D-03 splits, D-02 hierarchy)
- [ ] `backend/src/test/java/com/prosperity/envelope/EnvelopeRolloverTest.java` — stubs for D-12 lazy formula (RESET vs CARRY_OVER, zero-clamp)
- [ ] `frontend/src/app/envelopes/envelopes.spec.ts` — list page test stubs (filter by account, status badges)
- [ ] `frontend/src/app/envelopes/envelope-dialog.spec.ts` — dialog test stubs (multi-category binding, scope read-only)
- [ ] `frontend/src/app/envelopes/envelope-details.spec.ts` — history page test stubs (12-month table)
- [ ] `frontend/src/app/envelopes/envelope.service.spec.ts` — HttpClient signal service stubs

*Planner will finalize Wave 0 scope and link each missing file to the task that creates it.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Status badge colour contrast on dark/light themes | ENVL-05 | Visual/UX review, not deterministic | Run dev server, open `/envelopes`, verify green/yellow/red tags at 50%/85%/110% ratios |
| Sidebar navigation discoverability | ENVL-01 | UX only | Verify `Enveloppes` entry appears in sidebar with active-route highlight |
| Empty-state copy & CTA | ENVL-01, ENVL-06 | Copywriting | Verify "no envelope yet" state on a fresh account exposes the create CTA |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 180s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
