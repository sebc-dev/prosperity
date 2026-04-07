package com.prosperity.recurring;

import com.prosperity.shared.RecurrenceFrequency;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

/** DTO for recurring template responses. */
public record RecurringTemplateResponse(
    UUID id,
    UUID accountId,
    BigDecimal amount,
    String description,
    UUID categoryId,
    String categoryName,
    RecurrenceFrequency frequency,
    Integer dayOfMonth,
    LocalDate nextDueDate,
    boolean active,
    Instant createdAt) {}
