package fr.kalifazzia.prosperity.user;

import com.fasterxml.jackson.databind.ObjectMapper;
import fr.kalifazzia.prosperity.auth.JwtService;
import fr.kalifazzia.prosperity.user.dto.ChangePasswordRequest;
import fr.kalifazzia.prosperity.user.dto.CreateUserRequest;
import fr.kalifazzia.prosperity.user.dto.UpdatePreferencesRequest;
import fr.kalifazzia.prosperity.user.dto.UpdateProfileRequest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Testcontainers
class UserServiceTest {

    @Container
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("prosperity_test")
            .withUsername("test")
            .withPassword("test");

    @DynamicPropertySource
    static void configureProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("app.jwt.secret", () -> "test-secret-key-that-is-at-least-32-bytes-long-for-hmac-sha256");
        registry.add("app.jwt.access-expiry", () -> "900");
        registry.add("app.jwt.refresh-expiry", () -> "2592000");
    }

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private JwtService jwtService;

    @Autowired
    private PasswordEncoder passwordEncoder;

    private User adminUser;
    private User standardUser;
    private String adminToken;
    private String standardToken;

    @BeforeEach
    void setUp() {
        userRepository.deleteAll();

        adminUser = new User(
                UUID.randomUUID(),
                "admin@test.com",
                passwordEncoder.encode("password123"),
                "Admin User",
                SystemRole.ADMIN
        );
        userRepository.save(adminUser);

        standardUser = new User(
                UUID.randomUUID(),
                "standard@test.com",
                passwordEncoder.encode("password123"),
                "Standard User",
                SystemRole.STANDARD
        );
        userRepository.save(standardUser);

        adminToken = jwtService.generateAccessToken(adminUser);
        standardToken = jwtService.generateAccessToken(standardUser);
    }

    @Test
    void updateProfile_updatesDisplayName() throws Exception {
        UpdateProfileRequest request = new UpdateProfileRequest("New Admin Name");

        mockMvc.perform(patch("/api/users/me/profile")
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName").value("New Admin Name"));

        // Verify persisted
        User updated = userRepository.findById(adminUser.getId()).orElseThrow();
        assertThat(updated.getDisplayName()).isEqualTo("New Admin Name");
    }

    @Test
    void updatePreferences_savesJsonb() throws Exception {
        UpdatePreferencesRequest request = new UpdatePreferencesRequest(
                "dark", "fr", "EUR", List.of("cat-1", "cat-2")
        );

        mockMvc.perform(patch("/api/users/me/preferences")
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.preferences.theme").value("dark"))
                .andExpect(jsonPath("$.preferences.locale").value("fr"))
                .andExpect(jsonPath("$.preferences.defaultCurrency").value("EUR"));
    }

    @Test
    void changePassword_success() throws Exception {
        ChangePasswordRequest request = new ChangePasswordRequest(
                "password123", "newPassword456", "newPassword456"
        );

        mockMvc.perform(post("/api/users/me/password")
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk());

        // Verify password changed
        User updated = userRepository.findById(adminUser.getId()).orElseThrow();
        assertThat(passwordEncoder.matches("newPassword456", updated.getPasswordHash())).isTrue();
    }

    @Test
    void changePassword_wrongOldPassword_returns400() throws Exception {
        ChangePasswordRequest request = new ChangePasswordRequest(
                "wrongOldPassword", "newPassword456", "newPassword456"
        );

        mockMvc.perform(post("/api/users/me/password")
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void changePassword_mismatchedNewPasswords_returns400() throws Exception {
        ChangePasswordRequest request = new ChangePasswordRequest(
                "password123", "newPassword456", "differentPassword"
        );

        mockMvc.perform(post("/api/users/me/password")
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void createUser_adminCanCreateStandardUser() throws Exception {
        CreateUserRequest request = new CreateUserRequest(
                "newuser@test.com", "New User", "tempPassword123"
        );

        mockMvc.perform(post("/api/users")
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.email").value("newuser@test.com"))
                .andExpect(jsonPath("$.displayName").value("New User"))
                .andExpect(jsonPath("$.systemRole").value("STANDARD"))
                .andExpect(jsonPath("$.forcePasswordChange").value(true));

        // Verify password is stored as bcrypt
        User created = userRepository.findByEmail("newuser@test.com").orElseThrow();
        assertThat(passwordEncoder.matches("tempPassword123", created.getPasswordHash())).isTrue();
    }

    @Test
    void createUser_standardUserCannotCreate_returns403() throws Exception {
        CreateUserRequest request = new CreateUserRequest(
                "another@test.com", "Another User", "tempPassword123"
        );

        mockMvc.perform(post("/api/users")
                        .header("Authorization", "Bearer " + standardToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isForbidden());
    }

    @Test
    void getCurrentUser_returnsProfileWithPreferences() throws Exception {
        mockMvc.perform(get("/api/users/me")
                        .header("Authorization", "Bearer " + adminToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.email").value("admin@test.com"))
                .andExpect(jsonPath("$.displayName").value("Admin User"))
                .andExpect(jsonPath("$.systemRole").value("ADMIN"));
    }

    @Test
    void listUsers_adminCanList() throws Exception {
        mockMvc.perform(get("/api/users")
                        .header("Authorization", "Bearer " + adminToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2));
    }

    @Test
    void listUsers_standardUserCannotList_returns403() throws Exception {
        mockMvc.perform(get("/api/users")
                        .header("Authorization", "Bearer " + standardToken))
                .andExpect(status().isForbidden());
    }
}
