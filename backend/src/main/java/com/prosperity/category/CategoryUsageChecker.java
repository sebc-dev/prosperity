package com.prosperity.category;

import java.util.UUID;

/**
 * Port allowing CategoryService to check if a category is referenced by external data, without
 * creating a direct dependency from the category package to other feature packages.
 */
public interface CategoryUsageChecker {

  /** Returns true if the category is referenced by any data that would prevent deletion. */
  boolean isCategoryUsed(UUID categoryId);
}
