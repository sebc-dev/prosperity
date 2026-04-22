package com.prosperity.envelope;

import com.prosperity.account.AccountAccessDeniedException;
import com.prosperity.account.AccountNotFoundException;
import com.prosperity.category.CategoryNotFoundException;
import jakarta.validation.Valid;
import java.security.Principal;
import java.time.YearMonth;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * REST controller for envelope endpoints. Endpoints span:
 *
 * <ul>
 *   <li>{@code /api/accounts/{accountId}/envelopes} — list + create scoped to an account
 *   <li>{@code /api/envelopes} — list across all accounts the user has access to
 *   <li>{@code /api/envelopes/{id}} — get/update/delete + history
 * </ul>
 *
 * <p>403 vs 404 follows Phase 3/5 convention: existsById(account) -> 404 if missing, then 403 if
 * caller has no access.
 */
@RestController
@RequestMapping("/api")
public class EnvelopeController {

  private final EnvelopeService envelopeService;

  public EnvelopeController(EnvelopeService envelopeService) {
    this.envelopeService = envelopeService;
  }

  // ------------------ Account-scoped --------------------------------

  @PostMapping("/accounts/{accountId}/envelopes")
  public ResponseEntity<EnvelopeResponse> createEnvelope(
      @PathVariable UUID accountId,
      @Valid @RequestBody CreateEnvelopeRequest request,
      Principal principal) {
    EnvelopeResponse response =
        envelopeService.createEnvelope(accountId, request, principal.getName());
    return ResponseEntity.status(HttpStatus.CREATED).body(response);
  }

  @GetMapping("/accounts/{accountId}/envelopes")
  public List<EnvelopeResponse> listEnvelopesForAccount(
      @PathVariable UUID accountId,
      @RequestParam(name = "includeArchived", defaultValue = "false") boolean includeArchived,
      Principal principal) {
    return envelopeService.listEnvelopesForAccount(
        accountId, includeArchived, principal.getName());
  }

  // ------------------ Cross-account list ---------------------------

  @GetMapping("/envelopes")
  public List<EnvelopeResponse> listEnvelopes(
      @RequestParam(name = "accountId", required = false) UUID accountId,
      @RequestParam(name = "includeArchived", defaultValue = "false") boolean includeArchived,
      Principal principal) {
    if (accountId != null) {
      return envelopeService.listEnvelopesForAccount(
          accountId, includeArchived, principal.getName());
    }
    return envelopeService.listAllEnvelopes(includeArchived, principal.getName());
  }

  // ------------------ Envelope-scoped ------------------------------

  @GetMapping("/envelopes/{id}")
  public EnvelopeResponse getEnvelope(@PathVariable UUID id, Principal principal) {
    return envelopeService.getEnvelope(id, principal.getName());
  }

  @PutMapping("/envelopes/{id}")
  public EnvelopeResponse updateEnvelope(
      @PathVariable UUID id,
      @Valid @RequestBody UpdateEnvelopeRequest request,
      Principal principal) {
    return envelopeService.updateEnvelope(id, request, principal.getName());
  }

  @DeleteMapping("/envelopes/{id}")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void deleteEnvelope(@PathVariable UUID id, Principal principal) {
    envelopeService.deleteEnvelope(id, principal.getName());
  }

  /**
   * Returns the 12-month consumption history ending at {@code month} (defaults to current month).
   * The {@code month} request param is parsed as {@code yyyy-MM} (ISO 8601 month).
   */
  @GetMapping("/envelopes/{id}/history")
  public List<EnvelopeHistoryEntry> getHistory(
      @PathVariable UUID id,
      @RequestParam(name = "month", required = false)
          @DateTimeFormat(pattern = "yyyy-MM")
          YearMonth month,
      Principal principal) {
    YearMonth target = month != null ? month : YearMonth.now();
    return envelopeService.getEnvelopeHistory(id, target, principal.getName());
  }

  // ------------------ Exception handlers ----------------------------

  @ExceptionHandler(EnvelopeNotFoundException.class)
  @ResponseStatus(HttpStatus.NOT_FOUND)
  Map<String, String> handleEnvelopeNotFound(EnvelopeNotFoundException e) {
    return Map.of("error", e.getMessage());
  }

  @ExceptionHandler(AccountNotFoundException.class)
  @ResponseStatus(HttpStatus.NOT_FOUND)
  Map<String, String> handleAccountNotFound(AccountNotFoundException e) {
    return Map.of("error", e.getMessage());
  }

  @ExceptionHandler(CategoryNotFoundException.class)
  @ResponseStatus(HttpStatus.NOT_FOUND)
  Map<String, String> handleCategoryNotFound(CategoryNotFoundException e) {
    return Map.of("error", e.getMessage());
  }

  @ExceptionHandler(AccountAccessDeniedException.class)
  @ResponseStatus(HttpStatus.FORBIDDEN)
  Map<String, String> handleAccessDenied(AccountAccessDeniedException e) {
    return Map.of("error", e.getMessage());
  }

  @ExceptionHandler(DuplicateEnvelopeCategoryException.class)
  @ResponseStatus(HttpStatus.CONFLICT)
  Map<String, String> handleDuplicateCategory(DuplicateEnvelopeCategoryException e) {
    return Map.of("error", e.getMessage());
  }
}
