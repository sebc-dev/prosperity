---
phase: 6
slug: envelope-budgets
status: draft
nyquist_compliant: false
wave_0_complete: true
created: 2026-04-22
updated: 2026-04-22
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
| 06-01-01 | 01 | 1 | ENVL-01 | migration | `./mvnw -pl backend test -Dtest=ProsperityApplicationTest` | available | pending |
| 06-03-01 | 03 | 1 | ENVL-02..05 | scaffold | `./mvnw -pl backend test-compile` | Plan 03 | pending |
| 06-03-02 | 03 | 1 | ENVL-01,02,06,07 | scaffold | `./mvnw -pl backend test -Dtest='Envelope*Test'` | Plan 03 | pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky (table uses plain ASCII words: `pending`, `green`, `red`, `flaky`, `available`, `Plan 03`)*

---

## Wave 0 Requirements

Consolidated structure (Plan 03 ships these 3 backend scaffolds; frontend specs live in Plan 08 alongside the components they test):

- [x] `backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` — covers Service CRUD, allocation overrides (D-08/D-10), consumed aggregation (D-11, D-03 splits, D-02 hierarchy), rollover (D-12 lazy formula), status thresholds (D-13). Replaces the originally proposed split EnvelopeAllocationServiceTest, EnvelopeConsumedAggregationTest, EnvelopeRolloverTest files. Stubbed @Disabled @Test methods inside this single class cover each former entry:
  - `budget_for_month_without_override_returns_envelope_default_budget`, `budget_for_month_with_override_returns_override_amount` (former EnvelopeAllocationServiceTest)
  - `consumed_sums_negative_transactions_in_linked_categories`, `consumed_includes_transaction_splits_matching_linked_categories`, `consumed_includes_child_category_transactions_when_root_is_linked`, `transaction_in_unlinked_category_does_not_affect_consumed`, `transaction_on_last_day_of_month_included_in_that_month_consumed`, `transaction_on_first_day_of_next_month_excluded_from_previous_month_consumed`, `consumed_for_envelope_without_categories_returns_zero`, `split_parent_with_non_null_category_is_counted_only_via_splits_branch` (former EnvelopeConsumedAggregationTest)
  - `rollover_reset_policy_ignores_previous_month`, `rollover_carry_over_with_positive_previous_remainder_adds_to_available`, `rollover_carry_over_with_negative_previous_remainder_clamps_to_zero`, `rollover_carry_over_lookback_limited_to_one_previous_month` (former EnvelopeRolloverTest)
  - `status_*` (six stubs covering ENVL-05 thresholds + boundary cases) plus `ratio_denominator_includes_carry_over_for_carry_over_envelopes` (D-13 literal denominator)
  - `create_envelope_on_*_account_derives_*`, `create_envelope_with_category_already_linked_*_throws_*`, `update_envelope_can_keep_*`, `same_category_on_two_envelopes_*_is_allowed` (ENVL-01 service slice + D-01)
- [x] `backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java` — Testcontainers integration stubs (403 vs 404, DTO serialization, access inheritance, history endpoint, hard/soft delete, archived filter)
- [x] `backend/src/test/java/com/prosperity/envelope/EnvelopeAllocationControllerTest.java` — monthly override CRUD endpoints (create 201, duplicate 409, 403/404, list ordered by month, delete falls back to default)

Frontend test files are deferred to Plan 08 (Wave 4) because Vitest specs colocate with the component class they test:

- [ ] `frontend/src/app/envelopes/envelopes.spec.ts` — list page test stubs (filter by account, status badges)
- [ ] `frontend/src/app/envelopes/envelope-dialog.spec.ts` — dialog test stubs (multi-category binding, scope read-only, error mapping)
- [ ] `frontend/src/app/envelopes/envelope-details.spec.ts` — history page test stubs (12-month table)
- [ ] `frontend/src/app/envelopes/envelope-allocation-dialog.spec.ts` — monthly override dialog test stubs
- [ ] `frontend/src/app/envelopes/envelope.service.spec.ts` — HttpClient signal service stubs

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Status badge colour contrast on dark/light themes | ENVL-05 | Visual/UX review, not deterministic | Run dev server, open `/envelopes`, verify green/yellow/red tags at 50%/85%/110% ratios |
| Sidebar navigation discoverability | ENVL-01 | UX only | Verify `Enveloppes` entry appears in sidebar with active-route highlight |
| Empty-state copy & CTA | ENVL-01, ENVL-06 | Copywriting | Verify "no envelope yet" state on a fresh account exposes the create CTA |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 180s
- [ ] `nyquist_compliant: true` set in frontmatter (FLIPPED by Plan 08 once `pnpm test -- --run src/app/envelopes` exits 0 with all real assertions; backend bodies are green starting Plan 06)

**Approval:** Wave 0 scaffolding complete (Plan 03). Test bodies pending: backend Plan 06, frontend Plan 08.
