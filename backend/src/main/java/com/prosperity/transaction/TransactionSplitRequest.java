package com.prosperity.transaction;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.util.UUID;

/** DTO for a transaction split (single category + amount entry). */
public record TransactionSplitRequest(
    @NotNull UUID categoryId, @NotNull BigDecimal amount, @Size(max = 500) String description) {}
