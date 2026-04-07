package com.prosperity.transaction;

import com.prosperity.account.AccountAccessDeniedException;
import com.prosperity.account.AccountNotFoundException;
import com.prosperity.category.CategoryNotFoundException;
import jakarta.validation.Valid;
import java.math.BigDecimal;
import java.security.Principal;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * REST controller for transaction endpoints.
 *
 * <p>Endpoints span two path patterns:
 * <ul>
 *   <li>{@code /api/accounts/{accountId}/transactions} for listing and creating transactions</li>
 *   <li>{@code /api/transactions/{id}} for single-transaction operations</li>
 * </ul>
 *
 * <p>Per D-02: 403 is returned when account/transaction exists but user has no access.
 */
@RestController
@RequestMapping("/api")
public class TransactionController {

  private final TransactionService transactionService;

  public TransactionController(TransactionService transactionService) {
    this.transactionService = transactionService;
  }

  // ---------------------------------------------------------------------------
  // Account-scoped endpoints
  // ---------------------------------------------------------------------------

  /** Creates a manual transaction on an account. Returns 201 Created (TXNS-01, D-16). */
  @PostMapping("/accounts/{accountId}/transactions")
  public ResponseEntity<TransactionResponse> createTransaction(
      @PathVariable UUID accountId,
      @Valid @RequestBody CreateTransactionRequest request,
      Principal principal) {
    TransactionResponse response =
        transactionService.createTransaction(accountId, request, principal.getName());
    return ResponseEntity.status(HttpStatus.CREATED).body(response);
  }

  /**
   * Lists transactions for an account with optional filters and pagination. Default sort:
   * transactionDate DESC, page size 20 (TXNS-07, TXNS-08, D-14, D-15, D-16).
   */
  @GetMapping("/accounts/{accountId}/transactions")
  public Page<TransactionResponse> getTransactions(
      @PathVariable UUID accountId,
      @RequestParam(required = false) LocalDate dateFrom,
      @RequestParam(required = false) LocalDate dateTo,
      @RequestParam(required = false) BigDecimal amountMin,
      @RequestParam(required = false) BigDecimal amountMax,
      @RequestParam(required = false) UUID categoryId,
      @RequestParam(required = false) String search,
      @RequestParam(defaultValue = "0") int page,
      @RequestParam(defaultValue = "20") int size,
      Principal principal) {
    TransactionFilterParams filters =
        new TransactionFilterParams(dateFrom, dateTo, amountMin, amountMax, categoryId, search);
    Pageable pageable =
        PageRequest.of(page, size, Sort.by(Sort.Direction.DESC, "transaction_date"));
    return transactionService.getTransactions(accountId, filters, pageable, principal.getName());
  }

  // ---------------------------------------------------------------------------
  // Transaction-scoped endpoints
  // ---------------------------------------------------------------------------

  /** Returns a single transaction. Requires READ access to the transaction's account. */
  @GetMapping("/transactions/{id}")
  public TransactionResponse getTransaction(@PathVariable UUID id, Principal principal) {
    return transactionService.getTransaction(id, principal.getName());
  }

  /** Updates a manual transaction's fields. Requires WRITE access (TXNS-02). */
  @PutMapping("/transactions/{id}")
  public TransactionResponse updateTransaction(
      @PathVariable UUID id,
      @Valid @RequestBody UpdateTransactionRequest request,
      Principal principal) {
    return transactionService.updateTransaction(id, request, principal.getName());
  }

  /** Deletes a manual transaction. Requires WRITE access. Returns 204 No Content (TXNS-03). */
  @DeleteMapping("/transactions/{id}")
  public ResponseEntity<Void> deleteTransaction(@PathVariable UUID id, Principal principal) {
    transactionService.deleteTransaction(id, principal.getName());
    return ResponseEntity.noContent().build();
  }

  /** Toggles the pointed status of a transaction. Requires WRITE access (TXNS-05). */
  @PatchMapping("/transactions/{id}/pointed")
  public TransactionResponse togglePointed(@PathVariable UUID id, Principal principal) {
    return transactionService.togglePointed(id, principal.getName());
  }

  /** Updates the category of a transaction. Pass null categoryId to clear the category. */
  @PatchMapping("/transactions/{id}/category")
  public ResponseEntity<Void> updateCategory(
      @PathVariable UUID id,
      @RequestBody UpdateTransactionCategoryRequest request,
      Principal principal) {
    transactionService.updateCategory(id, request.categoryId(), principal.getName());
    return ResponseEntity.noContent().build();
  }

  /**
   * Sets (replaces) splits on a transaction. Split amounts must sum to the transaction amount
   * (D-05). Clears the transaction category (D-06). Requires WRITE access (TXNS-06).
   */
  @PutMapping("/transactions/{id}/splits")
  public TransactionResponse setSplits(
      @PathVariable UUID id,
      @Valid @RequestBody List<TransactionSplitRequest> splits,
      Principal principal) {
    return transactionService.setSplits(id, splits, principal.getName());
  }

  /**
   * Clears all splits from a transaction. Requires WRITE access (TXNS-06).
   */
  @DeleteMapping("/transactions/{id}/splits")
  public TransactionResponse clearSplits(@PathVariable UUID id, Principal principal) {
    return transactionService.clearSplits(id, principal.getName());
  }

  /**
   * Returns all splits for a transaction. Requires READ access (TXNS-06).
   */
  @GetMapping("/transactions/{id}/splits")
  public List<TransactionSplitResponse> getSplits(@PathVariable UUID id, Principal principal) {
    return transactionService.getSplits(id, principal.getName());
  }

  // ---------------------------------------------------------------------------
  // Exception handlers
  // ---------------------------------------------------------------------------

  @ExceptionHandler(TransactionNotFoundException.class)
  public ResponseEntity<Map<String, String>> handleNotFound(TransactionNotFoundException e) {
    return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", e.getMessage()));
  }

  @ExceptionHandler(CategoryNotFoundException.class)
  public ResponseEntity<Map<String, String>> handleCategoryNotFound(CategoryNotFoundException e) {
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

  @ExceptionHandler(IllegalStateException.class)
  public ResponseEntity<Map<String, String>> handleIllegalState(IllegalStateException e) {
    return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(Map.of("error", e.getMessage()));
  }

  @ExceptionHandler(IllegalArgumentException.class)
  public ResponseEntity<Map<String, String>> handleIllegalArgument(IllegalArgumentException e) {
    return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(Map.of("error", e.getMessage()));
  }
}
