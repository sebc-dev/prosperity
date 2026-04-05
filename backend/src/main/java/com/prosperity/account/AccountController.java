package com.prosperity.account;

import com.prosperity.auth.UserNotFoundException;
import jakarta.validation.Valid;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * REST controller for account CRUD and access management.
 *
 * <p>HTTP concerns only: status codes, request/response mapping, security principal resolution.
 * Business logic is delegated to {@link AccountService}.
 *
 * <p>Per D-02: 403 is returned when an account exists but the user has no access (never 404) to
 * avoid leaking account existence.
 */
@RestController
@RequestMapping("/api/accounts")
public class AccountController {

  private final AccountService accountService;

  public AccountController(AccountService accountService) {
    this.accountService = accountService;
  }

  // ---------------------------------------------------------------------------
  // Account CRUD
  // ---------------------------------------------------------------------------

  /** Creates a new account. The creator is automatically granted ADMIN access (D-04). */
  @PostMapping
  public ResponseEntity<AccountResponse> create(
      @Valid @RequestBody CreateAccountRequest request,
      @AuthenticationPrincipal UserDetails userDetails) {
    var response = accountService.createAccount(request, userDetails.getUsername());
    return ResponseEntity.status(HttpStatus.CREATED).body(response);
  }

  /**
   * Lists accounts accessible by the authenticated user.
   * D-07: archived accounts are excluded by default; pass {@code includeArchived=true} to include.
   */
  @GetMapping
  public ResponseEntity<List<AccountResponse>> list(
      @RequestParam(defaultValue = "false") boolean includeArchived,
      @AuthenticationPrincipal UserDetails userDetails) {
    var accounts = accountService.getAccounts(includeArchived, userDetails.getUsername());
    return ResponseEntity.ok(accounts);
  }

  /** Returns a single account. D-02: returns 403 if account exists but user has no access. */
  @GetMapping("/{id}")
  public ResponseEntity<AccountResponse> getById(
      @PathVariable UUID id,
      @AuthenticationPrincipal UserDetails userDetails) {
    var response = accountService.getAccount(id, userDetails.getUsername());
    return ResponseEntity.ok(response);
  }

  /**
   * Updates mutable account fields (partial PATCH semantics, D-08).
   * Requires at least WRITE access.
   */
  @PatchMapping("/{id}")
  public ResponseEntity<AccountResponse> update(
      @PathVariable UUID id,
      @Valid @RequestBody UpdateAccountRequest request,
      @AuthenticationPrincipal UserDetails userDetails) {
    var response = accountService.updateAccount(id, request, userDetails.getUsername());
    return ResponseEntity.ok(response);
  }

  // ---------------------------------------------------------------------------
  // Access management (ADMIN-only)
  // ---------------------------------------------------------------------------

  /** Lists all access entries for an account. Requires ADMIN access (ACCS-03). */
  @GetMapping("/{id}/access")
  public ResponseEntity<List<AccountAccessResponse>> listAccess(
      @PathVariable UUID id,
      @AuthenticationPrincipal UserDetails userDetails) {
    var entries = accountService.getAccessEntries(id, userDetails.getUsername());
    return ResponseEntity.ok(entries);
  }

  /** Grants or updates a user's access level on an account. Requires ADMIN access (ACCS-03). */
  @PostMapping("/{id}/access")
  public ResponseEntity<AccountAccessResponse> setAccess(
      @PathVariable UUID id,
      @Valid @RequestBody SetAccessRequest request,
      @AuthenticationPrincipal UserDetails userDetails) {
    var response = accountService.setAccess(id, request, userDetails.getUsername());
    return ResponseEntity.ok(response);
  }

  /** Revokes a user's access to an account. Requires ADMIN access (ACCS-03). */
  @DeleteMapping("/{id}/access/{accessId}")
  public ResponseEntity<Void> removeAccess(
      @PathVariable UUID id,
      @PathVariable UUID accessId,
      @AuthenticationPrincipal UserDetails userDetails) {
    accountService.removeAccess(id, accessId, userDetails.getUsername());
    return ResponseEntity.noContent().build();
  }

  // ---------------------------------------------------------------------------
  // Exception handlers
  // ---------------------------------------------------------------------------

  @ExceptionHandler(AccountNotFoundException.class)
  public ResponseEntity<Map<String, String>> handleNotFound(AccountNotFoundException e) {
    return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", e.getMessage()));
  }

  @ExceptionHandler(AccountAccessDeniedException.class)
  public ResponseEntity<Map<String, String>> handleAccessDenied(AccountAccessDeniedException e) {
    return ResponseEntity.status(HttpStatus.FORBIDDEN).body(Map.of("error", e.getMessage()));
  }

  @ExceptionHandler(IllegalStateException.class)
  public ResponseEntity<Map<String, String>> handleConflict(IllegalStateException e) {
    return ResponseEntity.status(HttpStatus.CONFLICT).body(Map.of("error", e.getMessage()));
  }

  @ExceptionHandler(UserNotFoundException.class)
  public ResponseEntity<Map<String, String>> handleUserNotFound(UserNotFoundException e) {
    return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", e.getMessage()));
  }

  @ExceptionHandler(AccessEntryNotFoundException.class)
  public ResponseEntity<Map<String, String>> handleAccessEntryNotFound(
      AccessEntryNotFoundException e) {
    return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", e.getMessage()));
  }

  @ExceptionHandler(IllegalArgumentException.class)
  public ResponseEntity<Map<String, String>> handleBadRequest(IllegalArgumentException e) {
    return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(Map.of("error", e.getMessage()));
  }
}
