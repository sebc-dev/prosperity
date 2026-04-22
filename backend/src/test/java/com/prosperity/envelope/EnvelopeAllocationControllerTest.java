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
