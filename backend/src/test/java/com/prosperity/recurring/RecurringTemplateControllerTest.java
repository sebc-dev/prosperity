package com.prosperity.recurring;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.prosperity.TestcontainersConfig;
import com.prosperity.account.Account;
import com.prosperity.account.AccountAccess;
import com.prosperity.account.AccountAccessRepository;
import com.prosperity.account.AccountRepository;
import com.prosperity.account.AccessLevel;
import com.prosperity.auth.User;
import com.prosperity.auth.UserRepository;
import com.prosperity.shared.AccountType;
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
import org.springframework.test.web.servlet.MvcResult;

/**
 * Integration tests for RecurringTemplateController endpoints. Covers CRUD, generate, inactive
 * guard, and access control. Uses real PostgreSQL via Testcontainers.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestcontainersConfig.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class RecurringTemplateControllerTest {

  @Autowired private MockMvc mockMvc;
  @Autowired private UserRepository userRepository;
  @Autowired private AccountRepository accountRepository;
  @Autowired private AccountAccessRepository accountAccessRepository;

  private User testUser;
  private Account testAccount;

  @BeforeEach
  void setUp() {
    testUser = userRepository.save(new User("test@test.com", "{bcrypt}$2a$10$hash", "Test User"));
    testAccount = accountRepository.save(new Account("Compte Courant", AccountType.PERSONAL));
    accountAccessRepository.save(new AccountAccess(testUser, testAccount, AccessLevel.WRITE));
  }

  // ---------------------------------------------------------------------------
  // CREATE (TXNS-04)
  // ---------------------------------------------------------------------------

  @Test
  void create_template_returns_201() throws Exception {
    // Arrange — inline

    // Act
    mockMvc
        .perform(
            post("/api/accounts/{accountId}/recurring-templates", testAccount.getId())
                .with(user("test@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"amount": -800.00, "description": "Loyer", \
                    "frequency": "MONTHLY", "dayOfMonth": 5, \
                    "nextDueDate": "2026-05-05"}
                    """))

        // Assert
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.amount").value(-800.00))
        .andExpect(jsonPath("$.description").value("Loyer"))
        .andExpect(jsonPath("$.frequency").value("MONTHLY"))
        .andExpect(jsonPath("$.dayOfMonth").value(5))
        .andExpect(jsonPath("$.nextDueDate").value("2026-05-05"))
        .andExpect(jsonPath("$.active").value(true));
  }

  // ---------------------------------------------------------------------------
  // LIST (TXNS-04)
  // ---------------------------------------------------------------------------

  @Test
  void list_active_templates_returns_only_active() throws Exception {
    // Arrange — create two templates, deactivate one
    UUID activeId = createTemplateViaApi("Loyer", -800.00);
    UUID inactiveId = createTemplateViaApi("Ancien abo", -15.00);
    deactivateTemplate(inactiveId);

    // Act — default (no includeInactive param)
    mockMvc
        .perform(
            get("/api/accounts/{accountId}/recurring-templates", testAccount.getId())
                .with(user("test@test.com")))

        // Assert
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.length()").value(1))
        .andExpect(jsonPath("$[0].description").value("Loyer"));
  }

  // ---------------------------------------------------------------------------
  // UPDATE (TXNS-04)
  // ---------------------------------------------------------------------------

  @Test
  void update_template_returns_updated() throws Exception {
    // Arrange
    UUID templateId = createTemplateViaApi("Loyer", -800.00);

    // Act
    mockMvc
        .perform(
            put(
                    "/api/accounts/{accountId}/recurring-templates/{templateId}",
                    testAccount.getId(),
                    templateId)
                .with(user("test@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"amount": -850.00, "description": "Loyer augmente"}
                    """))

        // Assert
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.amount").value(-850.00))
        .andExpect(jsonPath("$.description").value("Loyer augmente"));
  }

  // ---------------------------------------------------------------------------
  // DELETE (TXNS-04)
  // ---------------------------------------------------------------------------

  @Test
  void delete_template_returns_204() throws Exception {
    // Arrange
    UUID templateId = createTemplateViaApi("A supprimer", -100.00);

    // Act
    mockMvc
        .perform(
            delete(
                    "/api/accounts/{accountId}/recurring-templates/{templateId}",
                    testAccount.getId(),
                    templateId)
                .with(user("test@test.com"))
                .with(csrf()))

        // Assert
        .andExpect(status().isNoContent());
  }

  // ---------------------------------------------------------------------------
  // GENERATE (TXNS-04)
  // ---------------------------------------------------------------------------

  @Test
  void generate_transaction_creates_recurring_source_and_advances_date() throws Exception {
    // Arrange
    UUID templateId = createTemplateViaApi("Loyer", -800.00);

    // Act — generate a transaction
    mockMvc
        .perform(
            post(
                    "/api/accounts/{accountId}/recurring-templates/{templateId}/generate",
                    testAccount.getId(),
                    templateId)
                .with(user("test@test.com"))
                .with(csrf()))

        // Assert — generated transaction has RECURRING source and the template's nextDueDate
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.source").value("RECURRING"))
        .andExpect(jsonPath("$.transactionDate").value("2026-05-05"))
        .andExpect(jsonPath("$.amount").value(-800.00));

    // Verify nextDueDate advanced to 2026-06-05
    mockMvc
        .perform(
            get("/api/accounts/{accountId}/recurring-templates", testAccount.getId())
                .with(user("test@test.com"))
                .param("includeInactive", "false"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$[0].nextDueDate").value("2026-06-05"));
  }

  @Test
  void generate_from_inactive_template_returns_400() throws Exception {
    // Arrange
    UUID templateId = createTemplateViaApi("Ancien", -15.00);
    deactivateTemplate(templateId);

    // Act
    mockMvc
        .perform(
            post(
                    "/api/accounts/{accountId}/recurring-templates/{templateId}/generate",
                    testAccount.getId(),
                    templateId)
                .with(user("test@test.com"))
                .with(csrf()))

        // Assert
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error").exists());
  }

  // ---------------------------------------------------------------------------
  // ACCESS CONTROL
  // ---------------------------------------------------------------------------

  @Test
  void create_template_without_access_returns_403() throws Exception {
    // Arrange — second user with no access
    userRepository.save(
        new User("noaccess@test.com", "{bcrypt}$2a$10$hash", "No Access User"));

    // Act
    mockMvc
        .perform(
            post("/api/accounts/{accountId}/recurring-templates", testAccount.getId())
                .with(user("noaccess@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"amount": -100.00, "description": "Test", \
                    "frequency": "MONTHLY", "nextDueDate": "2026-05-05"}
                    """))

        // Assert
        .andExpect(status().isForbidden());
  }

  // ---------------------------------------------------------------------------
  // Test helpers
  // ---------------------------------------------------------------------------

  /**
   * Creates a recurring template via the API and returns its UUID. Uses MONTHLY frequency with
   * dayOfMonth=5 and nextDueDate=2026-05-05.
   */
  private UUID createTemplateViaApi(String description, double amount) throws Exception {
    MvcResult result =
        mockMvc
            .perform(
                post("/api/accounts/{accountId}/recurring-templates", testAccount.getId())
                    .with(user("test@test.com"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        String.format(
                            java.util.Locale.US,
                            """
                            {"amount": %.2f, "description": "%s", \
                            "frequency": "MONTHLY", "dayOfMonth": 5, \
                            "nextDueDate": "2026-05-05"}
                            """,
                            amount, description)))
            .andExpect(status().isCreated())
            .andReturn();

    String body = result.getResponse().getContentAsString();
    String idStr = com.jayway.jsonpath.JsonPath.read(body, "$.id");
    return UUID.fromString(idStr);
  }

  /** Deactivates a template by updating active=false. */
  private void deactivateTemplate(UUID templateId) throws Exception {
    mockMvc
        .perform(
            put(
                    "/api/accounts/{accountId}/recurring-templates/{templateId}",
                    testAccount.getId(),
                    templateId)
                .with(user("test@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"active": false}
                    """))
        .andExpect(status().isOk());
  }
}
