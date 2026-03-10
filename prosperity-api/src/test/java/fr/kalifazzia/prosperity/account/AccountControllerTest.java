package fr.kalifazzia.prosperity.account;

import com.fasterxml.jackson.databind.ObjectMapper;
import fr.kalifazzia.prosperity.account.dto.AccountDto;
import fr.kalifazzia.prosperity.account.dto.CreateAccountRequest;
import fr.kalifazzia.prosperity.auth.JwtService;
import fr.kalifazzia.prosperity.auth.dto.AuthResponse;
import fr.kalifazzia.prosperity.auth.dto.SetupRequest;
import fr.kalifazzia.prosperity.user.SystemRole;
import fr.kalifazzia.prosperity.user.User;
import fr.kalifazzia.prosperity.user.UserRepository;
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
import org.springframework.test.web.servlet.MvcResult;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.math.BigDecimal;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Testcontainers
class AccountControllerTest {

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

    @Autowired
    private AccountRepository accountRepository;

    @Autowired
    private PermissionRepository permissionRepository;

    private User adminUser;
    private User standardUser;
    private String adminToken;
    private String standardToken;

    @BeforeEach
    void setUp() {
        permissionRepository.deleteAll();
        accountRepository.deleteAll();
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
    void scenario_personal_account_is_created_then_only_visible_by_owner() throws Exception {
        // Arrange
        CreateAccountRequest request = new CreateAccountRequest(
                "Mon Compte Courant", "BNP Paribas", AccountType.PERSONAL,
                "EUR", BigDecimal.valueOf(1500.00), "#3B82F6", null
        );

        // Act 1 - Admin creates a personal account
        mockMvc.perform(post("/api/accounts")
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                // Assert 1 - Account is created with correct attributes
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name").value("Mon Compte Courant"))
                .andExpect(jsonPath("$.bankName").value("BNP Paribas"))
                .andExpect(jsonPath("$.accountType").value("PERSONAL"))
                .andExpect(jsonPath("$.currency").value("EUR"))
                .andExpect(jsonPath("$.permissionLevel").value("MANAGE"));

        // Act 2 - Admin lists their accounts
        mockMvc.perform(get("/api/accounts")
                        .header("Authorization", "Bearer " + adminToken))
                // Assert 2 - Admin can see the account
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].name").value("Mon Compte Courant"));

        // Act 3 - Standard user lists their accounts
        mockMvc.perform(get("/api/accounts")
                        .header("Authorization", "Bearer " + standardToken))
                // Assert 3 - Standard user cannot see admin's personal account
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(0));
    }

    @Test
    void scenario_shared_account_is_created_then_visible_by_both_users() throws Exception {
        // Arrange
        CreateAccountRequest request = new CreateAccountRequest(
                "Compte Joint", "Societe Generale", AccountType.SHARED,
                "EUR", BigDecimal.valueOf(3000.00), "#10B981", standardUser.getId()
        );

        // Act 1 - Admin creates a shared account
        mockMvc.perform(post("/api/accounts")
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                // Assert 1 - Account is created as shared with MANAGE permission
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.accountType").value("SHARED"))
                .andExpect(jsonPath("$.permissionLevel").value("MANAGE"));

        // Act 2 - Admin lists their accounts
        mockMvc.perform(get("/api/accounts")
                        .header("Authorization", "Bearer " + adminToken))
                // Assert 2 - Admin sees the shared account
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].name").value("Compte Joint"));

        // Act 3 - Standard user lists their accounts
        mockMvc.perform(get("/api/accounts")
                        .header("Authorization", "Bearer " + standardToken))
                // Assert 3 - Standard user sees the shared account with WRITE permission
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].name").value("Compte Joint"))
                .andExpect(jsonPath("$[0].permissionLevel").value("WRITE"));
    }

    @Test
    void scenario_two_users_create_personal_accounts_then_each_sees_only_their_own() throws Exception {
        // Arrange
        CreateAccountRequest adminAccount = new CreateAccountRequest(
                "Admin Personal", "BNP", AccountType.PERSONAL,
                "EUR", BigDecimal.valueOf(1000.00), "#EF4444", null
        );
        CreateAccountRequest standardAccount = new CreateAccountRequest(
                "Standard Personal", "SG", AccountType.PERSONAL,
                "EUR", BigDecimal.valueOf(500.00), "#8B5CF6", null
        );

        // Act 1 - Admin creates personal account
        mockMvc.perform(post("/api/accounts")
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(adminAccount)))
                .andExpect(status().isCreated());

        // Act 2 - Standard user creates personal account
        mockMvc.perform(post("/api/accounts")
                        .header("Authorization", "Bearer " + standardToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(standardAccount)))
                .andExpect(status().isCreated());

        // Act 3 - Admin lists their accounts
        mockMvc.perform(get("/api/accounts")
                        .header("Authorization", "Bearer " + adminToken))
                // Assert 3 - Admin only sees their personal account
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].name").value("Admin Personal"));

        // Act 4 - Standard user lists their accounts
        mockMvc.perform(get("/api/accounts")
                        .header("Authorization", "Bearer " + standardToken))
                // Assert 4 - Standard user only sees their personal account
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].name").value("Standard Personal"));
    }

    @Test
    void createAccount_withoutAuth_returns401() throws Exception {
        CreateAccountRequest request = new CreateAccountRequest(
                "Test Account", "BNP", AccountType.PERSONAL,
                "EUR", BigDecimal.ZERO, "#000000", null
        );

        mockMvc.perform(post("/api/accounts")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void createAccount_withInvalidData_returns400() throws Exception {
        // name is blank
        String invalidJson = "{\"name\":\"\",\"bankName\":\"BNP\",\"accountType\":\"PERSONAL\",\"currency\":\"EUR\",\"initialBalance\":0,\"color\":\"#000\"}";

        mockMvc.perform(post("/api/accounts")
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(invalidJson))
                .andExpect(status().isBadRequest());
    }
}
