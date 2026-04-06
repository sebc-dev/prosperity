package com.prosperity.transaction;

import com.prosperity.category.CategoryUsageChecker;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** Checks whether a category is used by any transaction. */
@Component
public class TransactionCategoryUsageChecker implements CategoryUsageChecker {

  private final TransactionRepository transactionRepository;

  public TransactionCategoryUsageChecker(TransactionRepository transactionRepository) {
    this.transactionRepository = transactionRepository;
  }

  @Override
  public boolean isCategoryUsed(UUID categoryId) {
    return transactionRepository.existsByCategoryId(categoryId);
  }
}
