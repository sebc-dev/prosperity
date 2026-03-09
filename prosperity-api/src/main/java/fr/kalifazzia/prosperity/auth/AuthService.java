package fr.kalifazzia.prosperity.auth;

import fr.kalifazzia.prosperity.auth.dto.AuthResponse;
import fr.kalifazzia.prosperity.auth.dto.LoginRequest;
import fr.kalifazzia.prosperity.auth.dto.RefreshRequest;
import fr.kalifazzia.prosperity.user.User;
import fr.kalifazzia.prosperity.user.UserRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.UUID;

@Service
public class AuthService {

    private final UserRepository userRepository;
    private final RefreshTokenRepository refreshTokenRepository;
    private final JwtService jwtService;
    private final PasswordEncoder passwordEncoder;
    private final long refreshExpirySeconds;

    public AuthService(
            UserRepository userRepository,
            RefreshTokenRepository refreshTokenRepository,
            JwtService jwtService,
            PasswordEncoder passwordEncoder,
            @Value("${app.jwt.refresh-expiry}") long refreshExpirySeconds
    ) {
        this.userRepository = userRepository;
        this.refreshTokenRepository = refreshTokenRepository;
        this.jwtService = jwtService;
        this.passwordEncoder = passwordEncoder;
        this.refreshExpirySeconds = refreshExpirySeconds;
    }

    @Transactional
    public AuthResponse login(LoginRequest request) {
        User user = userRepository.findByEmail(request.email())
                .orElseThrow(() -> new BadCredentialsException("Invalid credentials"));

        if (!passwordEncoder.matches(request.password(), user.getPasswordHash())) {
            throw new BadCredentialsException("Invalid credentials");
        }

        // Single-session: delete existing refresh tokens
        refreshTokenRepository.deleteByUserId(user.getId());

        return generateTokens(user);
    }

    @Transactional
    public AuthResponse refreshToken(RefreshRequest request) {
        String tokenHash = passwordEncoder.encode(request.refreshToken());

        // Find by iterating stored tokens and matching (bcrypt cannot be looked up by hash)
        RefreshToken storedToken = refreshTokenRepository.findAll().stream()
                .filter(rt -> passwordEncoder.matches(request.refreshToken(), rt.getTokenHash()))
                .findFirst()
                .orElseThrow(() -> new BadCredentialsException("Invalid refresh token"));

        if (storedToken.isExpired()) {
            refreshTokenRepository.delete(storedToken);
            throw new BadCredentialsException("Refresh token expired");
        }

        // Rotation: delete old token
        refreshTokenRepository.delete(storedToken);

        User user = userRepository.findById(storedToken.getUserId())
                .orElseThrow(() -> new BadCredentialsException("User not found"));

        return generateTokens(user);
    }

    public AuthResponse generateTokens(User user) {
        String accessToken = jwtService.generateAccessToken(user);
        String rawRefreshToken = jwtService.generateRefreshToken();
        String refreshHash = passwordEncoder.encode(rawRefreshToken);

        RefreshToken refreshToken = new RefreshToken(
                UUID.randomUUID(),
                user.getId(),
                refreshHash,
                Instant.now().plusSeconds(refreshExpirySeconds)
        );
        refreshTokenRepository.save(refreshToken);

        return new AuthResponse(accessToken, rawRefreshToken);
    }
}
