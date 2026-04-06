package com.prosperity.transaction;

import com.prosperity.category.CategoryNotFoundException;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * REST controller for transaction endpoints. Phase 4: only PATCH category. Full CRUD in Phase 5.
 */
@RestController
@RequestMapping("/api/transactions")
public class TransactionController {

  private final TransactionService transactionService;

  public TransactionController(TransactionService transactionService) {
    this.transactionService = transactionService;
  }

  /** Updates the category of a transaction. Pass null categoryId to clear the category. */
  @PatchMapping("/{id}/category")
  public ResponseEntity<Void> updateCategory(
      @PathVariable UUID id, @RequestBody UpdateTransactionCategoryRequest request) {
    transactionService.updateCategory(id, request.categoryId());
    return ResponseEntity.noContent().build();
  }

  @ExceptionHandler(TransactionNotFoundException.class)
  public ResponseEntity<Map<String, String>> handleNotFound(TransactionNotFoundException e) {
    return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", e.getMessage()));
  }

  @ExceptionHandler(CategoryNotFoundException.class)
  public ResponseEntity<Map<String, String>> handleCategoryNotFound(CategoryNotFoundException e) {
    return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", e.getMessage()));
  }
}
