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
