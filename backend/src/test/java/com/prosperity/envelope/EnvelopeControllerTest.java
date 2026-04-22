package com.prosperity.envelope;

import static org.assertj.core.api.Assertions.assertThat;
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
import com.prosperity.shared.TransactionSource;
import com.prosperity.transaction.Transaction;
import com.prosperity.transaction.TransactionRepository;
import java.math.BigDecimal;
import java.time.LocalDate;
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
 * Integration tests for {@link EnvelopeController} endpoints. Covers CRUD, history, access control
 * (403 vs 404 inheritance from the parent account), scope derivation, D-01 uniqueness (409), and
 * hard-vs-soft delete (D-18). Uses real PostgreSQL via Testcontainers.
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

  private static final String USER_EMAIL = "test@test.com";
  private static final String OTHER_USER_EMAIL = "other@test.com";
  private static final UUID COURSES_CATEGORY_ID =
      UUID.fromString("a0000000-0000-0000-0000-000000000101");
  private static final UUID RESTAURANT_CATEGORY_ID =
      UUID.fromString("a0000000-0000-0000-0000-000000000102");

  @Autowired private MockMvc mockMvc;
  @Autowired private EnvelopeRepository envelopeRepository;
  @Autowired private EnvelopeAllocationRepository allocationRepository;
  @Autowired private UserRepository userRepository;
  @Autowired private AccountRepository accountRepository;
  @Autowired private AccountAccessRepository accountAccessRepository;
  @Autowired private CategoryRepository categoryRepository;
  @Autowired private TransactionRepository transactionRepository;

  private User testUser;
  private Account testAccount;
  private Category coursesCategory;
  private Category restaurantCategory;

  @BeforeEach
  void setUp() {
    testUser = userRepository.save(new User(USER_EMAIL, "{bcrypt}$2a$10$hash", "Test User"));
    testAccount = accountRepository.save(new Account("Compte Courant", AccountType.PERSONAL));
    accountAccessRepository.save(new AccountAccess(testUser, testAccount, AccessLevel.WRITE));
    coursesCategory = categoryRepository.findById(COURSES_CATEGORY_ID).orElseThrow();
    restaurantCategory = categoryRepository.findById(RESTAURANT_CATEGORY_ID).orElseThrow();
  }

  // -------------------------------------------------------------------------
  // Builders
  // -------------------------------------------------------------------------

  private Envelope persistEnvelope(
      Account account, String name, BigDecimal budget, RolloverPolicy policy, Category... cats) {
    EnvelopeScope scope =
        account.getAccountType() == AccountType.SHARED
            ? EnvelopeScope.SHARED
            : EnvelopeScope.PERSONAL;
    Envelope envelope = new Envelope(account, name, scope, new Money(budget));
    envelope.setOwner(scope == EnvelopeScope.PERSONAL ? testUser : null);
    envelope.setRolloverPolicy(policy);
    for (Category c : cats) {
      envelope.getCategories().add(c);
    }
    return envelopeRepository.save(envelope);
  }

  // -------------------------------------------------------------------------
  // ENVL-01 — Create
  // -------------------------------------------------------------------------

  @Test
  void create_envelope_on_personal_account_sets_scope_personal_and_owner_current_user()
      throws Exception {
    // Arrange — personal account + WRITE access already set up in @BeforeEach

    // Act
    mockMvc
        .perform(
            post("/api/accounts/{accountId}/envelopes", testAccount.getId())
                .with(user(USER_EMAIL))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    String.format(
                        """
                        {"name":"Vie quotidienne","categoryIds":["%s"],\
                        "budget":100.00,"rolloverPolicy":"RESET"}
                        """,
                        coursesCategory.getId())))

        // Assert
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.scope").value("PERSONAL"))
        .andExpect(jsonPath("$.ownerId").value(testUser.getId().toString()))
        .andExpect(jsonPath("$.name").value("Vie quotidienne"))
        .andExpect(jsonPath("$.defaultBudget").value(100.00));
  }

  @Test
  void create_envelope_on_shared_account_sets_scope_shared_and_owner_null() throws Exception {
    // Arrange — shared account, user has WRITE
    Account sharedAccount = accountRepository.save(new Account("Compte Foyer", AccountType.SHARED));
    accountAccessRepository.save(new AccountAccess(testUser, sharedAccount, AccessLevel.WRITE));

    // Act
    mockMvc
        .perform(
            post("/api/accounts/{accountId}/envelopes", sharedAccount.getId())
                .with(user(USER_EMAIL))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    String.format(
                        """
                        {"name":"Courses foyer","categoryIds":["%s"],\
                        "budget":400.00,"rolloverPolicy":"CARRY_OVER"}
                        """,
                        coursesCategory.getId())))

        // Assert
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.scope").value("SHARED"))
        .andExpect(jsonPath("$.ownerId").doesNotExist());
  }

  @Test
  void create_envelope_without_write_access_returns_403() throws Exception {
    // Arrange — second user with READ only on testAccount
    User readerUser =
        userRepository.save(new User(OTHER_USER_EMAIL, "{bcrypt}$2a$10$hash", "Reader"));
    accountAccessRepository.save(new AccountAccess(readerUser, testAccount, AccessLevel.READ));

    // Act
    mockMvc
        .perform(
            post("/api/accounts/{accountId}/envelopes", testAccount.getId())
                .with(user(OTHER_USER_EMAIL))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    String.format(
                        """
                        {"name":"Interdit","categoryIds":["%s"],\
                        "budget":50.00,"rolloverPolicy":"RESET"}
                        """,
                        coursesCategory.getId())))

        // Assert
        .andExpect(status().isForbidden());
  }

  @Test
  void create_envelope_on_nonexistent_account_returns_404() throws Exception {
    // Arrange
    UUID fakeAccountId = UUID.randomUUID();

    // Act
    mockMvc
        .perform(
            post("/api/accounts/{accountId}/envelopes", fakeAccountId)
                .with(user(USER_EMAIL))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    String.format(
                        """
                        {"name":"X","categoryIds":["%s"],\
                        "budget":50.00,"rolloverPolicy":"RESET"}
                        """,
                        coursesCategory.getId())))

        // Assert
        .andExpect(status().isNotFound());
  }

  @Test
  void create_envelope_with_category_already_linked_on_account_returns_409() throws Exception {
    // Arrange — envelope A already links courses on testAccount
    persistEnvelope(
        testAccount, "Existante", new BigDecimal("100.00"), RolloverPolicy.RESET, coursesCategory);

    // Act
    mockMvc
        .perform(
            post("/api/accounts/{accountId}/envelopes", testAccount.getId())
                .with(user(USER_EMAIL))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    String.format(
                        """
                        {"name":"Doublon","categoryIds":["%s"],\
                        "budget":50.00,"rolloverPolicy":"RESET"}
                        """,
                        coursesCategory.getId())))

        // Assert
        .andExpect(status().isConflict());
  }

  @Test
  void create_envelope_ignores_scope_field_in_payload_and_derives_from_account_type()
      throws Exception {
    // Arrange — PERSONAL account; payload contains an IGNORED "scope":"SHARED" extra field (Pitfall
    // 4)

    // Act
    mockMvc
        .perform(
            post("/api/accounts/{accountId}/envelopes", testAccount.getId())
                .with(user(USER_EMAIL))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    String.format(
                        """
                        {"name":"Injection","scope":"SHARED","categoryIds":["%s"],\
                        "budget":100.00,"rolloverPolicy":"RESET"}
                        """,
                        coursesCategory.getId())))

        // Assert — response scope is PERSONAL (derived from account.accountType, not payload)
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.scope").value("PERSONAL"));
  }

  // -------------------------------------------------------------------------
  // ENVL-01/02 — Read (single + list)
  // -------------------------------------------------------------------------

  @Test
  void list_envelopes_on_account_returns_only_user_accessible_envelopes() throws Exception {
    // Arrange — testUser has WRITE on testAccount; another account the user cannot see
    persistEnvelope(
        testAccount, "Visible", new BigDecimal("100.00"), RolloverPolicy.RESET, coursesCategory);
    Account hiddenAccount =
        accountRepository.save(new Account("Compte Tiers", AccountType.PERSONAL));
    // intentionally NO AccountAccess for testUser on hiddenAccount
    persistEnvelope(
        hiddenAccount,
        "Invisible",
        new BigDecimal("100.00"),
        RolloverPolicy.RESET,
        restaurantCategory);

    // Act
    mockMvc
        .perform(
            get("/api/accounts/{accountId}/envelopes", testAccount.getId()).with(user(USER_EMAIL)))

        // Assert — only the envelope on the accessible account appears
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.length()").value(1))
        .andExpect(jsonPath("$[0].name").value("Visible"));
  }

  @Test
  void list_envelopes_excludes_archived_by_default() throws Exception {
    // Arrange — two envelopes, one archived
    persistEnvelope(
        testAccount, "Actif", new BigDecimal("100.00"), RolloverPolicy.RESET, coursesCategory);
    Envelope archived =
        persistEnvelope(
            testAccount,
            "Archive",
            new BigDecimal("50.00"),
            RolloverPolicy.RESET,
            restaurantCategory);
    archived.setArchived(true);
    envelopeRepository.save(archived);

    // Act
    mockMvc
        .perform(
            get("/api/accounts/{accountId}/envelopes", testAccount.getId()).with(user(USER_EMAIL)))

        // Assert — only the non-archived one
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.length()").value(1))
        .andExpect(jsonPath("$[0].name").value("Actif"));
  }

  @Test
  void list_envelopes_with_include_archived_param_returns_archived() throws Exception {
    // Arrange — one active, one archived
    persistEnvelope(
        testAccount, "Actif", new BigDecimal("100.00"), RolloverPolicy.RESET, coursesCategory);
    Envelope archived =
        persistEnvelope(
            testAccount,
            "Archive",
            new BigDecimal("50.00"),
            RolloverPolicy.RESET,
            restaurantCategory);
    archived.setArchived(true);
    envelopeRepository.save(archived);

    // Act
    mockMvc
        .perform(
            get("/api/accounts/{accountId}/envelopes", testAccount.getId())
                .param("includeArchived", "true")
                .with(user(USER_EMAIL)))

        // Assert — both returned
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.length()").value(2));
  }

  @Test
  void get_envelope_response_includes_status_ratio_consumed_available_for_current_month()
      throws Exception {
    // Arrange — envelope with budget 100, one transaction consuming 40 this month
    Envelope envelope =
        persistEnvelope(
            testAccount,
            "Vie quotidienne",
            new BigDecimal("100.00"),
            RolloverPolicy.RESET,
            coursesCategory);
    Transaction tx =
        new Transaction(
            testAccount,
            new Money(new BigDecimal("-40.00")),
            LocalDate.now(ZoneId.systemDefault()).withDayOfMonth(10),
            TransactionSource.MANUAL);
    tx.setCategory(coursesCategory);
    tx.setCreatedBy(testUser);
    transactionRepository.save(tx);

    // Act
    mockMvc
        .perform(get("/api/envelopes/{id}", envelope.getId()).with(user(USER_EMAIL)))

        // Assert — ratio = 40/100 = 0.4 (GREEN since < 0.80)
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("GREEN"))
        .andExpect(jsonPath("$.ratio").value(0.4))
        .andExpect(jsonPath("$.consumed").value(40.00))
        .andExpect(jsonPath("$.available").value(60.00));
  }

  @Test
  void get_envelope_without_read_access_returns_403_and_not_404() throws Exception {
    // Arrange — envelope exists; caller is a user with NO access to the account
    Envelope envelope =
        persistEnvelope(
            testAccount, "Prive", new BigDecimal("100.00"), RolloverPolicy.RESET, coursesCategory);
    userRepository.save(new User(OTHER_USER_EMAIL, "{bcrypt}$2a$10$hash", "Autre"));
    // no AccountAccess row for OTHER_USER_EMAIL

    // Act
    mockMvc
        .perform(get("/api/envelopes/{id}", envelope.getId()).with(user(OTHER_USER_EMAIL)))

        // Assert — 403 (envelope EXISTS, so not 404) — confirms existsById precedes access check
        .andExpect(status().isForbidden());
  }

  @Test
  void get_nonexistent_envelope_returns_404() throws Exception {
    // Arrange
    UUID fakeId = UUID.randomUUID();

    // Act
    mockMvc
        .perform(get("/api/envelopes/{id}", fakeId).with(user(USER_EMAIL)))

        // Assert
        .andExpect(status().isNotFound());
  }

  // -------------------------------------------------------------------------
  // ENVL-06 — History
  // -------------------------------------------------------------------------

  @Test
  void get_envelope_history_returns_12_months_ordered_chronologically() throws Exception {
    // Arrange — envelope only; query targets April 2026 explicitly
    Envelope envelope =
        persistEnvelope(
            testAccount,
            "Vie quotidienne",
            new BigDecimal("100.00"),
            RolloverPolicy.RESET,
            coursesCategory);

    // Act
    mockMvc
        .perform(
            get("/api/envelopes/{id}/history", envelope.getId())
                .param("month", "2026-04")
                .with(user(USER_EMAIL)))

        // Assert — 12 entries, first is 2025-05 (12 months back inclusive), last is 2026-04
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.length()").value(12))
        .andExpect(jsonPath("$[0].month").value("2025-05"))
        .andExpect(jsonPath("$[11].month").value("2026-04"));
  }

  @Test
  void get_envelope_history_month_without_transactions_returns_zero_consumed() throws Exception {
    // Arrange — envelope with no transactions at all
    Envelope envelope =
        persistEnvelope(
            testAccount, "Vide", new BigDecimal("100.00"), RolloverPolicy.RESET, coursesCategory);

    // Act
    mockMvc
        .perform(
            get("/api/envelopes/{id}/history", envelope.getId())
                .param("month", "2026-04")
                .with(user(USER_EMAIL)))

        // Assert — every bucket is 0
        .andExpect(status().isOk())
        .andExpect(jsonPath("$[0].consumed").value(0))
        .andExpect(jsonPath("$[11].consumed").value(0));
  }

  @Test
  void get_envelope_history_overlays_monthly_overrides_on_default_budget() throws Exception {
    // Arrange — default budget 100, override for 2026-04 = 250
    Envelope envelope =
        persistEnvelope(
            testAccount,
            "Override test",
            new BigDecimal("100.00"),
            RolloverPolicy.RESET,
            coursesCategory);
    allocationRepository.save(
        new EnvelopeAllocation(
            envelope, YearMonth.of(2026, 4), new Money(new BigDecimal("250.00"))));

    // Act
    mockMvc
        .perform(
            get("/api/envelopes/{id}/history", envelope.getId())
                .param("month", "2026-04")
                .with(user(USER_EMAIL)))

        // Assert — April bucket uses override budget (250); March uses default (100)
        .andExpect(status().isOk())
        .andExpect(jsonPath("$[11].month").value("2026-04"))
        .andExpect(jsonPath("$[11].effectiveBudget").value(250.00))
        .andExpect(jsonPath("$[10].month").value("2026-03"))
        .andExpect(jsonPath("$[10].effectiveBudget").value(100.00));
  }

  // -------------------------------------------------------------------------
  // ENVL-07 — Update + Delete
  // -------------------------------------------------------------------------

  @Test
  void update_envelope_with_write_access_persists_changes() throws Exception {
    // Arrange
    Envelope envelope =
        persistEnvelope(
            testAccount,
            "Initial",
            new BigDecimal("100.00"),
            RolloverPolicy.RESET,
            coursesCategory);

    // Act
    mockMvc
        .perform(
            put("/api/envelopes/{id}", envelope.getId())
                .with(user(USER_EMAIL))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    String.format(
                        """
                        {"name":"Renamed","categoryIds":["%s"],\
                        "budget":250.00,"rolloverPolicy":"CARRY_OVER"}
                        """,
                        coursesCategory.getId())))

        // Assert
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.name").value("Renamed"))
        .andExpect(jsonPath("$.defaultBudget").value(250.00))
        .andExpect(jsonPath("$.rolloverPolicy").value("CARRY_OVER"));
  }

  @Test
  void update_envelope_without_write_access_returns_403() throws Exception {
    // Arrange — envelope + user with only READ
    Envelope envelope =
        persistEnvelope(
            testAccount, "Locked", new BigDecimal("100.00"), RolloverPolicy.RESET, coursesCategory);
    User reader = userRepository.save(new User(OTHER_USER_EMAIL, "{bcrypt}$2a$10$hash", "Reader"));
    accountAccessRepository.save(new AccountAccess(reader, testAccount, AccessLevel.READ));

    // Act
    mockMvc
        .perform(
            put("/api/envelopes/{id}", envelope.getId())
                .with(user(OTHER_USER_EMAIL))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"name":"Hacked"}
                    """))

        // Assert
        .andExpect(status().isForbidden());
  }

  @Test
  void update_envelope_partial_patch_only_changes_provided_fields() throws Exception {
    // Arrange — envelope name=Initial budget=100 policy=RESET; PATCH only name
    Envelope envelope =
        persistEnvelope(
            testAccount,
            "Initial",
            new BigDecimal("100.00"),
            RolloverPolicy.RESET,
            coursesCategory);

    // Act
    mockMvc
        .perform(
            put("/api/envelopes/{id}", envelope.getId())
                .with(user(USER_EMAIL))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"name":"Renamed"}
                    """))

        // Assert — name changed, budget/policy preserved
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.name").value("Renamed"))
        .andExpect(jsonPath("$.defaultBudget").value(100.00))
        .andExpect(jsonPath("$.rolloverPolicy").value("RESET"));
  }

  @Test
  void delete_envelope_without_allocations_hard_deletes() throws Exception {
    // Arrange — envelope with no allocation rows
    Envelope envelope =
        persistEnvelope(
            testAccount,
            "ToDelete",
            new BigDecimal("100.00"),
            RolloverPolicy.RESET,
            coursesCategory);
    UUID envelopeId = envelope.getId();

    // Act
    mockMvc
        .perform(delete("/api/envelopes/{id}", envelopeId).with(user(USER_EMAIL)).with(csrf()))

        // Assert
        .andExpect(status().isNoContent());
    assertThat(envelopeRepository.findById(envelopeId)).isEmpty();
  }

  @Test
  void delete_envelope_with_allocations_soft_deletes_and_excludes_from_list() throws Exception {
    // Arrange — envelope + at least one allocation
    Envelope envelope =
        persistEnvelope(
            testAccount,
            "ToArchive",
            new BigDecimal("100.00"),
            RolloverPolicy.RESET,
            coursesCategory);
    allocationRepository.save(
        new EnvelopeAllocation(
            envelope, YearMonth.of(2026, 4), new Money(new BigDecimal("250.00"))));
    UUID envelopeId = envelope.getId();

    // Act
    mockMvc
        .perform(delete("/api/envelopes/{id}", envelopeId).with(user(USER_EMAIL)).with(csrf()))

        // Assert — 204; envelope still present but archived; default list excludes it
        .andExpect(status().isNoContent());
    Envelope reloaded = envelopeRepository.findById(envelopeId).orElseThrow();
    assertThat(reloaded.isArchived()).isTrue();

    mockMvc
        .perform(
            get("/api/accounts/{accountId}/envelopes", testAccount.getId()).with(user(USER_EMAIL)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.length()").value(0));
  }

  @Test
  void delete_envelope_without_write_access_returns_403() throws Exception {
    // Arrange — READ-only user
    Envelope envelope =
        persistEnvelope(
            testAccount,
            "Guarded",
            new BigDecimal("100.00"),
            RolloverPolicy.RESET,
            coursesCategory);
    User reader = userRepository.save(new User(OTHER_USER_EMAIL, "{bcrypt}$2a$10$hash", "Reader"));
    accountAccessRepository.save(new AccountAccess(reader, testAccount, AccessLevel.READ));

    // Act
    mockMvc
        .perform(
            delete("/api/envelopes/{id}", envelope.getId())
                .with(user(OTHER_USER_EMAIL))
                .with(csrf()))

        // Assert
        .andExpect(status().isForbidden());
  }
}
