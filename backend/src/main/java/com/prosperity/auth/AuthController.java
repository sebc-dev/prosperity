package com.prosperity.auth;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * REST controller for authentication endpoints.
 *
 * <p>Provides setup wizard (admin creation), login with explicit session save (Spring Security 7
 * BFF cookie flow), current user retrieval, and first-launch status check.
 */
@RestController
@RequestMapping("/api/auth")
public class AuthController {

  private final AuthService authService;
  private final AuthenticationManager authenticationManager;
  private final UserRepository userRepository;
  private final SecurityContextRepository securityContextRepository =
      new HttpSessionSecurityContextRepository();

  public AuthController(
      AuthService authService,
      AuthenticationManager authenticationManager,
      UserRepository userRepository) {
    this.authService = authService;
    this.authenticationManager = authenticationManager;
    this.userRepository = userRepository;
  }

  /** Creates the admin user. Returns 201 on success, 409 if setup already complete. */
  @PostMapping("/setup")
  public ResponseEntity<UserResponse> setup(@Valid @RequestBody SetupRequest request) {
    try {
      var response = authService.createAdmin(request);
      return ResponseEntity.status(HttpStatus.CREATED).body(response);
    } catch (SetupAlreadyCompleteException e) {
      return ResponseEntity.status(HttpStatus.CONFLICT).build();
    }
  }

  /**
   * Authenticates a user and creates an HTTP session.
   *
   * <p>Explicitly saves the SecurityContext to the session as required by Spring Security 7 (no
   * auto-save).
   */
  @PostMapping("/login")
  public ResponseEntity<?> login(
      @Valid @RequestBody LoginRequest request,
      HttpServletRequest httpRequest,
      HttpServletResponse httpResponse) {
    try {
      var token =
          UsernamePasswordAuthenticationToken.unauthenticated(request.email(), request.password());
      var authentication = authenticationManager.authenticate(token);

      var context = SecurityContextHolder.createEmptyContext();
      context.setAuthentication(authentication);
      SecurityContextHolder.setContext(context);
      securityContextRepository.saveContext(context, httpRequest, httpResponse);

      var userDetails = (UserDetails) authentication.getPrincipal();
      var user = userRepository.findByEmail(userDetails.getUsername()).orElseThrow();
      return ResponseEntity.ok(authService.toUserResponse(user));
    } catch (BadCredentialsException e) {
      return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
          .body(Map.of("error", "Identifiants invalides"));
    }
  }

  /** Returns the currently authenticated user, or 401 if not authenticated. */
  @GetMapping("/me")
  public ResponseEntity<UserResponse> me(@AuthenticationPrincipal UserDetails userDetails) {
    if (userDetails == null) {
      return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
    }
    var user = userRepository.findByEmail(userDetails.getUsername()).orElseThrow();
    return ResponseEntity.ok(authService.toUserResponse(user));
  }

  /** Returns whether the initial setup has been completed (at least one user exists). */
  @GetMapping("/status")
  public ResponseEntity<Map<String, Boolean>> status() {
    return ResponseEntity.ok(Map.of("setupComplete", authService.isSetupComplete()));
  }
}
