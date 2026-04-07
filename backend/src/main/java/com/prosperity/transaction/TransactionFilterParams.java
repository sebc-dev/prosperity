package com.prosperity.transaction;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.UUID;

/** Optional filter parameters for listing transactions (all fields nullable). */
public record TransactionFilterParams(
    LocalDate dateFrom,
    LocalDate dateTo,
    BigDecimal amountMin,
    BigDecimal amountMax,
    UUID categoryId,
    String search) {}
