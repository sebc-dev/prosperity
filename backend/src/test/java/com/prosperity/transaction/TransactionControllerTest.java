package com.prosperity.transaction;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
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
import com.prosperity.category.Category;
import com.prosperity.category.CategoryRepository;
import com.prosperity.shared.AccountType;
import com.prosperity.shared.Money;
import com.prosperity.shared.TransactionSource;
import java.math.BigDecimal;
import java.time.LocalDate;
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
 * Integration tests for TransactionController endpoints. Covers CRUD, pagination, filters,
 * pointage, splits, and access control. Uses real PostgreSQL via Testcontainers.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestcontainersConfig.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class TransactionControllerTest {

  @Autowired private MockMvc mockMvc;
  @Autowired private UserRepository userRepository;
  @Autowired private AccountRepository accountRepository;
  @Autowired private AccountAccessRepository accountAccessRepository;
  @Autowired private TransactionRepository transactionRepository;
  @Autowired private CategoryRepository categoryRepository;

  private User testUser;
  private Account testAccount;
  private Category testCategory;

  @BeforeEach
  void setUp() {
    testUser = userRepository.save(new User("test@test.com", "{bcrypt}$2a$10$hash", "Test User"));
    testAccount = accountRepository.save(new Account("Compte Courant", AccountType.PERSONAL));
    accountAccessRepository.save(new AccountAccess(testUser, testAccount, AccessLevel.WRITE));

    // Use a seeded system category (Courses)
    testCategory =
        categoryRepository
            .findById(UUID.fromString("a0000000-0000-0000-0000-000000000101"))
            .orElseThrow();
  }

  // ---------------------------------------------------------------------------
  // CREATE (TXNS-01)
  // ---------------------------------------------------------------------------

  @Test
  void create_manual_transaction_returns_201_with_response() throws Exception {
    // Arrange — test data inline

    // Act
    mockMvc
        .perform(
            post("/api/accounts/{accountId}/transactions", testAccount.getId())
                .with(user("test@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    String.format(
                        """
                        {"amount": -45.30, "transactionDate": "2026-04-07", \
                        "description": "Courses Lidl", "categoryId": "%s"}
                        """,
                        testCategory.getId())))

        // Assert
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.amount").value(-45.30))
        .andExpect(jsonPath("$.description").value("Courses Lidl"))
        .andExpect(jsonPath("$.source").value("MANUAL"))
        .andExpect(jsonPath("$.state").value("MANUAL_UNMATCHED"))
        .andExpect(jsonPath("$.pointed").value(false))
        .andExpect(jsonPath("$.categoryId").value(testCategory.getId().toString()))
        .andExpect(jsonPath("$.accountId").value(testAccount.getId().toString()));
  }

  @Test
  void create_transaction_without_write_access_returns_403() throws Exception {
    // Arrange — second user with no access
    User noAccessUser =
        userRepository.save(
            new User("noaccess@test.com", "{bcrypt}$2a$10$hash", "No Access User"));

    // Act
    mockMvc
        .perform(
            post("/api/accounts/{accountId}/transactions", testAccount.getId())
                .with(user("noaccess@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"amount": -10.00, "transactionDate": "2026-04-07", "description": "Test"}
                    """))

        // Assert
        .andExpect(status().isForbidden());
  }

  @Test
  void create_transaction_on_nonexistent_account_returns_404() throws Exception {
    // Arrange
    UUID fakeAccountId = UUID.randomUUID();

    // Act
    mockMvc
        .perform(
            post("/api/accounts/{accountId}/transactions", fakeAccountId)
                .with(user("test@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"amount": -10.00, "transactionDate": "2026-04-07", "description": "Test"}
                    """))

        // Assert
        .andExpect(status().isNotFound());
  }

  @Test
  void create_transaction_with_invalid_category_returns_404() throws Exception {
    // Arrange
    UUID fakeCategoryId = UUID.randomUUID();

    // Act
    mockMvc
        .perform(
            post("/api/accounts/{accountId}/transactions", testAccount.getId())
                .with(user("test@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    String.format(
                        """
                        {"amount": -10.00, "transactionDate": "2026-04-07", \
                        "description": "Test", "categoryId": "%s"}
                        """,
                        fakeCategoryId)))

        // Assert
        .andExpect(status().isNotFound());
  }

  // ---------------------------------------------------------------------------
  // PAGINATION (TXNS-08)
  // ---------------------------------------------------------------------------

  @Test
  void get_transactions_paginated_returns_page_with_content() throws Exception {
    // Arrange — create 25 transactions directly in the database
    for (int i = 0; i < 25; i++) {
      Transaction tx =
          new Transaction(
              testAccount,
              new Money(new BigDecimal("-10.00")),
              LocalDate.of(2026, 4, 1).plusDays(i % 28),
              TransactionSource.MANUAL);
      tx.setDescription("Transaction " + i);
      tx.setCreatedBy(testUser);
      transactionRepository.save(tx);
    }

    // Act
    mockMvc
        .perform(
            get("/api/accounts/{accountId}/transactions", testAccount.getId())
                .with(user("test@test.com"))
                .param("page", "0")
                .param("size", "10"))

        // Assert
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.content.length()").value(10))
        .andExpect(jsonPath("$.totalElements").value(25))
        .andExpect(jsonPath("$.totalPages").value(3));
  }

  // ---------------------------------------------------------------------------
  // FILTERS (TXNS-07)
  // ---------------------------------------------------------------------------

  @Test
  void get_transactions_filtered_by_date_range() throws Exception {
    // Arrange — transactions on 3 different dates
    createTransactionDirectly(new BigDecimal("-10.00"), LocalDate.of(2026, 3, 1), "March");
    createTransactionDirectly(new BigDecimal("-20.00"), LocalDate.of(2026, 4, 15), "April");
    createTransactionDirectly(new BigDecimal("-30.00"), LocalDate.of(2026, 5, 1), "May");

    // Act
    mockMvc
        .perform(
            get("/api/accounts/{accountId}/transactions", testAccount.getId())
                .with(user("test@test.com"))
                .param("dateFrom", "2026-04-01")
                .param("dateTo", "2026-04-30"))

        // Assert
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.content.length()").value(1))
        .andExpect(jsonPath("$.content[0].description").value("April"));
  }

  @Test
  void get_transactions_filtered_by_amount_range() throws Exception {
    // Arrange
    createTransactionDirectly(new BigDecimal("-5.00"), LocalDate.of(2026, 4, 7), "Small");
    createTransactionDirectly(new BigDecimal("-50.00"), LocalDate.of(2026, 4, 7), "Medium");
    createTransactionDirectly(new BigDecimal("-500.00"), LocalDate.of(2026, 4, 7), "Large");

    // Act
    mockMvc
        .perform(
            get("/api/accounts/{accountId}/transactions", testAccount.getId())
                .with(user("test@test.com"))
                .param("amountMin", "-100.00")
                .param("amountMax", "-10.00"))

        // Assert
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.content.length()").value(1))
        .andExpect(jsonPath("$.content[0].description").value("Medium"));
  }

  @Test
  void get_transactions_filtered_by_category() throws Exception {
    // Arrange
    createTransactionDirectly(new BigDecimal("-10.00"), LocalDate.of(2026, 4, 7), "With cat");
    Transaction withCat = transactionRepository.findAll().stream()
        .filter(t -> "With cat".equals(t.getDescription()))
        .findFirst()
        .orElseThrow();
    withCat.setCategory(testCategory);
    transactionRepository.save(withCat);

    createTransactionDirectly(new BigDecimal("-20.00"), LocalDate.of(2026, 4, 7), "No cat");

    // Act
    mockMvc
        .perform(
            get("/api/accounts/{accountId}/transactions", testAccount.getId())
                .with(user("test@test.com"))
                .param("categoryId", testCategory.getId().toString()))

        // Assert
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.content.length()").value(1))
        .andExpect(jsonPath("$.content[0].description").value("With cat"));
  }

  @Test
  void get_transactions_filtered_by_search_text() throws Exception {
    // Arrange
    createTransactionDirectly(new BigDecimal("-45.00"), LocalDate.of(2026, 4, 7), "Courses Lidl");
    createTransactionDirectly(
        new BigDecimal("-12.00"), LocalDate.of(2026, 4, 7), "Boulangerie Paul");

    // Act
    mockMvc
        .perform(
            get("/api/accounts/{accountId}/transactions", testAccount.getId())
                .with(user("test@test.com"))
                .param("search", "Lidl"))

        // Assert
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.content.length()").value(1))
        .andExpect(jsonPath("$.content[0].description").value("Courses Lidl"));
  }

  // ---------------------------------------------------------------------------
  // UPDATE (TXNS-02)
  // ---------------------------------------------------------------------------

  @Test
  void update_manual_transaction_returns_updated_response() throws Exception {
    // Arrange
    UUID txId = createTransactionViaApi(new BigDecimal("-45.30"), "Courses Lidl");

    // Act
    mockMvc
        .perform(
            put("/api/transactions/{id}", txId)
                .with(user("test@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"amount": -50.00, "description": "Courses Carrefour"}
                    """))

        // Assert
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.amount").value(-50.00))
        .andExpect(jsonPath("$.description").value("Courses Carrefour"));
  }

  @Test
  void update_non_manual_transaction_returns_400() throws Exception {
    // Arrange — create a RECURRING transaction directly
    Transaction recurringTx =
        new Transaction(
            testAccount,
            new Money(new BigDecimal("-100.00")),
            LocalDate.of(2026, 4, 7),
            TransactionSource.RECURRING);
    recurringTx.setDescription("Loyer");
    recurringTx.setCreatedBy(testUser);
    transactionRepository.save(recurringTx);

    // Act
    mockMvc
        .perform(
            put("/api/transactions/{id}", recurringTx.getId())
                .with(user("test@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"description": "Hacked"}
                    """))

        // Assert
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error").exists());
  }

  // ---------------------------------------------------------------------------
  // DELETE (TXNS-03)
  // ---------------------------------------------------------------------------

  @Test
  void delete_manual_transaction_returns_204() throws Exception {
    // Arrange
    UUID txId = createTransactionViaApi(new BigDecimal("-10.00"), "A supprimer");

    // Act
    mockMvc
        .perform(
            delete("/api/transactions/{id}", txId)
                .with(user("test@test.com"))
                .with(csrf()))

        // Assert
        .andExpect(status().isNoContent());
  }

  @Test
  void delete_non_manual_transaction_returns_400() throws Exception {
    // Arrange
    Transaction recurringTx =
        new Transaction(
            testAccount,
            new Money(new BigDecimal("-100.00")),
            LocalDate.of(2026, 4, 7),
            TransactionSource.RECURRING);
    recurringTx.setDescription("Loyer");
    recurringTx.setCreatedBy(testUser);
    transactionRepository.save(recurringTx);

    // Act
    mockMvc
        .perform(
            delete("/api/transactions/{id}", recurringTx.getId())
                .with(user("test@test.com"))
                .with(csrf()))

        // Assert
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error").exists());
  }

  // ---------------------------------------------------------------------------
  // POINTAGE (TXNS-05)
  // ---------------------------------------------------------------------------

  @Test
  void toggle_pointed_flips_boolean() throws Exception {
    // Arrange
    UUID txId = createTransactionViaApi(new BigDecimal("-10.00"), "Pointage test");

    // Act — first toggle: false -> true
    mockMvc
        .perform(
            patch("/api/transactions/{id}/pointed", txId)
                .with(user("test@test.com"))
                .with(csrf()))

        // Assert
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.pointed").value(true));

    // Act — second toggle: true -> false
    mockMvc
        .perform(
            patch("/api/transactions/{id}/pointed", txId)
                .with(user("test@test.com"))
                .with(csrf()))

        // Assert
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.pointed").value(false));
  }

  // ---------------------------------------------------------------------------
  // SPLITS (TXNS-06)
  // ---------------------------------------------------------------------------

  @Test
  void set_splits_with_valid_sum_returns_transaction_with_null_category() throws Exception {
    // Arrange — transaction with a category
    UUID txId = createTransactionViaApi(new BigDecimal("-100.00"), "Split test");
    // Use two distinct seeded categories
    String cat1Id = "a0000000-0000-0000-0000-000000000101"; // Courses
    String cat2Id = "a0000000-0000-0000-0000-000000000102"; // Restaurants

    // Act
    mockMvc
        .perform(
            put("/api/transactions/{id}/splits", txId)
                .with(user("test@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    String.format(
                        """
                        [
                          {"categoryId": "%s", "amount": -60.00, "description": "Courses"},
                          {"categoryId": "%s", "amount": -40.00, "description": "Restaurant"}
                        ]
                        """,
                        cat1Id, cat2Id)))

        // Assert
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.categoryId").isEmpty())
        .andExpect(jsonPath("$.splits.length()").value(2));
  }

  @Test
  void set_splits_with_invalid_sum_returns_400() throws Exception {
    // Arrange — transaction with amount -100.00
    UUID txId = createTransactionViaApi(new BigDecimal("-100.00"), "Bad split");
    String catId = "a0000000-0000-0000-0000-000000000101";

    // Act — splits sum to -90.00, not -100.00
    mockMvc
        .perform(
            put("/api/transactions/{id}/splits", txId)
                .with(user("test@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    String.format(
                        """
                        [
                          {"categoryId": "%s", "amount": -50.00, "description": "Part 1"},
                          {"categoryId": "%s", "amount": -40.00, "description": "Part 2"}
                        ]
                        """,
                        catId, catId)))

        // Assert
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error").exists());
  }

  @Test
  void clear_splits_returns_transaction() throws Exception {
    // Arrange — create transaction and add splits
    UUID txId = createTransactionViaApi(new BigDecimal("-100.00"), "Clear split test");
    String catId = "a0000000-0000-0000-0000-000000000101";
    mockMvc
        .perform(
            put("/api/transactions/{id}/splits", txId)
                .with(user("test@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    String.format(
                        """
                        [{"categoryId": "%s", "amount": -100.00, "description": "All"}]
                        """,
                        catId)));

    // Act
    mockMvc
        .perform(
            delete("/api/transactions/{id}/splits", txId)
                .with(user("test@test.com"))
                .with(csrf()))

        // Assert
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.splits.length()").value(0));
  }

  // ---------------------------------------------------------------------------
  // Test helpers
  // ---------------------------------------------------------------------------

  private void createTransactionDirectly(BigDecimal amount, LocalDate date, String description) {
    Transaction tx = new Transaction(testAccount, new Money(amount), date, TransactionSource.MANUAL);
    tx.setDescription(description);
    tx.setCreatedBy(testUser);
    transactionRepository.save(tx);
  }

  /**
   * Creates a transaction via the API and returns its UUID. Exercises the full HTTP stack to ensure
   * consistent state.
   */
  private UUID createTransactionViaApi(BigDecimal amount, String description) throws Exception {
    MvcResult result =
        mockMvc
            .perform(
                post("/api/accounts/{accountId}/transactions", testAccount.getId())
                    .with(user("test@test.com"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        String.format(
                            """
                            {"amount": %s, "transactionDate": "2026-04-07", \
                            "description": "%s"}
                            """,
                            amount, description)))
            .andExpect(status().isCreated())
            .andReturn();

    String body = result.getResponse().getContentAsString();
    String idStr = com.jayway.jsonpath.JsonPath.read(body, "$.id");
    return UUID.fromString(idStr);
  }
}
