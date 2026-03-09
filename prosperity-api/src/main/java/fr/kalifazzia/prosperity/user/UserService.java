package fr.kalifazzia.prosperity.user;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.uuid.Generators;
import fr.kalifazzia.prosperity.user.dto.ChangePasswordRequest;
import fr.kalifazzia.prosperity.user.dto.CreateUserRequest;
import fr.kalifazzia.prosperity.user.dto.UpdatePreferencesRequest;
import fr.kalifazzia.prosperity.user.dto.UpdateProfileRequest;
import fr.kalifazzia.prosperity.user.dto.UserDto;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
public class UserService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final ObjectMapper objectMapper;

    public UserService(UserRepository userRepository, PasswordEncoder passwordEncoder, ObjectMapper objectMapper) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.objectMapper = objectMapper;
    }

    @Transactional(readOnly = true)
    public UserDto getCurrentUser(UUID userId) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("User not found"));
        return toDto(user);
    }

    @Transactional
    public UserDto updateProfile(UUID userId, UpdateProfileRequest request) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("User not found"));
        user.setDisplayName(request.displayName());
        userRepository.save(user);
        return toDto(user);
    }

    @Transactional
    public UserDto updatePreferences(UUID userId, UpdatePreferencesRequest request) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("User not found"));

        try {
            Map<String, Object> prefs = Map.of(
                    "theme", request.theme() != null ? request.theme() : "system",
                    "locale", request.locale() != null ? request.locale() : "en",
                    "defaultCurrency", request.defaultCurrency() != null ? request.defaultCurrency() : "EUR",
                    "favoriteCategories", request.favoriteCategories() != null ? request.favoriteCategories() : List.of()
            );
            user.setPreferences(objectMapper.writeValueAsString(prefs));
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("Failed to serialize preferences", e);
        }

        userRepository.save(user);
        return toDto(user);
    }

    @Transactional
    public void changePassword(UUID userId, ChangePasswordRequest request) {
        if (!request.newPassword().equals(request.confirmPassword())) {
            throw new IllegalArgumentException("New password and confirmation do not match");
        }

        User user = userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("User not found"));

        if (!passwordEncoder.matches(request.oldPassword(), user.getPasswordHash())) {
            throw new IllegalArgumentException("Old password is incorrect");
        }

        user.setPasswordHash(passwordEncoder.encode(request.newPassword()));
        user.setForcePasswordChange(false);
        userRepository.save(user);
    }

    @PreAuthorize("hasRole('ADMIN')")
    @Transactional
    public UserDto createUser(CreateUserRequest request) {
        if (userRepository.findByEmail(request.email()).isPresent()) {
            throw new IllegalArgumentException("Email already in use");
        }

        User user = new User(
                Generators.timeBasedEpochGenerator().generate(),
                request.email(),
                passwordEncoder.encode(request.password()),
                request.displayName(),
                SystemRole.STANDARD
        );
        user.setForcePasswordChange(true);
        userRepository.save(user);
        return toDto(user);
    }

    @PreAuthorize("hasRole('ADMIN')")
    @Transactional(readOnly = true)
    public List<UserDto> listUsers() {
        return userRepository.findAll().stream()
                .map(this::toDto)
                .collect(Collectors.toList());
    }

    private UserDto toDto(User user) {
        Object preferences;
        try {
            preferences = objectMapper.readValue(user.getPreferences(), Object.class);
        } catch (JsonProcessingException e) {
            preferences = Map.of();
        }

        return new UserDto(
                user.getId(),
                user.getEmail(),
                user.getDisplayName(),
                user.getSystemRole().name(),
                preferences,
                user.isForcePasswordChange()
        );
    }
}
