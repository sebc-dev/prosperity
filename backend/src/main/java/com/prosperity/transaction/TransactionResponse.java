package com.prosperity.transaction;

import com.prosperity.shared.TransactionSource;
import com.prosperity.shared.TransactionState;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

/** DTO for transaction responses including category and split information. */
public record TransactionResponse(
    UUID id,
    UUID accountId,
    BigDecimal amount,
    String description,
    UUID categoryId,
    String categoryName,
    LocalDate transactionDate,
    TransactionSource source,
    TransactionState state,
    boolean pointed,
    Instant createdAt,
    List<TransactionSplitResponse> splits) {}
