package com.prosperity.transaction;

import com.prosperity.category.Category;
import com.prosperity.category.CategoryNotFoundException;
import com.prosperity.category.CategoryRepository;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Service handling transaction business logic. Phase 4: only category update. */
@Service
public class TransactionService {

  private final TransactionRepository transactionRepository;
  private final CategoryRepository categoryRepository;

  public TransactionService(
      TransactionRepository transactionRepository, CategoryRepository categoryRepository) {
    this.transactionRepository = transactionRepository;
    this.categoryRepository = categoryRepository;
  }

  /**
   * Updates the category of a transaction. Pass null categoryId to clear the category.
   *
   * @param transactionId the transaction to update
   * @param categoryId the new category, or null to clear
   * @throws TransactionNotFoundException if the transaction does not exist
   * @throws CategoryNotFoundException if the categoryId is non-null and does not exist
   */
  @Transactional
  public void updateCategory(UUID transactionId, UUID categoryId) {
    Transaction transaction =
        transactionRepository
            .findById(transactionId)
            .orElseThrow(
                () -> new TransactionNotFoundException("Transaction not found: " + transactionId));

    if (categoryId == null) {
      transaction.setCategory(null);
    } else {
      Category category =
          categoryRepository
              .findById(categoryId)
              .orElseThrow(
                  () -> new CategoryNotFoundException("Category not found: " + categoryId));
      transaction.setCategory(category);
    }
    transactionRepository.save(transaction);
  }
}
