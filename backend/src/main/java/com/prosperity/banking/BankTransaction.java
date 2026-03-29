package com.prosperity.banking;

import com.prosperity.shared.Money;
import java.time.LocalDate;

/** Record representing a transaction fetched from a bank connector. */
public record BankTransaction(
    String transactionId,
    Money amount,
    String description,
    LocalDate date,
    String categoryId,
    boolean pending) {}
