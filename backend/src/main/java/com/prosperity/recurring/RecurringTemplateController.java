package com.prosperity.recurring;

import com.prosperity.account.AccountAccessDeniedException;
import com.prosperity.account.AccountNotFoundException;
import com.prosperity.category.CategoryNotFoundException;
import com.prosperity.transaction.TransactionResponse;
import jakarta.validation.Valid;
import java.security.Principal;
import java.util.List;
import java.util.Map;
import java.util.UUID;
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
import org.springframework.web.bind.annotation.RestController;

/**
 * REST controller for recurring template endpoints, scoped under an account.
 *
 * <p>HTTP concerns only: status codes, request/response mapping. Business logic is delegated to
 * {@link RecurringTemplateService}.
 */
@RestController
@RequestMapping("/api/accounts/{accountId}/recurring-templates")
public class RecurringTemplateController {

  private final RecurringTemplateService recurringTemplateService;

  public RecurringTemplateController(RecurringTemplateService recurringTemplateService) {
    this.recurringTemplateService = recurringTemplateService;
  }

  /** Creates a new recurring template on the given account. Returns 201 Created. */
  @PostMapping
  public ResponseEntity<RecurringTemplateResponse> createTemplate(
      @PathVariable UUID accountId,
      @Valid @RequestBody CreateRecurringTemplateRequest request,
      Principal principal) {
    RecurringTemplateResponse response =
        recurringTemplateService.createTemplate(accountId, request, principal.getName());
    return ResponseEntity.status(HttpStatus.CREATED).body(response);
  }

  /** Returns recurring templates for the account. Inactive templates excluded by default. */
  @GetMapping
  public List<RecurringTemplateResponse> getTemplates(
      @PathVariable UUID accountId,
      @RequestParam(defaultValue = "false") boolean includeInactive,
      Principal principal) {
    return recurringTemplateService.getTemplates(accountId, includeInactive, principal.getName());
  }

  /** Updates a recurring template's fields (partial update — all fields nullable). */
  @PutMapping("/{templateId}")
  public RecurringTemplateResponse updateTemplate(
      @PathVariable UUID accountId,
      @PathVariable UUID templateId,
      @Valid @RequestBody UpdateRecurringTemplateRequest request,
      Principal principal) {
    return recurringTemplateService.updateTemplate(templateId, request, principal.getName());
  }

  /** Deletes a recurring template. Returns 204 No Content. */
  @DeleteMapping("/{templateId}")
  public ResponseEntity<Void> deleteTemplate(
      @PathVariable UUID accountId,
      @PathVariable UUID templateId,
      Principal principal) {
    recurringTemplateService.deleteTemplate(templateId, principal.getName());
    return ResponseEntity.noContent().build();
  }

  /**
   * Generates a real transaction from the template, advancing the template's nextDueDate. Returns
   * 201 Created with the generated TransactionResponse.
   */
  @PostMapping("/{templateId}/generate")
  public ResponseEntity<TransactionResponse> generateTransaction(
      @PathVariable UUID accountId,
      @PathVariable UUID templateId,
      Principal principal) {
    TransactionResponse response =
        recurringTemplateService.generateTransaction(templateId, principal.getName());
    return ResponseEntity.status(HttpStatus.CREATED).body(response);
  }

  // ---------------------------------------------------------------------------
  // Exception handlers
  // ---------------------------------------------------------------------------

  @ExceptionHandler(RecurringTemplateNotFoundException.class)
  public ResponseEntity<Map<String, String>> handleNotFound(RecurringTemplateNotFoundException e) {
    return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", e.getMessage()));
  }

  @ExceptionHandler(AccountAccessDeniedException.class)
  public ResponseEntity<Map<String, String>> handleAccessDenied(AccountAccessDeniedException e) {
    return ResponseEntity.status(HttpStatus.FORBIDDEN).body(Map.of("error", e.getMessage()));
  }

  @ExceptionHandler(AccountNotFoundException.class)
  public ResponseEntity<Map<String, String>> handleAccountNotFound(AccountNotFoundException e) {
    return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", e.getMessage()));
  }

  @ExceptionHandler(CategoryNotFoundException.class)
  public ResponseEntity<Map<String, String>> handleCategoryNotFound(CategoryNotFoundException e) {
    return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", e.getMessage()));
  }

  @ExceptionHandler(IllegalStateException.class)
  public ResponseEntity<Map<String, String>> handleIllegalState(IllegalStateException e) {
    return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(Map.of("error", e.getMessage()));
  }
}
