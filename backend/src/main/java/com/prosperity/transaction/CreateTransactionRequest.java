package com.prosperity.transaction;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.UUID;

/** DTO for creating a new transaction manually. */
public record CreateTransactionRequest(
    @NotNull BigDecimal amount,
    @NotNull LocalDate transactionDate,
    @Size(max = 500) String description,
    UUID categoryId) {}
