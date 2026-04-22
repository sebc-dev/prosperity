---
phase: 06-envelope-budgets
plan: 03
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java
  - backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java
  - backend/src/test/java/com/prosperity/envelope/EnvelopeAllocationControllerTest.java
  - .planning/phases/06-envelope-budgets/06-VALIDATION.md
autonomous: true
requirements:
  - ENVL-01
  - ENVL-02
  - ENVL-03
  - ENVL-04
  - ENVL-05
  - ENVL-06
  - ENVL-07
must_haves:
  truths:
    - "Wave 0 backend test scaffolds exist as compilable JUnit 5 classes with @Disabled stub methods covering every test row in 06-VALIDATION.md and 06-RESEARCH.md Phase Requirements -> Test Map"
    - "Each scaffold class is annotated with @SpringBootTest, @AutoConfigureMockMvc (controllers only), @ActiveProfiles(test), @Import(TestcontainersConfig.class), @DirtiesContext(AFTER_EACH_TEST_METHOD) — same as TransactionControllerTest"
    - "Plan 06 (Backend Tests) will remove @Disabled and fill in AAA bodies; this plan only ships compilable RED stubs"
    - "06-VALIDATION.md Wave 0 Requirements list aligned with the consolidated 3-file scaffold structure (no longer references EnvelopeAllocationServiceTest, EnvelopeConsumedAggregationTest, EnvelopeRolloverTest as separate files — those concerns live as @Disabled methods inside EnvelopeServiceTest)"
    - "06-VALIDATION.md Per-Task Verification Map references ProsperityApplicationTest (the actual smoke/migration test), not the non-existent FlywayMigrationTest"
    - "06-VALIDATION.md wave_0_complete flag flips to true at the end of Plan 03 (Wave 0 = scaffold creation, body filling is wave 2/3+)"
  artifacts:
    - path: "backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java"
      provides: "Stubs for ENVL-02..05 unit + integration scenarios (consumed, rollover, status, scope derivation, D-01) — also covers former EnvelopeAllocationServiceTest, EnvelopeConsumedAggregationTest, EnvelopeRolloverTest concerns"
      contains: "class EnvelopeServiceTest"
    - path: "backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java"
      provides: "Stubs for ENVL-01, 06, 07 integration scenarios (CRUD, access control, history)"
      contains: "class EnvelopeControllerTest"
    - path: "backend/src/test/java/com/prosperity/envelope/EnvelopeAllocationControllerTest.java"
      provides: "Stubs for ENVL-02 monthly override endpoints"
      contains: "class EnvelopeAllocationControllerTest"
    - path: ".planning/phases/06-envelope-budgets/06-VALIDATION.md"
      provides: "Updated Wave 0 Requirements list + Per-Task Verification Map; wave_0_complete flag set to true after Plan 03"
      contains: "wave_0_complete: true"
  key_links:
    - from: "EnvelopeControllerTest"
      to: "TestcontainersConfig"
      via: "@Import"
      pattern: "@Import\\(TestcontainersConfig\\.class\\)"
    - from: "06-VALIDATION.md Wave 0 Requirements"
      to: "Plan 03 scaffold files"
      via: "1:1 mapping (3 backend files)"
      pattern: "EnvelopeServiceTest\\.java"
---

<objective>
Create Wave 0 backend test scaffolds — compilable JUnit 5 classes with `@Disabled` stub methods covering every requirement→test row in `06-VALIDATION.md` and `06-RESEARCH.md` (Validation Architecture → Phase Requirements → Test Map). The stubs will be FILLED IN with real AAA bodies in Plan 06 (Backend Tests). This plan ONLY ships compilable RED stubs so the rest of Wave 1 has a stable test target file to point `<verify>` blocks at and so Plan 06 doesn't have to scaffold the file structure under context pressure.

Purpose: Resolve the 06-VALIDATION.md `wave_0_complete: false` flag and provide a Nyquist-compliant test surface for downstream plans. Decouples scaffolding from real test writing (which is a separate cognitive load — see 06-RESEARCH.md Validation Architecture).

Output: 3 backend test files compiling cleanly + updated 06-VALIDATION.md (consolidated Wave 0 Requirements list, corrected migration smoke test reference, wave_0_complete: true). All test methods are `@Disabled("Wave 0 stub — body in Plan 06")` so the build remains green.

NOTE: Frontend test scaffolds (`envelopes.spec.ts`, `envelope-dialog.spec.ts`, `envelope-details.spec.ts`, `envelope.service.spec.ts`) are bundled with the frontend implementation in Plan 08 because Vitest specs colocate with the component file and need the component class to import — splitting them off here would create dangling imports.
</objective>

<execution_context>
@/home/negus/dev/prosperity/.claude/get-shit-done/workflows/execute-plan.md
@/home/negus/dev/prosperity/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/06-envelope-budgets/06-CONTEXT.md
@.planning/phases/06-envelope-budgets/06-RESEARCH.md
@.planning/phases/06-envelope-budgets/06-VALIDATION.md
@.claude/rules/testing-principles.md

@backend/src/test/java/com/prosperity/transaction/TransactionControllerTest.java
@backend/src/test/java/com/prosperity/envelope/EnvelopeTest.java

<revision_note>
**Iteration 1 revision (BLOCKER 3, Option A):** Plan 03 ships 3 backend scaffold files (consolidated EnvelopeServiceTest covers former EnvelopeAllocationServiceTest, EnvelopeConsumedAggregationTest, EnvelopeRolloverTest concerns via grouped @Disabled methods). 06-VALIDATION.md Wave 0 Requirements rewritten in Task 3 to match this structure. WARNING 4: ProsperityApplicationTest replaces non-existent FlywayMigrationTest in the Per-Task Verification Map; wave_0_complete: true is the final acceptance step of Task 3 (semantics: Wave 0 = scaffold creation, which IS what Plan 03 delivers; nyquist_compliant flips later when test bodies are green — Plan 06 for backend, Plan 08 for frontend).

**BLOCKER 4 NOT APPLIED (planner judgment):** Checker says replace `org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc` with `org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc`. Verified against the live codebase (UserControllerTest, AuthControllerTest, AccountControllerTest all use the .webmvc.test variant) and against the Spring Boot 4.0.5 jars in ~/.m2: the class lives at `org/springframework/boot/webmvc/test/autoconfigure/AutoConfigureMockMvc.class` in `spring-boot-webmvc-test-4.0.5.jar`; the suggested package does NOT exist in `spring-boot-test-autoconfigure-4.0.5.jar` (only legacy 3.x variants in /3.4.x and /3.5.x). The current import is the correct one for Spring Boot 4.0.x. Applying the checker's suggested fix would break compilation.
</revision_note>

<interfaces>
TestcontainersConfig (com.prosperity.TestcontainersConfig) — provides PostgreSQL Testcontainer used by all integration tests via @Import.

Existing test file pattern (TransactionControllerTest.java):
- @SpringBootTest
- @AutoConfigureMockMvc (from `org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc` — Spring Boot 4.0.x package, NOT the legacy 3.x `org.springframework.boot.test.autoconfigure.web.servlet` location which does not exist in 4.0.5)
- @ActiveProfiles("test")
- @Import(TestcontainersConfig.class)
- @DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
- Autowired MockMvc + repositories
- @BeforeEach setUp seeds testUser/testAccount/testCategory
- Test methods are package-private void with descriptive snake_case names

Test method naming convention (testing-principles.md): scenario_description_and_expected_result, e.g. `create_envelope_on_personal_account_sets_scope_personal_and_owner_current_user`.

Migration smoke test in this codebase: `com.prosperity.ProsperityApplicationTest` (NOT `FlywayMigrationTest`, which does not exist).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: EnvelopeServiceTest scaffold (consumed, rollover, status, scope derivation, D-01) — consolidates former EnvelopeAllocationServiceTest + EnvelopeConsumedAggregationTest + EnvelopeRolloverTest concerns</name>
  <files>backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java</files>
  <read_first>
    - backend/src/test/java/com/prosperity/transaction/TransactionControllerTest.java (canonical test class structure; copy annotations + @BeforeEach pattern verbatim)
    - .planning/phases/06-envelope-budgets/06-RESEARCH.md (Phase Requirements -> Test Map section, lines 757-794: every "EnvelopeServiceTest#..." row maps to a stub method here)
    - .planning/phases/06-envelope-budgets/06-VALIDATION.md (Wave 0 Requirements section: this scaffold is the EnvelopeServiceTest entry — will be rewritten in Task 3)
    - .claude/rules/testing-principles.md (snake_case naming, AAA placeholder)
  </read_first>
  <action>
Create `backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` with the EXACT contents below. This file ONLY contains stubs annotated `@Disabled("Wave 0 stub — body in Plan 06")` so it compiles and runs cleanly while leaving the work for Plan 06.

```java
package com.prosperity.envelope;

import com.prosperity.TestcontainersConfig;
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;

/**
 * Wave 0 RED stubs for the Envelope service layer (Plan 06 fills in the bodies).
 *
 * <p>Coverage map (mirrors 06-RESEARCH.md "Phase Requirements -> Test Map"):
 *
 * <ul>
 *   <li>ENVL-02: default vs override budget resolution (formerly EnvelopeAllocationServiceTest)
 *   <li>ENVL-03: consumed aggregation (transactions + splits + recursive CTE + boundaries + D-04)
 *       — formerly EnvelopeConsumedAggregationTest
 *   <li>ENVL-04: rollover formula (RESET, CARRY_OVER positive, CARRY_OVER negative -> 0, lookback)
 *       — formerly EnvelopeRolloverTest
 *   <li>ENVL-05: status thresholds (GREEN, YELLOW, RED + 80%/100% boundaries)
 *   <li>ENVL-01 service slice: scope derivation from account type, D-01 uniqueness
 * </ul>
 */
@SpringBootTest
@ActiveProfiles("test")
@Import(TestcontainersConfig.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class EnvelopeServiceTest {

  // -------------------------------------------------------------------------
  // ENVL-02 — Budget resolution (override vs default) [former EnvelopeAllocationServiceTest]
  // -------------------------------------------------------------------------

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void budget_for_month_without_override_returns_envelope_default_budget() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void budget_for_month_with_override_returns_override_amount() {}

  // -------------------------------------------------------------------------
  // ENVL-03 — Consumed aggregation [former EnvelopeConsumedAggregationTest]
  // -------------------------------------------------------------------------

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void consumed_sums_negative_transactions_in_linked_categories() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void consumed_includes_transaction_splits_matching_linked_categories() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void consumed_includes_child_category_transactions_when_root_is_linked() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void transaction_in_unlinked_category_does_not_affect_consumed() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void transaction_on_last_day_of_month_included_in_that_month_consumed() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void transaction_on_first_day_of_next_month_excluded_from_previous_month_consumed() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void consumed_for_envelope_without_categories_returns_zero() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void split_parent_with_non_null_category_is_counted_only_via_splits_branch() {}

  // -------------------------------------------------------------------------
  // ENVL-04 — Rollover (RESET, CARRY_OVER, lookback) [former EnvelopeRolloverTest]
  // -------------------------------------------------------------------------

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void rollover_reset_policy_ignores_previous_month() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void rollover_carry_over_with_positive_previous_remainder_adds_to_available() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void rollover_carry_over_with_negative_previous_remainder_clamps_to_zero() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void rollover_carry_over_lookback_limited_to_one_previous_month() {}

  // -------------------------------------------------------------------------
  // ENVL-05 — Status thresholds (boundary values per BVA / D-13)
  // -------------------------------------------------------------------------

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void status_when_consumed_is_zero_returns_green() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void status_when_consumed_below_eighty_percent_returns_green() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void status_at_exactly_80_percent_is_yellow() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void status_at_exactly_100_percent_is_yellow_and_above_is_red() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void status_above_100_percent_returns_red() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void status_when_budget_zero_returns_green_defensively() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void ratio_denominator_includes_carry_over_for_carry_over_envelopes() {}

  // -------------------------------------------------------------------------
  // ENVL-01 service slice — scope derivation + D-01 uniqueness
  // -------------------------------------------------------------------------

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void create_envelope_on_personal_account_derives_scope_personal_and_sets_owner() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void create_envelope_on_shared_account_derives_scope_shared_and_owner_null() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void create_envelope_with_category_already_linked_on_account_throws_duplicate_exception() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void update_envelope_can_keep_its_existing_categories_without_triggering_duplicate_check() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void same_category_on_two_envelopes_on_different_accounts_is_allowed() {}
}
```

Notes:
- No `@AutoConfigureMockMvc` here — service-layer tests use Autowired services, not MockMvc.
- No `@Autowired` fields yet — Plan 06 will add them with the right repositories.
- All names are snake_case scenario_description_and_expected_result per testing-principles.md.
- Two new stubs added (vs original): `split_parent_with_non_null_category_is_counted_only_via_splits_branch` covers BLOCKER 2 dedup behavior; `ratio_denominator_includes_carry_over_for_carry_over_envelopes` covers BLOCKER 1 D-13 literal denominator.
  </action>
  <verify>
    <automated>cd /home/negus/dev/prosperity && ./mvnw -pl backend test-compile -q 2>&1 | tail -10</automated>
  </verify>
  <acceptance_criteria>
    - File `backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` exists
    - `grep -c "@Disabled(\"Wave 0 stub" backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` returns at least 24 (one per @Test method)
    - `grep -c "@Test" backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` returns at least 24
    - `grep -c "void rollover_carry_over_with_negative_previous_remainder_clamps_to_zero" backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` returns 1
    - `grep -c "void status_at_exactly_80_percent_is_yellow" backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` returns 1
    - `grep -c "void create_envelope_on_shared_account_derives_scope_shared_and_owner_null" backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` returns 1
    - `grep -c "void split_parent_with_non_null_category_is_counted_only_via_splits_branch" backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` returns 1
    - `grep -c "void ratio_denominator_includes_carry_over_for_carry_over_envelopes" backend/src/test/java/com/prosperity/envelope/EnvelopeServiceTest.java` returns 1
    - `./mvnw -pl backend test-compile -q` exits 0
  </acceptance_criteria>
  <done>EnvelopeServiceTest.java compiles, contains 24+ disabled scenario stubs covering ENVL-02..05 + service-slice ENVL-01 + new BLOCKER 1/2 coverage stubs.</done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: EnvelopeControllerTest + EnvelopeAllocationControllerTest scaffolds (CRUD, access control, allocations)</name>
  <files>backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java, backend/src/test/java/com/prosperity/envelope/EnvelopeAllocationControllerTest.java</files>
  <read_first>
    - backend/src/test/java/com/prosperity/transaction/TransactionControllerTest.java (canonical Testcontainers + MockMvc structure)
    - backend/src/test/java/com/prosperity/auth/UserControllerTest.java (confirm AutoConfigureMockMvc import path used in this codebase: `org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc`)
    - .planning/phases/06-envelope-budgets/06-RESEARCH.md (Phase Requirements -> Test Map: every "EnvelopeControllerTest#..." and "EnvelopeAllocationControllerTest#..." row)
    - .planning/phases/06-envelope-budgets/06-VALIDATION.md (Wave 0 Requirements list — will be rewritten in Task 3)
  </read_first>
  <action>
Create exactly these two files.

**Important on the AutoConfigureMockMvc import:** Use `import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;` — that is the Spring Boot 4.0.x package and what every existing controller test in this codebase uses (UserControllerTest, AuthControllerTest, AccountControllerTest). The legacy Spring Boot 3.x location `org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc` does NOT exist in `spring-boot-test-autoconfigure-4.0.5.jar`.

**File 1: `backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java`**

```java
package com.prosperity.envelope;

import com.prosperity.TestcontainersConfig;
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;

/**
 * Wave 0 RED stubs for EnvelopeController integration tests (Plan 06 fills in the bodies).
 *
 * <p>Coverage map (mirrors 06-RESEARCH.md "Phase Requirements -> Test Map"):
 *
 * <ul>
 *   <li>ENVL-01: create with scope derivation, 403/404, D-01 -> 409
 *   <li>ENVL-06: history endpoint (12 months ordered, zero-consumed buckets)
 *   <li>ENVL-07: update with WRITE access (200), without WRITE (403); delete hard vs soft; archived
 *       hidden by default
 * </ul>
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestcontainersConfig.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class EnvelopeControllerTest {

  // -------------------------------------------------------------------------
  // ENVL-01 — Create
  // -------------------------------------------------------------------------

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void create_envelope_on_personal_account_sets_scope_personal_and_owner_current_user() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void create_envelope_on_shared_account_sets_scope_shared_and_owner_null() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void create_envelope_without_write_access_returns_403() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void create_envelope_on_nonexistent_account_returns_404() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void create_envelope_with_category_already_linked_on_account_returns_409() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void create_envelope_ignores_scope_field_in_payload_and_derives_from_account_type() {}

  // -------------------------------------------------------------------------
  // ENVL-01/02 — Read (single + list)
  // -------------------------------------------------------------------------

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void list_envelopes_on_account_returns_only_user_accessible_envelopes() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void list_envelopes_excludes_archived_by_default() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void list_envelopes_with_include_archived_param_returns_archived() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void get_envelope_response_includes_status_ratio_consumed_available_for_current_month() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void get_envelope_without_read_access_returns_403_and_not_404() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void get_nonexistent_envelope_returns_404() {}

  // -------------------------------------------------------------------------
  // ENVL-06 — History
  // -------------------------------------------------------------------------

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void get_envelope_history_returns_12_months_ordered_chronologically() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void get_envelope_history_month_without_transactions_returns_zero_consumed() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void get_envelope_history_overlays_monthly_overrides_on_default_budget() {}

  // -------------------------------------------------------------------------
  // ENVL-07 — Update + Delete
  // -------------------------------------------------------------------------

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void update_envelope_with_write_access_persists_changes() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void update_envelope_without_write_access_returns_403() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void update_envelope_partial_patch_only_changes_provided_fields() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void delete_envelope_without_allocations_hard_deletes() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void delete_envelope_with_allocations_soft_deletes_and_excludes_from_list() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void delete_envelope_without_write_access_returns_403() {}
}
```

**File 2: `backend/src/test/java/com/prosperity/envelope/EnvelopeAllocationControllerTest.java`**

```java
package com.prosperity.envelope;

import com.prosperity.TestcontainersConfig;
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;

/**
 * Wave 0 RED stubs for EnvelopeAllocationController (monthly override CRUD). Plan 06 fills bodies.
 *
 * <p>Coverage map: ENVL-02 monthly override endpoints (D-08, D-10).
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestcontainersConfig.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class EnvelopeAllocationControllerTest {

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void create_allocation_for_envelope_returns_201_with_response() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void duplicate_allocation_for_same_month_returns_409() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void create_allocation_without_write_access_returns_403() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void list_allocations_for_envelope_returns_overrides_ordered_by_month_asc() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void update_allocation_replaces_allocated_amount_for_month() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void delete_allocation_removes_override_and_falls_back_to_default_budget() {}

  @Test
  @Disabled("Wave 0 stub — body in Plan 06")
  void create_allocation_for_nonexistent_envelope_returns_404() {}
}
```
  </action>
  <verify>
    <automated>cd /home/negus/dev/prosperity && ./mvnw -pl backend test -Dtest='Envelope*Test' -q 2>&1 | tail -15</automated>
  </verify>
  <acceptance_criteria>
    - File `backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java` exists
    - File `backend/src/test/java/com/prosperity/envelope/EnvelopeAllocationControllerTest.java` exists
    - `grep -c "@Test" backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java` returns at least 21
    - `grep -c "@Test" backend/src/test/java/com/prosperity/envelope/EnvelopeAllocationControllerTest.java` returns at least 7
    - `grep -c "@Import(TestcontainersConfig.class)" backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java` returns 1
    - `grep -c "@Import(TestcontainersConfig.class)" backend/src/test/java/com/prosperity/envelope/EnvelopeAllocationControllerTest.java` returns 1
    - `grep -c "@AutoConfigureMockMvc" backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java` returns 1
    - `grep -c "import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;" backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java` returns 1
    - `grep -c "import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;" backend/src/test/java/com/prosperity/envelope/EnvelopeAllocationControllerTest.java` returns 1
    - `grep -c "@Disabled" backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java` returns at least 21
    - `grep -c "void create_envelope_on_personal_account_sets_scope_personal_and_owner_current_user" backend/src/test/java/com/prosperity/envelope/EnvelopeControllerTest.java` returns 1
    - `grep -c "void duplicate_allocation_for_same_month_returns_409" backend/src/test/java/com/prosperity/envelope/EnvelopeAllocationControllerTest.java` returns 1
    - `./mvnw -pl backend test -Dtest='Envelope*Test' -q` exits 0 (all stubs are @Disabled so no execution; existing EnvelopeTest still passes; surefire reports 0 failures)
  </acceptance_criteria>
  <done>Both test scaffolds compile and run (all methods @Disabled). Test count summary shows existing EnvelopeTest still green, new tests skipped. Imports use the Spring Boot 4.0.x AutoConfigureMockMvc package (`org.springframework.boot.webmvc.test.autoconfigure`).</done>
</task>

<task type="auto" tdd="false">
  <name>Task 3: Update 06-VALIDATION.md (consolidated Wave 0 Requirements list, ProsperityApplicationTest reference, wave_0_complete: true)</name>
  <files>.planning/phases/06-envelope-budgets/06-VALIDATION.md</files>
  <read_first>
    - .planning/phases/06-envelope-budgets/06-VALIDATION.md (current state)
    - .planning/phases/06-envelope-budgets/06-01-data-layer-PLAN.md (confirms ProsperityApplicationTest is the migration smoke test, not FlywayMigrationTest)
  </read_first>
  <action>
Apply the following SURGICAL edits to `.planning/phases/06-envelope-budgets/06-VALIDATION.md` (do NOT replace the entire file — make precise modifications):

**Edit 1 — Frontmatter:**
- Locate the YAML block at the top of the file.
- Change `wave_0_complete: false` to `wave_0_complete: true`.
- ADD a new line `updated: 2026-04-22` immediately after the existing `created: 2026-04-22` line.
- Leave `nyquist_compliant: false` UNCHANGED (Plan 08 will flip it later — Wave 0 = scaffold creation, nyquist compliance requires test bodies green).

**Edit 2 — Per-Task Verification Map (table row replacement):**
- Locate the row containing `FlywayMigrationTest` and replace it with this row (same column structure):
  | 06-01-01 | 01 | 1 | ENVL-01 | migration | `./mvnw -pl backend test -Dtest=ProsperityApplicationTest` | available | pending |
- ADD two more rows immediately after that row, one for each Plan 03 task:
  | 06-03-01 | 03 | 1 | ENVL-02..05 | scaffold | `./mvnw -pl backend test-compile` | Plan 03 | pending |
  | 06-03-02 | 03 | 1 | ENVL-01,02,06,07 | scaffold | `./mvnw -pl backend test -Dtest='Envelope*Test'` | Plan 03 | pending |
- Use plain ASCII status words ("available", "pending", "Plan 03") instead of emoji checkmarks to keep grep targets stable. The original status legend can stay as-is below the table.

**Edit 3 — Wave 0 Requirements section:**
- Locate the section heading `## Wave 0 Requirements`.
- Replace the entire bullet list under that heading (down to the next `## ` heading) with the following CONSOLIDATED list:

```
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
```

**Edit 4 — Validation Sign-Off section:**
- Tick the first 5 checkboxes (change `- [ ]` to `- [x]`) — leave the last one (`nyquist_compliant: true set in frontmatter`) unchecked.
- Append parenthetical "(FLIPPED by Plan 08 once `pnpm test -- --run src/app/envelopes` exits 0 with all real assertions; backend bodies are green starting Plan 06)" to the last checkbox line.
- Change the `**Approval:** pending` line to `**Approval:** Wave 0 scaffolding complete (Plan 03). Test bodies pending: backend Plan 06, frontend Plan 08.`

After applying these edits, save the file. Verify with:
- `grep -c "wave_0_complete: true" .planning/phases/06-envelope-budgets/06-VALIDATION.md` returns 1
- `grep -c "FlywayMigrationTest" .planning/phases/06-envelope-budgets/06-VALIDATION.md` returns 0
- `grep -c "ProsperityApplicationTest" .planning/phases/06-envelope-budgets/06-VALIDATION.md` returns at least 1
  </action>
  <verify>
    <automated>grep -c "wave_0_complete: true" .planning/phases/06-envelope-budgets/06-VALIDATION.md && grep -c "ProsperityApplicationTest" .planning/phases/06-envelope-budgets/06-VALIDATION.md && test "$(grep -c FlywayMigrationTest .planning/phases/06-envelope-budgets/06-VALIDATION.md)" = "0"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "wave_0_complete: true" .planning/phases/06-envelope-budgets/06-VALIDATION.md` returns 1
    - `grep -c "nyquist_compliant: false" .planning/phases/06-envelope-budgets/06-VALIDATION.md` returns 1 (Plan 08 will flip it)
    - `grep -c "ProsperityApplicationTest" .planning/phases/06-envelope-budgets/06-VALIDATION.md` returns at least 1
    - `grep -c "FlywayMigrationTest" .planning/phases/06-envelope-budgets/06-VALIDATION.md` returns 0 (removed)
    - `grep -c "EnvelopeServiceTest.java" .planning/phases/06-envelope-budgets/06-VALIDATION.md` returns at least 1 (consolidated entry)
    - `grep -c "EnvelopeControllerTest.java" .planning/phases/06-envelope-budgets/06-VALIDATION.md` returns at least 1
    - `grep -c "EnvelopeAllocationControllerTest.java" .planning/phases/06-envelope-budgets/06-VALIDATION.md` returns at least 1
    - `grep -c "Wave 0 scaffolding complete" .planning/phases/06-envelope-budgets/06-VALIDATION.md` returns 1
  </acceptance_criteria>
  <done>06-VALIDATION.md updated to reflect the consolidated 3-file Wave 0 scaffold structure delivered by Plan 03; references the actual smoke test (ProsperityApplicationTest) instead of the non-existent FlywayMigrationTest; wave_0_complete flag is true; nyquist_compliant stays false (flipped later by Plan 08).</done>
</task>

</tasks>

<verification>
- `./mvnw -pl backend test-compile` exits 0.
- `./mvnw -pl backend test -Dtest='Envelope*Test'` runs without failures (existing EnvelopeTest green; new stubs skipped).
- 06-VALIDATION.md frontmatter `wave_0_complete: true` is set and the file's Wave 0 Requirements list maps 1:1 to the three backend scaffolds delivered by this plan.
- `nyquist_compliant: false` remains until Plan 08 flips it (after frontend specs are real and green).
</verification>

<success_criteria>
- 3 backend test files exist as compilable scaffolds
- All test methods @Disabled with the same message ("Wave 0 stub — body in Plan 06") so Plan 06 can grep-find every body to fill
- Test method names match the names referenced in 06-RESEARCH.md Test Map and the rewritten 06-VALIDATION.md Wave 0 Requirements
- AutoConfigureMockMvc imports use the Spring Boot 4.0.x package (`org.springframework.boot.webmvc.test.autoconfigure`) — same as every existing controller test in this codebase
- 06-VALIDATION.md updated: consolidated Wave 0 Requirements (3 backend files), Per-Task Verification Map references ProsperityApplicationTest, wave_0_complete: true, nyquist_compliant: false (Plan 08 flips later)
- ./mvnw -pl backend test -Dtest='Envelope*Test' returns success (no compile errors, no test failures since stubs are skipped)
</success_criteria>

<output>
After completion, create `.planning/phases/06-envelope-budgets/06-03-test-scaffolds-SUMMARY.md`.
</output>
