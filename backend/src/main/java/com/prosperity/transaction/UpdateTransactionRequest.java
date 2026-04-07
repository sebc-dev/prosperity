package com.prosperity.transaction;

import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.UUID;

/** DTO for updating a transaction (partial update via PATCH). All fields nullable. */
public record UpdateTransactionRequest(
    BigDecimal amount,
    LocalDate transactionDate,
    @Size(max = 500) String description,
    UUID categoryId,
    Boolean clearCategory) {}
