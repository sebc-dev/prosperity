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
import com.prosperity.auth.User;
import com.prosperity.auth.UserRepository;
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

  // ---------------------------------------------------------------------------
  // GET /api/categories
  // ---------------------------------------------------------------------------

  @Test
  void list_returns_seeded_system_categories() throws Exception {
    setupUser("user@test.com");

    mockMvc
        .perform(get("/api/categories").with(user("user@test.com")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.length()").value(49)); // V011 seeds 49 system categories
  }

  @Test
  void list_returns_categories_with_parent_info() throws Exception {
    setupUser("user@test.com");

    // Courses (child of Alimentation & Restauration) should have parentId and parentName
    mockMvc
        .perform(get("/api/categories").with(user("user@test.com")))
        .andExpect(status().isOk())
        .andExpect(
            jsonPath("$[?(@.name == 'Courses')].parentName")
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
                        """))
        .andExpect(status().isCreated());

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
            jsonPath("$.error").value("Les categories systeme ne peuvent pas etre modifiees"));
  }

  @Test
  void update_nonexistent_category_returns_404() throws Exception {
    setupUser("user@test.com");

    mockMvc
        .perform(
            put("/api/categories/{id}", UUID.randomUUID())
                .with(user("user@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                        {"name":"Whatever"}
                        """))
        .andExpect(status().isNotFound());
  }

  @Test
  void update_duplicate_name_returns_409() throws Exception {
    setupUser("user@test.com");
    UUID catAId = createCustomCategory("CatA");
    createCustomCategory("CatB");

    mockMvc
        .perform(
            put("/api/categories/{id}", catAId)
                .with(user("user@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                        {"name":"CatB"}
                        """))
        .andExpect(status().isConflict());
  }

  // ---------------------------------------------------------------------------
  // DELETE /api/categories/{id}
  // ---------------------------------------------------------------------------

  @Test
  void delete_custom_unused_category_returns_204() throws Exception {
    setupUser("user@test.com");
    UUID customId = createCustomCategory("A Supprimer");

    mockMvc
        .perform(delete("/api/categories/{id}", customId).with(user("user@test.com")).with(csrf()))
        .andExpect(status().isNoContent());
  }

  @Test
  void delete_system_category_returns_400() throws Exception {
    setupUser("user@test.com");
    String systemId = "a0000000-0000-0000-0000-000000000100";

    mockMvc
        .perform(delete("/api/categories/{id}", systemId).with(user("user@test.com")).with(csrf()))
        .andExpect(status().isBadRequest())
        .andExpect(
            jsonPath("$.error").value("Les categories systeme ne peuvent pas etre supprimees"));
  }

  @Test
  void delete_category_with_children_returns_409() throws Exception {
    setupUser("user@test.com");
    // Create a root custom category
    UUID parentId = createCustomCategory("Parent");
    // Create a child under it
    createCustomChildCategory("Enfant", parentId);

    mockMvc
        .perform(delete("/api/categories/{id}", parentId).with(user("user@test.com")).with(csrf()))
        .andExpect(status().isConflict())
        .andExpect(
            jsonPath("$.error")
                .value("Impossible de supprimer une categorie qui contient des sous-categories"));
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
                    .content(
                        String.format(
                            """
                        {"name":"%s","parentId":null}
                        """,
                            name)))
            .andExpect(status().isCreated())
            .andReturn();

    String body = result.getResponse().getContentAsString();
    String idStr = com.jayway.jsonpath.JsonPath.read(body, "$.id");
    return UUID.fromString(idStr);
  }

  /** Creates a custom child category via the API and returns its UUID. */
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
    String idStr = com.jayway.jsonpath.JsonPath.read(body, "$.id");
    return UUID.fromString(idStr);
  }
}
