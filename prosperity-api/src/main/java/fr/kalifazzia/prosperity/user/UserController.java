package fr.kalifazzia.prosperity.user;

import fr.kalifazzia.prosperity.shared.security.SecurityUtils;
import fr.kalifazzia.prosperity.user.dto.ChangePasswordRequest;
import fr.kalifazzia.prosperity.user.dto.CreateUserRequest;
import fr.kalifazzia.prosperity.user.dto.UpdatePreferencesRequest;
import fr.kalifazzia.prosperity.user.dto.UpdateProfileRequest;
import fr.kalifazzia.prosperity.user.dto.UserDto;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/users")
public class UserController {

    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    @GetMapping("/me")
    public ResponseEntity<UserDto> getCurrentUser() {
        UUID userId = SecurityUtils.extractUserId();
        return ResponseEntity.ok(userService.getCurrentUser(userId));
    }

    @PatchMapping("/me/profile")
    public ResponseEntity<UserDto> updateProfile(
            @Valid @RequestBody UpdateProfileRequest profileRequest) {
        UUID userId = SecurityUtils.extractUserId();
        return ResponseEntity.ok(userService.updateProfile(userId, profileRequest));
    }

    @PatchMapping("/me/preferences")
    public ResponseEntity<UserDto> updatePreferences(
            @Valid @RequestBody UpdatePreferencesRequest preferencesRequest) {
        UUID userId = SecurityUtils.extractUserId();
        return ResponseEntity.ok(userService.updatePreferences(userId, preferencesRequest));
    }

    @PostMapping("/me/password")
    public ResponseEntity<Void> changePassword(
            @Valid @RequestBody ChangePasswordRequest passwordRequest) {
        UUID userId = SecurityUtils.extractUserId();
        userService.changePassword(userId, passwordRequest);
        return ResponseEntity.ok().build();
    }

    @GetMapping
    public ResponseEntity<List<UserDto>> listUsers() {
        return ResponseEntity.ok(userService.listUsers());
    }

    @PostMapping
    public ResponseEntity<UserDto> createUser(@Valid @RequestBody CreateUserRequest createRequest) {
        UserDto user = userService.createUser(createRequest);
        return ResponseEntity.status(HttpStatus.CREATED).body(user);
    }

}
