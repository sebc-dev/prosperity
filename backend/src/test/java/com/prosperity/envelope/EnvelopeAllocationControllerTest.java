package com.prosperity.envelope;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.prosperity.TestcontainersConfig;
import com.prosperity.account.AccessLevel;
import com.prosperity.account.Account;
import com.prosperity.account.AccountAccess;
import com.prosperity.account.AccountAccessRepository;
import com.prosperity.account.AccountRepository;
import com.prosperity.auth.User;
import com.prosperity.auth.UserRepository;
import com.prosperity.category.Category;
import com.prosperity.category.CategoryRepository;
import com.prosperity.shared.AccountType;
import com.prosperity.shared.EnvelopeScope;
import com.prosperity.shared.Money;
import com.prosperity.shared.RolloverPolicy;
import java.math.BigDecimal;
import java.time.YearMonth;
import java.time.ZoneId;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

/**
 * Integration tests for {@link EnvelopeAllocationController} monthly override CRUD (D-08, D-10).
 * Uses real PostgreSQL via Testcontainers.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestcontainersConfig.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class EnvelopeAllocationControllerTest {

  private static final String USER_EMAIL = "test@test.com";
  private static final String OTHER_USER_EMAIL = "other@test.com";
  private static final UUID COURSES_CATEGORY_ID =
      UUID.fromString("a0000000-0000-0000-0000-000000000101");

  @Autowired private MockMvc mockMvc;
  @Autowired private EnvelopeRepository envelopeRepository;
  @Autowired private EnvelopeAllocationRepository allocationRepository;
  @Autowired private UserRepository userRepository;
  @Autowired private AccountRepository accountRepository;
  @Autowired private AccountAccessRepository accountAccessRepository;
  @Autowired private CategoryRepository categoryRepository;

  private User testUser;
  private Account testAccount;
  private Category coursesCategory;

  @BeforeEach
  void setUp() {
    testUser = userRepository.save(new User(USER_EMAIL, "{bcrypt}$2a$10$hash", "Test User"));
    testAccount = accountRepository.save(new Account("Compte Courant", AccountType.PERSONAL));
    accountAccessRepository.save(new AccountAccess(testUser, testAccount, AccessLevel.WRITE));
    coursesCategory = categoryRepository.findById(COURSES_CATEGORY_ID).orElseThrow();
  }

  // -------------------------------------------------------------------------
  // Builders
  // -------------------------------------------------------------------------

  private Envelope persistEnvelope(String name, BigDecimal budget) {
    Envelope envelope = new Envelope(testAccount, name, EnvelopeScope.PERSONAL, new Money(budget));
    envelope.setOwner(testUser);
    envelope.setRolloverPolicy(RolloverPolicy.RESET);
    envelope.getCategories().add(coursesCategory);
    return envelopeRepository.save(envelope);
  }

  private void persistAllocation(Envelope envelope, YearMonth month, BigDecimal amount) {
    allocationRepository.save(new EnvelopeAllocation(envelope, month, new Money(amount)));
  }

  // -------------------------------------------------------------------------
  // ENVL-02 — Monthly override CRUD
  // -------------------------------------------------------------------------

  @Test
  void create_allocation_for_envelope_returns_201_with_response() throws Exception {
    // Arrange
    Envelope envelope = persistEnvelope("Vie quotidienne", new BigDecimal("100.00"));

    // Act
    mockMvc
        .perform(
            post("/api/envelopes/{id}/allocations", envelope.getId())
                .with(user(USER_EMAIL))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"month":"2026-04","allocatedAmount":250.00}
                    """))

        // Assert
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.month").value("2026-04"))
        .andExpect(jsonPath("$.allocatedAmount").value(250.00))
        .andExpect(jsonPath("$.envelopeId").value(envelope.getId().toString()));
  }

  @Test
  void duplicate_allocation_for_same_month_returns_409() throws Exception {
    // Arrange — allocation already exists for 2026-04
    Envelope envelope = persistEnvelope("Vie quotidienne", new BigDecimal("100.00"));
    persistAllocation(envelope, YearMonth.of(2026, 4), new BigDecimal("250.00"));

    // Act
    mockMvc
        .perform(
            post("/api/envelopes/{id}/allocations", envelope.getId())
                .with(user(USER_EMAIL))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"month":"2026-04","allocatedAmount":300.00}
                    """))

        // Assert — DataIntegrityViolation translated to 409 Conflict by controller
        .andExpect(status().isConflict());
  }

  @Test
  void create_allocation_without_write_access_returns_403() throws Exception {
    // Arrange — user with READ only
    Envelope envelope = persistEnvelope("Vie quotidienne", new BigDecimal("100.00"));
    User reader = userRepository.save(new User(OTHER_USER_EMAIL, "{bcrypt}$2a$10$hash", "Reader"));
    accountAccessRepository.save(new AccountAccess(reader, testAccount, AccessLevel.READ));

    // Act
    mockMvc
        .perform(
            post("/api/envelopes/{id}/allocations", envelope.getId())
                .with(user(OTHER_USER_EMAIL))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"month":"2026-04","allocatedAmount":250.00}
                    """))

        // Assert
        .andExpect(status().isForbidden());
  }

  @Test
  void list_allocations_for_envelope_returns_overrides_ordered_by_month_asc() throws Exception {
    // Arrange — insert out-of-order months: June, January, March
    Envelope envelope = persistEnvelope("Vie quotidienne", new BigDecimal("100.00"));
    persistAllocation(envelope, YearMonth.of(2026, 6), new BigDecimal("300.00"));
    persistAllocation(envelope, YearMonth.of(2026, 1), new BigDecimal("100.00"));
    persistAllocation(envelope, YearMonth.of(2026, 3), new BigDecimal("200.00"));

    // Act
    mockMvc
        .perform(get("/api/envelopes/{id}/allocations", envelope.getId()).with(user(USER_EMAIL)))

        // Assert — ordered ascending by month
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.length()").value(3))
        .andExpect(jsonPath("$[0].month").value("2026-01"))
        .andExpect(jsonPath("$[1].month").value("2026-03"))
        .andExpect(jsonPath("$[2].month").value("2026-06"));
  }

  @Test
  void update_allocation_replaces_allocated_amount_for_month() throws Exception {
    // Arrange
    Envelope envelope = persistEnvelope("Vie quotidienne", new BigDecimal("100.00"));
    EnvelopeAllocation allocation =
        allocationRepository.save(
            new EnvelopeAllocation(
                envelope, YearMonth.of(2026, 4), new Money(new BigDecimal("250.00"))));

    // Act
    mockMvc
        .perform(
            put("/api/envelopes/allocations/{allocationId}", allocation.getId())
                .with(user(USER_EMAIL))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"month":"2026-04","allocatedAmount":500.00}
                    """))

        // Assert — amount replaced
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.month").value("2026-04"))
        .andExpect(jsonPath("$.allocatedAmount").value(500.00));
  }

  @Test
  void delete_allocation_removes_override_and_falls_back_to_default_budget() throws Exception {
    // Arrange — envelope default 100, override 250 for April 2026
    Envelope envelope = persistEnvelope("Vie quotidienne", new BigDecimal("100.00"));
    EnvelopeAllocation allocation =
        allocationRepository.save(
            new EnvelopeAllocation(
                envelope,
                YearMonth.now(ZoneId.systemDefault()),
                new Money(new BigDecimal("250.00"))));

    // Act
    mockMvc
        .perform(
            delete("/api/envelopes/allocations/{allocationId}", allocation.getId())
                .with(user(USER_EMAIL))
                .with(csrf()))

        // Assert — 204, then GET envelope shows default budget again
        .andExpect(status().isNoContent());
    mockMvc
        .perform(get("/api/envelopes/{id}", envelope.getId()).with(user(USER_EMAIL)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.effectiveBudget").value(100.00))
        .andExpect(jsonPath("$.hasMonthlyOverride").value(false));
  }

  @Test
  void create_allocation_for_nonexistent_envelope_returns_404() throws Exception {
    // Arrange
    UUID fakeEnvelopeId = UUID.randomUUID();

    // Act
    mockMvc
        .perform(
            post("/api/envelopes/{id}/allocations", fakeEnvelopeId)
                .with(user(USER_EMAIL))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"month":"2026-04","allocatedAmount":250.00}
                    """))

        // Assert
        .andExpect(status().isNotFound());
  }
}
