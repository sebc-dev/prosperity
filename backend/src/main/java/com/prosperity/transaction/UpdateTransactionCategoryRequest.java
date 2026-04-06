package com.prosperity.transaction;

import java.util.UUID;

/** DTO for PATCH /api/transactions/{id}/category. Nullable categoryId clears the category. */
public record UpdateTransactionCategoryRequest(UUID categoryId) {}
