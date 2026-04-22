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
