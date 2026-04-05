package com.prosperity.category;

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
import com.prosperity.account.AccountRepository;
import com.prosperity.auth.User;
import com.prosperity.auth.UserRepository;
import com.prosperity.shared.AccountType;
import com.prosperity.shared.Money;
import com.prosperity.shared.TransactionSource;
import com.prosperity.transaction.Transaction;
import com.prosperity.transaction.TransactionRepository;
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
import org.springframework.test.web.servlet.MvcResult;

/**
 * Integration tests for CategoryController endpoints. Uses a real PostgreSQL database via
 * Testcontainers with Flyway-seeded system categories.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestcontainersConfig.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class CategoryControllerTest {

  @Autowired private MockMvc mockMvc;
  @Autowired private UserRepository userRepository;
  @Autowired private CategoryRepository categoryRepository;
  @Autowired private TransactionRepository transactionRepository;
  @Autowired private AccountRepository accountRepository;

  // ---------------------------------------------------------------------------
  // GET /api/categories
  // ---------------------------------------------------------------------------

  @Test
  void list_returns_seeded_system_categories() throws Exception {
    setupUser("user@test.com");

    mockMvc
        .perform(get("/api/categories").with(user("user@test.com")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.length()").value(org.hamcrest.Matchers.greaterThanOrEqualTo(10)));
  }

  @Test
  void list_returns_categories_with_parent_info() throws Exception {
    setupUser("user@test.com");

    // Courses (child of Alimentation & Restauration) should have parentId and parentName
    mockMvc
        .perform(get("/api/categories").with(user("user@test.com")))
        .andExpect(status().isOk())
        .andExpect(
            jsonPath(
                    "$[?(@.name == 'Courses')].parentName")
                .value(org.hamcrest.Matchers.hasItem("Alimentation & Restauration")));
  }

  // ---------------------------------------------------------------------------
  // POST /api/categories
  // ---------------------------------------------------------------------------

  @Test
  void create_custom_root_category_returns_201() throws Exception {
    setupUser("user@test.com");

    mockMvc
        .perform(
            post("/api/categories")
                .with(user("user@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"name":"Ma Categorie","parentId":null}
                    """))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.name").value("Ma Categorie"))
        .andExpect(jsonPath("$.system").value(false))
        .andExpect(jsonPath("$.parentId").isEmpty());
  }

  @Test
  void create_custom_child_category_returns_201() throws Exception {
    setupUser("user@test.com");
    // Use a seeded root category as parent: Alimentation & Restauration
    String rootId = "a0000000-0000-0000-0000-000000000100";

    mockMvc
        .perform(
            post("/api/categories")
                .with(user("user@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    String.format(
                        """
                        {"name":"Boulangerie","parentId":"%s"}
                        """,
                        rootId)))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.name").value("Boulangerie"))
        .andExpect(jsonPath("$.parentId").value(rootId))
        .andExpect(jsonPath("$.parentName").value("Alimentation & Restauration"))
        .andExpect(jsonPath("$.system").value(false));
  }

  @Test
  void create_category_with_depth_3_returns_400() throws Exception {
    setupUser("user@test.com");
    // Courses is a child category (parent_id != null)
    String childId = "a0000000-0000-0000-0000-000000000101";

    mockMvc
        .perform(
            post("/api/categories")
                .with(user("user@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    String.format(
                        """
                        {"name":"Trop Profond","parentId":"%s"}
                        """,
                        childId)))
        .andExpect(status().isBadRequest())
        .andExpect(
            jsonPath("$.error").value("La categorie parente ne peut pas etre une sous-categorie"));
  }

  @Test
  void create_duplicate_name_returns_409() throws Exception {
    setupUser("user@test.com");
    // Create a custom root category
    mockMvc
        .perform(
            post("/api/categories")
                .with(user("user@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"name":"Unique","parentId":null}
                    """));

    // Try to create another with the same name at root level
    mockMvc
        .perform(
            post("/api/categories")
                .with(user("user@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"name":"Unique","parentId":null}
                    """))
        .andExpect(status().isConflict());
  }

  // ---------------------------------------------------------------------------
  // PUT /api/categories/{id}
  // ---------------------------------------------------------------------------

  @Test
  void update_custom_category_returns_200() throws Exception {
    setupUser("user@test.com");
    UUID customId = createCustomCategory("A Renommer");

    mockMvc
        .perform(
            put("/api/categories/{id}", customId)
                .with(user("user@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"name":"Renommee"}
                    """))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.name").value("Renommee"));
  }

  @Test
  void update_system_category_returns_400() throws Exception {
    setupUser("user@test.com");
    // Alimentation & Restauration is a system category
    String systemId = "a0000000-0000-0000-0000-000000000100";

    mockMvc
        .perform(
            put("/api/categories/{id}", systemId)
                .with(user("user@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"name":"Hacked"}
                    """))
        .andExpect(status().isBadRequest())
        .andExpect(
            jsonPath("$.error")
                .value("Les categories systeme ne peuvent pas etre modifiees"));
  }

  // ---------------------------------------------------------------------------
  // DELETE /api/categories/{id}
  // ---------------------------------------------------------------------------

  @Test
  void delete_custom_unused_category_returns_204() throws Exception {
    setupUser("user@test.com");
    UUID customId = createCustomCategory("A Supprimer");

    mockMvc
        .perform(
            delete("/api/categories/{id}", customId)
                .with(user("user@test.com"))
                .with(csrf()))
        .andExpect(status().isNoContent());
  }

  @Test
  void delete_system_category_returns_400() throws Exception {
    setupUser("user@test.com");
    String systemId = "a0000000-0000-0000-0000-000000000100";

    mockMvc
        .perform(
            delete("/api/categories/{id}", systemId)
                .with(user("user@test.com"))
                .with(csrf()))
        .andExpect(status().isBadRequest())
        .andExpect(
            jsonPath("$.error")
                .value("Les categories systeme ne peuvent pas etre supprimees"));
  }

  @Test
  void delete_category_with_children_returns_409() throws Exception {
    setupUser("user@test.com");
    // Create a root custom category
    UUID parentId = createCustomCategory("Parent");
    // Create a child under it
    createCustomChildCategory("Enfant", parentId);

    mockMvc
        .perform(
            delete("/api/categories/{id}", parentId)
                .with(user("user@test.com"))
                .with(csrf()))
        .andExpect(status().isConflict())
        .andExpect(
            jsonPath("$.error")
                .value(
                    "Impossible de supprimer une categorie qui contient des sous-categories"));
  }

  @Test
  void delete_category_used_by_transactions_returns_409() throws Exception {
    User testUser = setupUser("user@test.com");
    UUID customId = createCustomCategory("Utilisee");

    // Create a minimal transaction referencing this category
    Account account = new Account("Test Account", AccountType.PERSONAL);
    accountRepository.save(account);

    Category category = categoryRepository.findById(customId).orElseThrow();
    Transaction transaction =
        new Transaction(
            account,
            new Money(BigDecimal.valueOf(42)),
            LocalDate.of(2026, 1, 15),
            TransactionSource.MANUAL);
    transaction.setCategory(category);
    transaction.setDescription("Test transaction");
    transaction.setCreatedBy(testUser);
    transactionRepository.save(transaction);

    mockMvc
        .perform(
            delete("/api/categories/{id}", customId)
                .with(user("user@test.com"))
                .with(csrf()))
        .andExpect(status().isConflict())
        .andExpect(
            jsonPath("$.error")
                .value(
                    "Cette categorie est utilisee par des transactions et ne peut pas etre supprimee"));
  }

  @Test
  void delete_nonexistent_category_returns_404() throws Exception {
    setupUser("user@test.com");

    mockMvc
        .perform(
            delete("/api/categories/{id}", UUID.randomUUID())
                .with(user("user@test.com"))
                .with(csrf()))
        .andExpect(status().isNotFound());
  }

  // ---------------------------------------------------------------------------
  // Test helpers
  // ---------------------------------------------------------------------------

  private User setupUser(String email) {
    User user = new User(email, "{bcrypt}$2a$10$hashedpassword", email.split("@")[0]);
    return userRepository.save(user);
  }

  /**
   * Creates a custom root category via the API and returns its UUID. Uses MockMvc to exercise the
   * full stack.
   */
  private UUID createCustomCategory(String name) throws Exception {
    MvcResult result =
        mockMvc
            .perform(
                post("/api/categories")
                    .with(user("user@test.com"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(String.format("""
                        {"name":"%s","parentId":null}
                        """, name)))
            .andExpect(status().isCreated())
            .andReturn();

    String body = result.getResponse().getContentAsString();
    // Extract id from JSON response
    String idStr = body.split("\"id\":\"")[1].split("\"")[0];
    return UUID.fromString(idStr);
  }

  /**
   * Creates a custom child category via the API and returns its UUID.
   */
  private UUID createCustomChildCategory(String name, UUID parentId) throws Exception {
    MvcResult result =
        mockMvc
            .perform(
                post("/api/categories")
                    .with(user("user@test.com"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        String.format(
                            """
                            {"name":"%s","parentId":"%s"}
                            """,
                            name, parentId)))
            .andExpect(status().isCreated())
            .andReturn();

    String body = result.getResponse().getContentAsString();
    String idStr = body.split("\"id\":\"")[1].split("\"")[0];
    return UUID.fromString(idStr);
  }
}
