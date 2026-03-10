package fr.kalifazzia.prosperity.auth;

import fr.kalifazzia.prosperity.auth.dto.AuthResponse;
import fr.kalifazzia.prosperity.auth.dto.SetupRequest;
import fr.kalifazzia.prosperity.user.SystemRole;
import fr.kalifazzia.prosperity.user.User;
import fr.kalifazzia.prosperity.shared.exception.BusinessRuleException;
import fr.kalifazzia.prosperity.user.UserRepository;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Service
public class SetupService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final AuthService authService;

    public SetupService(UserRepository userRepository, PasswordEncoder passwordEncoder, AuthService authService) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.authService = authService;
    }

    public boolean isAdminExists() {
        return userRepository.existsBySystemRole(SystemRole.ADMIN);
    }

    @Transactional
    public AuthResponse createAdmin(SetupRequest request) {
        if (isAdminExists()) {
            throw new IllegalStateException("Admin already exists. Setup is locked.");
        }

        User admin = new User(
                UUID.randomUUID(),
                request.email(),
                passwordEncoder.encode(request.password()),
                request.displayName(),
                SystemRole.ADMIN
        );

        try {
            userRepository.save(admin);
        } catch (DataIntegrityViolationException e) {
            throw new BusinessRuleException("An administrator already exists");
        }

        return authService.generateTokens(admin);
    }
}
