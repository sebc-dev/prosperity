package com.prosperity.account;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.prosperity.TestcontainersConfig;
import com.prosperity.auth.User;
import com.prosperity.auth.UserRepository;
import com.prosperity.shared.AccountType;
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
 * Integration tests for AccountController endpoints. Uses a real PostgreSQL database via
 * Testcontainers and full Spring context.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestcontainersConfig.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class AccountControllerTest {

  @Autowired private MockMvc mockMvc;
  @Autowired private UserRepository userRepository;
  @Autowired private AccountRepository accountRepository;
  @Autowired private AccountAccessRepository accountAccessRepository;

  // ---------------------------------------------------------------------------
  // Account CRUD
  // ---------------------------------------------------------------------------

  @Test
  void create_personal_account_returns_201_with_admin_access() throws Exception {
    setupUser("admin@test.com");

    mockMvc
        .perform(
            post("/api/accounts")
                .with(user("admin@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"name":"Compte Courant","accountType":"PERSONAL"}
                    """))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.name").value("Compte Courant"))
        .andExpect(jsonPath("$.accountType").value("PERSONAL"))
        .andExpect(jsonPath("$.currentUserAccessLevel").value("ADMIN"));
  }

  @Test
  void create_shared_account_returns_201_and_creator_has_admin() throws Exception {
    setupUser("admin@test.com");

    mockMvc
        .perform(
            post("/api/accounts")
                .with(user("admin@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"name":"Compte Commun","accountType":"SHARED"}
                    """))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.accountType").value("SHARED"))
        .andExpect(jsonPath("$.currentUserAccessLevel").value("ADMIN"));
  }

  @Test
  void list_accounts_returns_only_accessible_accounts() throws Exception {
    User owner = setupUser("owner@test.com");
    User other = setupUser("other@test.com");
    Account accessible = createAccount("Accessible", AccountType.PERSONAL);
    Account inaccessible = createAccount("Inaccessible", AccountType.PERSONAL);
    grantAccess(owner, accessible, AccessLevel.ADMIN);
    grantAccess(other, inaccessible, AccessLevel.ADMIN);

    mockMvc
        .perform(get("/api/accounts").with(user("owner@test.com")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.length()").value(1))
        .andExpect(jsonPath("$[0].name").value("Accessible"));
  }

  @Test
  void list_accounts_excludes_archived_by_default() throws Exception {
    User owner = setupUser("owner@test.com");
    Account archived = createAccount("Archived", AccountType.PERSONAL);
    archived.setArchived(true);
    accountRepository.save(archived);
    grantAccess(owner, archived, AccessLevel.ADMIN);

    mockMvc
        .perform(get("/api/accounts").with(user("owner@test.com")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.length()").value(0));
  }

  @Test
  void list_accounts_includes_archived_when_requested() throws Exception {
    User owner = setupUser("owner@test.com");
    Account archived = createAccount("Old Account", AccountType.PERSONAL);
    archived.setArchived(true);
    accountRepository.save(archived);
    grantAccess(owner, archived, AccessLevel.ADMIN);

    mockMvc
        .perform(
            get("/api/accounts")
                .with(user("owner@test.com"))
                .param("includeArchived", "true"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.length()").value(1))
        .andExpect(jsonPath("$[0].archived").value(true));
  }

  @Test
  void get_account_returns_403_when_no_access() throws Exception {
    setupUser("other@test.com");
    Account account = createAccount("Private", AccountType.PERSONAL);

    mockMvc
        .perform(
            get("/api/accounts/{id}", account.getId()).with(user("other@test.com")))
        .andExpect(status().isForbidden());
  }

  @Test
  void update_account_changes_name() throws Exception {
    User owner = setupUser("owner@test.com");
    Account account = createAccount("Old Name", AccountType.PERSONAL);
    grantAccess(owner, account, AccessLevel.ADMIN);

    mockMvc
        .perform(
            patch("/api/accounts/{id}", account.getId())
                .with(user("owner@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"name":"New Name"}
                    """))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.name").value("New Name"));
  }

  @Test
  void update_account_archives_account() throws Exception {
    User owner = setupUser("owner@test.com");
    Account account = createAccount("Active Account", AccountType.PERSONAL);
    grantAccess(owner, account, AccessLevel.ADMIN);

    mockMvc
        .perform(
            patch("/api/accounts/{id}", account.getId())
                .with(user("owner@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"archived":true}
                    """))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.archived").value(true));
  }

  @Test
  void update_account_returns_403_for_read_only_user() throws Exception {
    User reader = setupUser("reader@test.com");
    Account account = createAccount("Shared Account", AccountType.SHARED);
    grantAccess(reader, account, AccessLevel.READ);

    mockMvc
        .perform(
            patch("/api/accounts/{id}", account.getId())
                .with(user("reader@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"name":"Renamed"}
                    """))
        .andExpect(status().isForbidden());
  }

  // ---------------------------------------------------------------------------
  // Access Management
  // ---------------------------------------------------------------------------

  @Test
  void list_access_returns_entries_for_admin() throws Exception {
    User admin = setupUser("admin@test.com");
    Account account = createAccount("My Account", AccountType.PERSONAL);
    grantAccess(admin, account, AccessLevel.ADMIN);

    mockMvc
        .perform(
            get("/api/accounts/{id}/access", account.getId()).with(user("admin@test.com")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.length()").value(1))
        .andExpect(jsonPath("$[0].accessLevel").value("ADMIN"));
  }

  @Test
  void list_access_returns_403_for_non_admin() throws Exception {
    User writer = setupUser("writer@test.com");
    Account account = createAccount("Shared", AccountType.SHARED);
    grantAccess(writer, account, AccessLevel.WRITE);

    mockMvc
        .perform(
            get("/api/accounts/{id}/access", account.getId()).with(user("writer@test.com")))
        .andExpect(status().isForbidden());
  }

  @Test
  void set_access_grants_access_to_new_user() throws Exception {
    User admin = setupUser("admin@test.com");
    User newUser = setupUser("newuser@test.com");
    Account account = createAccount("Shared Account", AccountType.SHARED);
    grantAccess(admin, account, AccessLevel.ADMIN);

    mockMvc
        .perform(
            post("/api/accounts/{id}/access", account.getId())
                .with(user("admin@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    String.format(
                        """
                        {"userId":"%s","accessLevel":"READ"}
                        """,
                        newUser.getId())))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.accessLevel").value("READ"))
        .andExpect(jsonPath("$.userEmail").value("newuser@test.com"));
  }

  @Test
  void remove_access_returns_204() throws Exception {
    User admin = setupUser("admin@test.com");
    User other = setupUser("other@test.com");
    Account account = createAccount("My Account", AccountType.PERSONAL);
    AccountAccess adminAccess = grantAccess(admin, account, AccessLevel.ADMIN);
    AccountAccess otherAccess = grantAccess(other, account, AccessLevel.READ);

    mockMvc
        .perform(
            delete("/api/accounts/{id}/access/{accessId}", account.getId(), otherAccess.getId())
                .with(user("admin@test.com"))
                .with(csrf()))
        .andExpect(status().isNoContent());
  }

  @Test
  void remove_last_admin_returns_409() throws Exception {
    User admin = setupUser("admin@test.com");
    Account account = createAccount("My Account", AccountType.PERSONAL);
    AccountAccess adminAccess = grantAccess(admin, account, AccessLevel.ADMIN);

    mockMvc
        .perform(
            delete("/api/accounts/{id}/access/{accessId}", account.getId(), adminAccess.getId())
                .with(user("admin@test.com"))
                .with(csrf()))
        .andExpect(status().isConflict());
  }

  // ---------------------------------------------------------------------------
  // Unauthenticated requests
  // ---------------------------------------------------------------------------

  @Test
  void unauthenticated_request_returns_401() throws Exception {
    mockMvc
        .perform(get("/api/accounts"))
        .andExpect(status().isUnauthorized());
  }

  @Test
  void unauthenticated_post_without_csrf_returns_403() throws Exception {
    mockMvc
        .perform(
            post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"name":"Test","accountType":"PERSONAL"}
                    """))
        .andExpect(status().isForbidden());
  }

  // ---------------------------------------------------------------------------
  // Validation (@Valid)
  // ---------------------------------------------------------------------------

  @Test
  void create_account_returns_400_when_name_is_blank() throws Exception {
    setupUser("user@test.com");

    mockMvc
        .perform(
            post("/api/accounts")
                .with(user("user@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"name":"","accountType":"PERSONAL"}
                    """))
        .andExpect(status().isBadRequest());
  }

  @Test
  void create_account_returns_400_when_name_is_null() throws Exception {
    setupUser("user@test.com");

    mockMvc
        .perform(
            post("/api/accounts")
                .with(user("user@test.com"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"accountType":"PERSONAL"}
                    """))
        .andExpect(status().isBadRequest());
  }

  // ---------------------------------------------------------------------------
  // GET /{id} happy path
  // ---------------------------------------------------------------------------

  @Test
  void get_account_returns_200_with_correct_fields() throws Exception {
    User owner = setupUser("owner@test.com");
    Account account = createAccount("My Account", AccountType.PERSONAL);
    grantAccess(owner, account, AccessLevel.ADMIN);

    mockMvc
        .perform(
            get("/api/accounts/{id}", account.getId())
                .with(user("owner@test.com")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.name").value("My Account"))
        .andExpect(jsonPath("$.accountType").value("PERSONAL"))
        .andExpect(jsonPath("$.currentUserAccessLevel").value("ADMIN"))
        .andExpect(jsonPath("$.archived").value(false));
  }

  // ---------------------------------------------------------------------------
  // Empty list
  // ---------------------------------------------------------------------------

  @Test
  void list_accounts_returns_empty_array_when_no_accounts_accessible() throws Exception {
    setupUser("loner@test.com");

    mockMvc
        .perform(get("/api/accounts").with(user("loner@test.com")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.length()").value(0));
  }

  // ---------------------------------------------------------------------------
  // Test helpers
  // ---------------------------------------------------------------------------

  private User setupUser(String email) {
    User user = new User(email, "{bcrypt}$2a$10$hashedpassword", email.split("@")[0]);
    return userRepository.save(user);
  }

  private Account createAccount(String name, AccountType type) {
    Account account = new Account(name, type);
    return accountRepository.save(account);
  }

  private AccountAccess grantAccess(User user, Account account, AccessLevel level) {
    AccountAccess access = new AccountAccess(user, account, level);
    return accountAccessRepository.save(access);
  }
}
