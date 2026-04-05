package com.prosperity.auth;

import java.util.List;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Business logic for authentication: setup wizard, user lookup, and response mapping. */
@Service
public class AuthService {

  private final UserRepository userRepository;
  private final PasswordEncoder passwordEncoder;

  public AuthService(UserRepository userRepository, PasswordEncoder passwordEncoder) {
    this.userRepository = userRepository;
    this.passwordEncoder = passwordEncoder;
  }

  /** Returns true if at least one user exists (setup already completed). */
  public boolean isSetupComplete() {
    return userRepository.count() > 0;
  }

  /**
   * Creates the admin user during initial setup.
   *
   * @throws SetupAlreadyCompleteException if any user already exists
   */
  @Transactional
  public UserResponse createAdmin(SetupRequest request) {
    if (isSetupComplete()) {
      throw new SetupAlreadyCompleteException();
    }

    var user =
        new User(
            request.email(), passwordEncoder.encode(request.password()), request.displayName());
    user.setRole(Role.ADMIN);
    var saved = userRepository.save(user);

    return new UserResponse(
        saved.getId(), saved.getDisplayName(), saved.getEmail(), saved.getRole().name());
  }

  /** Looks up a user by email and returns the safe DTO. Throws UserNotFoundException if absent. */
  public UserResponse findUserResponseByEmail(String email) {
    return toUserResponse(
        userRepository
            .findByEmail(email)
            .orElseThrow(() -> new UserNotFoundException("User not found: " + email)));
  }

  /** Returns all users as safe DTOs. */
  @Transactional(readOnly = true)
  public List<UserResponse> listAllUsers() {
    return userRepository.findAll().stream().map(this::toUserResponse).toList();
  }

  /** Maps a User entity to a safe UserResponse DTO. */
  private UserResponse toUserResponse(User user) {
    return new UserResponse(
        user.getId(), user.getDisplayName(), user.getEmail(), user.getRole().name());
  }
}
