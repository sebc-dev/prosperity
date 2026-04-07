package com.prosperity.transaction;

import java.math.BigDecimal;
import java.util.UUID;

/** DTO for transaction split responses. */
public record TransactionSplitResponse(
    UUID id, UUID categoryId, String categoryName, BigDecimal amount, String description) {}
