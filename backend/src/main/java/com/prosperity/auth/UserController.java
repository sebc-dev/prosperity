package com.prosperity.auth;

import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * REST controller exposing user list for account access management.
 *
 * <p>Provides {@code GET /api/users} used by the access management dialog user dropdown. Secured by
 * the default {@code anyRequest().authenticated()} in SecurityConfig.
 */
@RestController
@RequestMapping("/api/users")
public class UserController {

  private final AuthService authService;

  public UserController(AuthService authService) {
    this.authService = authService;
  }

  /** Returns all users for account access management. Authenticated users only. */
  @GetMapping
  public ResponseEntity<List<UserResponse>> listUsers() {
    return ResponseEntity.ok(authService.listAllUsers());
  }
}
