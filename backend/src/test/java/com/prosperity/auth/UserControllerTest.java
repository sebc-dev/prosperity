package com.prosperity.auth;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.prosperity.TestcontainersConfig;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestcontainersConfig.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class UserControllerTest {

  @Autowired private MockMvc mockMvc;
  @Autowired private UserRepository userRepository;

  @Test
  void list_users_returns_all_users() throws Exception {
    setupUser("alice@test.com");
    setupUser("bob@test.com");

    mockMvc
        .perform(get("/api/users").with(user("alice@test.com")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.length()").value(2));
  }

  @Test
  void list_users_returns_401_when_unauthenticated() throws Exception {
    mockMvc
        .perform(get("/api/users"))
        .andExpect(status().isUnauthorized());
  }

  private User setupUser(String email) {
    User user = new User(email, "{bcrypt}$2a$10$hashedpassword", email.split("@")[0]);
    return userRepository.save(user);
  }
}
