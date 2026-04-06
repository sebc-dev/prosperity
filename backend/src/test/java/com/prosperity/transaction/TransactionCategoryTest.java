package com.prosperity.transaction;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.prosperity.TestcontainersConfig;
import com.prosperity.account.Account;
import com.prosperity.account.AccountRepository;
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
 * Integration tests for PATCH /api/transactions/{id}/category endpoint. Uses real PostgreSQL via
 * Testcontainers and full Spring context.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestcontainersConfig.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class TransactionCategoryTest {

  @Autowired private MockMvc mockMvc;
  @Autowired private UserRepository userRepository;
  @Autowired private AccountRepository accountRepository;
  @Autowired private TransactionRepository transactionRepository;
  @Autowired private CategoryRepository categoryRepository;

  @Test
  void update_category_returns_204() throws Exception {
    User owner = setupUser("owner@test.com");
    Account account = createAccount("Test Account");
    Transaction transaction = createTransaction(account);
    Category category = createCategory("Alimentation");

    mockMvc
        .perform(
            patch("/api/transactions/{id}/category", transaction.getId())
                .with(user("owner@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"categoryId\":\"" + category.getId() + "\"}"))
        .andExpect(status().isNoContent());
  }

  @Test
  void clear_category_returns_204() throws Exception {
    User owner = setupUser("owner@test.com");
    Account account = createAccount("Test Account");
    Category category = createCategory("Alimentation");
    Transaction transaction = createTransaction(account);
    transaction.setCategory(category);
    transactionRepository.save(transaction);

    mockMvc
        .perform(
            patch("/api/transactions/{id}/category", transaction.getId())
                .with(user("owner@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"categoryId\":null}"))
        .andExpect(status().isNoContent());
  }

  @Test
  void update_category_transaction_not_found_returns_404() throws Exception {
    setupUser("owner@test.com");
    Category category = createCategory("Alimentation");

    mockMvc
        .perform(
            patch("/api/transactions/{id}/category", UUID.randomUUID())
                .with(user("owner@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"categoryId\":\"" + category.getId() + "\"}"))
        .andExpect(status().isNotFound());
  }

  @Test
  void update_category_category_not_found_returns_404() throws Exception {
    User owner = setupUser("owner@test.com");
    Account account = createAccount("Test Account");
    Transaction transaction = createTransaction(account);

    mockMvc
        .perform(
            patch("/api/transactions/{id}/category", transaction.getId())
                .with(user("owner@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"categoryId\":\"" + UUID.randomUUID() + "\"}"))
        .andExpect(status().isNotFound());
  }

  @Test
  void delete_category_used_by_transactions_returns_409() throws Exception {
    User owner = setupUser("owner@test.com");
    Account account = createAccount("Test Account");
    Category category = createCategory("Utilisee");
    Transaction transaction = createTransaction(account);
    transaction.setCategory(category);
    transaction.setCreatedBy(owner);
    transactionRepository.save(transaction);

    mockMvc
        .perform(
            delete("/api/categories/{id}", category.getId())
                .with(user("owner@test.com"))
                .with(csrf()))
        .andExpect(status().isConflict())
        .andExpect(
            jsonPath("$.error")
                .value(
                    "Cette categorie est utilisee par des transactions et ne peut pas etre supprimee"));
  }

  // ---------------------------------------------------------------------------
  // Test helpers
  // ---------------------------------------------------------------------------

  private User setupUser(String email) {
    User user = new User(email, "{bcrypt}$2a$10$hashedpassword", email.split("@")[0]);
    return userRepository.save(user);
  }

  private Account createAccount(String name) {
    Account account = new Account(name, AccountType.PERSONAL);
    return accountRepository.save(account);
  }

  private Transaction createTransaction(Account account) {
    Transaction transaction =
        new Transaction(account, new Money(new BigDecimal("50.00")), LocalDate.now(), TransactionSource.MANUAL);
    return transactionRepository.save(transaction);
  }

  private Category createCategory(String name) {
    Category category = new Category(name);
    return categoryRepository.save(category);
  }
}
