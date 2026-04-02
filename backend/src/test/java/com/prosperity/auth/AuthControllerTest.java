package com.prosperity.auth;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.prosperity.TestcontainersConfig;
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
 * Integration tests for AuthController endpoints. Uses a real PostgreSQL database via
 * Testcontainers and full Spring context.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestcontainersConfig.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class AuthControllerTest {

  @Autowired private MockMvc mockMvc;

  private static final String VALID_SETUP_JSON =
      """
      {"email":"admin@test.com","password":"SecurePass123!","displayName":"Admin User"}
      """;

  @Test
  void setup_creates_admin_and_returns_201() throws Exception {
    var result =
        mockMvc.perform(
            post("/api/auth/setup")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_SETUP_JSON));

    result
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.displayName").value("Admin User"))
        .andExpect(jsonPath("$.email").value("admin@test.com"))
        .andExpect(jsonPath("$.role").value("ADMIN"));
  }

  @Test
  void setup_returns_409_when_admin_already_exists() throws Exception {
    mockMvc.perform(
        post("/api/auth/setup")
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content(VALID_SETUP_JSON));

    var result =
        mockMvc.perform(
            post("/api/auth/setup")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"email":"other@test.com","password":"AnotherPass123!","displayName":"Other"}
                    """));

    result.andExpect(status().isConflict());
  }

  @Test
  void setup_returns_400_for_invalid_email() throws Exception {
    var result =
        mockMvc.perform(
            post("/api/auth/setup")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"email":"not-an-email","password":"SecurePass123!","displayName":"Admin"}
                    """));

    result.andExpect(status().isBadRequest());
  }

  @Test
  void setup_returns_400_for_weak_password() throws Exception {
    var result =
        mockMvc.perform(
            post("/api/auth/setup")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"email":"admin@test.com","password":"short","displayName":"Admin"}
                    """));

    result.andExpect(status().isBadRequest());
  }

  @Test
  void login_returns_200_with_user_for_valid_credentials() throws Exception {
    mockMvc.perform(
        post("/api/auth/setup")
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content(VALID_SETUP_JSON));

    var result =
        mockMvc.perform(
            post("/api/auth/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"email":"admin@test.com","password":"SecurePass123!"}
                    """));

    result
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.displayName").value("Admin User"))
        .andExpect(jsonPath("$.email").value("admin@test.com"));
  }

  @Test
  void login_returns_401_for_invalid_credentials() throws Exception {
    mockMvc.perform(
        post("/api/auth/setup")
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content(VALID_SETUP_JSON));

    var result =
        mockMvc.perform(
            post("/api/auth/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"email":"admin@test.com","password":"WrongPassword123!"}
                    """));

    result
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.error").value("Identifiants invalides"));
  }

  @Test
  void login_returns_401_for_nonexistent_user() throws Exception {
    var result =
        mockMvc.perform(
            post("/api/auth/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"email":"nobody@test.com","password":"SecurePass123!"}
                    """));

    result
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.error").value("Identifiants invalides"));
  }

  @Test
  void me_returns_user_when_authenticated() throws Exception {
    mockMvc.perform(
        post("/api/auth/setup")
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content(VALID_SETUP_JSON));

    var result =
        mockMvc.perform(
            get("/api/auth/me")
                .with(user("admin@test.com").roles("ADMIN")));

    result
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.displayName").value("Admin User"))
        .andExpect(jsonPath("$.email").value("admin@test.com"));
  }

  @Test
  void me_returns_401_when_not_authenticated() throws Exception {
    var result = mockMvc.perform(get("/api/auth/me"));

    result.andExpect(status().isUnauthorized());
  }

  @Test
  void status_returns_false_when_no_users() throws Exception {
    var result = mockMvc.perform(get("/api/auth/status"));

    result
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.setupComplete").value(false));
  }

  @Test
  void status_returns_true_after_setup() throws Exception {
    mockMvc.perform(
        post("/api/auth/setup")
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content(VALID_SETUP_JSON));

    var result = mockMvc.perform(get("/api/auth/status"));

    result
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.setupComplete").value(true));
  }
}
