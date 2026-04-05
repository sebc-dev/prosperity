package com.prosperity.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.crypto.password.PasswordEncoder;

/** Unit tests for AuthService business logic with mocked dependencies. */
@ExtendWith(MockitoExtension.class)
class AuthServiceTest {

  @Mock private UserRepository userRepository;
  @Mock private PasswordEncoder passwordEncoder;
  @InjectMocks private AuthService authService;

  @Test
  void is_setup_complete_returns_false_when_no_users() {
    when(userRepository.count()).thenReturn(0L);

    var result = authService.isSetupComplete();

    assertThat(result).isFalse();
  }

  @Test
  void is_setup_complete_returns_true_when_users_exist() {
    when(userRepository.count()).thenReturn(1L);

    var result = authService.isSetupComplete();

    assertThat(result).isTrue();
  }

  @Test
  void create_admin_hashes_password_and_sets_admin_role() {
    when(userRepository.count()).thenReturn(0L);
    when(passwordEncoder.encode("SecurePass123!")).thenReturn("{bcrypt}hashedpassword");
    when(userRepository.save(any(User.class))).thenAnswer(invocation -> invocation.getArgument(0));

    var result =
        authService.createAdmin(new SetupRequest("admin@test.com", "SecurePass123!", "Admin"));

    assertThat(result.email()).isEqualTo("admin@test.com");
    assertThat(result.displayName()).isEqualTo("Admin");
    assertThat(result.role()).isEqualTo("ADMIN");

    verify(passwordEncoder).encode("SecurePass123!");

    var userCaptor = ArgumentCaptor.forClass(User.class);
    verify(userRepository).save(userCaptor.capture());
    var savedUser = userCaptor.getValue();
    assertThat(savedUser.getPasswordHash()).isEqualTo("{bcrypt}hashedpassword");
    assertThat(savedUser.getRole()).isEqualTo(Role.ADMIN);
  }

  @Test
  void create_admin_throws_when_setup_already_complete() {
    when(userRepository.count()).thenReturn(1L);

    assertThatThrownBy(
            () ->
                authService.createAdmin(
                    new SetupRequest("admin@test.com", "SecurePass123!", "Admin")))
        .isInstanceOf(SetupAlreadyCompleteException.class);
  }

  @Test
  void find_user_response_by_email_returns_dto_when_user_exists() {
    // Arrange
    var user = new User("user@test.com", "{bcrypt}hash", "Display");
    user.setRole(Role.USER);
    when(userRepository.findByEmail("user@test.com")).thenReturn(Optional.of(user));

    // Act
    var result = authService.findUserResponseByEmail("user@test.com");

    // Assert
    assertThat(result.email()).isEqualTo("user@test.com");
    assertThat(result.displayName()).isEqualTo("Display");
  }

  @Test
  void find_user_response_by_email_throws_when_user_not_found() {
    // Arrange
    when(userRepository.findByEmail("missing@test.com")).thenReturn(Optional.empty());

    // Act & Assert
    assertThatThrownBy(() -> authService.findUserResponseByEmail("missing@test.com"))
        .isInstanceOf(UserNotFoundException.class);
  }

  @Test
  void list_all_users_returns_empty_list_when_no_users() {
    // Arrange
    when(userRepository.findAll()).thenReturn(List.of());

    // Act
    var result = authService.listAllUsers();

    // Assert
    assertThat(result).isEmpty();
  }

  @Test
  void list_all_users_maps_all_users_to_responses() {
    // Arrange
    var user = new User("alice@test.com", "{bcrypt}hash", "Alice");
    user.setRole(Role.USER);
    when(userRepository.findAll()).thenReturn(List.of(user));

    // Act
    var result = authService.listAllUsers();

    // Assert
    assertThat(result).hasSize(1);
    assertThat(result.get(0).email()).isEqualTo("alice@test.com");
    assertThat(result.get(0).displayName()).isEqualTo("Alice");
  }
}
