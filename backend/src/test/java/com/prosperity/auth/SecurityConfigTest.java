package com.prosperity.auth;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.prosperity.TestcontainersConfig;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

/**
 * Integration tests for SecurityConfig: CSRF enforcement, access control, and public endpoint
 * accessibility.
 */
@SpringBootTest
@AutoConfigureMockMvc
@Import(TestcontainersConfig.class)
@ActiveProfiles("test")
class SecurityConfigTest {

  @Autowired private MockMvc mockMvc;

  @Test
  void csrf_exempt_on_login_and_setup() throws Exception {
    mockMvc
        .perform(
            post("/api/auth/setup")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"email":"admin@test.com","password":"SecurePass123!","displayName":"Admin"}
                    """))
        .andExpect(status().isCreated());

    mockMvc
        .perform(
            post("/api/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"email":"admin@test.com","password":"SecurePass123!"}
                    """))
        .andExpect(status().isOk());
  }

  @Test
  void unauthenticated_request_to_protected_endpoint_returns_401() throws Exception {
    var result = mockMvc.perform(get("/api/some-protected-resource"));

    result.andExpect(status().isUnauthorized());
  }

  @Test
  void public_endpoints_accessible_without_auth() throws Exception {
    mockMvc.perform(get("/api/auth/status")).andExpect(status().isOk());

    mockMvc.perform(get("/actuator/health")).andExpect(status().isOk());
  }

  @Test
  void csrf_enforcement_on_post_to_protected_endpoint_without_token_returns_403() throws Exception {
    var result =
        mockMvc.perform(
            post("/api/some-protected-endpoint")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"));

    result.andExpect(status().isForbidden());
  }
}
