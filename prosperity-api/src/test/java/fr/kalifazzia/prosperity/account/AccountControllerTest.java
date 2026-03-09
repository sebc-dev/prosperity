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
    void createPersonalAccount_onlyOwnerCanSee() throws Exception {
        CreateAccountRequest request = new CreateAccountRequest(
                "Mon Compte Courant", "BNP Paribas", AccountType.PERSONAL,
                "EUR", BigDecimal.valueOf(1500.00), "#3B82F6"
        );

        // Admin creates a personal account
        mockMvc.perform(post("/api/accounts")
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name").value("Mon Compte Courant"))
                .andExpect(jsonPath("$.bankName").value("BNP Paribas"))
                .andExpect(jsonPath("$.accountType").value("PERSONAL"))
                .andExpect(jsonPath("$.currency").value("EUR"))
                .andExpect(jsonPath("$.permissionLevel").value("MANAGE"));

        // Admin can see it
        mockMvc.perform(get("/api/accounts")
                        .header("Authorization", "Bearer " + adminToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].name").value("Mon Compte Courant"));

        // Standard user cannot see admin's personal account
        mockMvc.perform(get("/api/accounts")
                        .header("Authorization", "Bearer " + standardToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(0));
    }

    @Test
    void createSharedAccount_bothUsersSeeIt() throws Exception {
        CreateAccountRequest request = new CreateAccountRequest(
                "Compte Joint", "Societe Generale", AccountType.SHARED,
                "EUR", BigDecimal.valueOf(3000.00), "#10B981"
        );

        // Admin creates a shared account
        mockMvc.perform(post("/api/accounts")
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.accountType").value("SHARED"))
                .andExpect(jsonPath("$.permissionLevel").value("MANAGE"));

        // Admin sees it
        mockMvc.perform(get("/api/accounts")
                        .header("Authorization", "Bearer " + adminToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].name").value("Compte Joint"));

        // Standard user also sees it
        mockMvc.perform(get("/api/accounts")
                        .header("Authorization", "Bearer " + standardToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].name").value("Compte Joint"))
                .andExpect(jsonPath("$[0].permissionLevel").value("WRITE"));
    }

    @Test
    void visibilityIsolation_userACannotSeeUserBPersonalAccounts() throws Exception {
        // Admin creates personal account
        CreateAccountRequest adminAccount = new CreateAccountRequest(
                "Admin Personal", "BNP", AccountType.PERSONAL,
                "EUR", BigDecimal.valueOf(1000.00), "#EF4444"
        );
        mockMvc.perform(post("/api/accounts")
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(adminAccount)))
                .andExpect(status().isCreated());

        // Standard user creates personal account
        CreateAccountRequest standardAccount = new CreateAccountRequest(
                "Standard Personal", "SG", AccountType.PERSONAL,
                "EUR", BigDecimal.valueOf(500.00), "#8B5CF6"
        );
        mockMvc.perform(post("/api/accounts")
                        .header("Authorization", "Bearer " + standardToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(standardAccount)))
                .andExpect(status().isCreated());

        // Admin only sees their personal account
        mockMvc.perform(get("/api/accounts")
                        .header("Authorization", "Bearer " + adminToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].name").value("Admin Personal"));

        // Standard user only sees their personal account
        mockMvc.perform(get("/api/accounts")
                        .header("Authorization", "Bearer " + standardToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].name").value("Standard Personal"));
    }

    @Test
    void createAccount_withoutAuth_returns401() throws Exception {
        CreateAccountRequest request = new CreateAccountRequest(
                "Test Account", "BNP", AccountType.PERSONAL,
                "EUR", BigDecimal.ZERO, "#000000"
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
