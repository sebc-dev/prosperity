package com.prosperity.recurring;

import com.prosperity.shared.RecurrenceFrequency;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.UUID;

/** DTO for creating a new recurring transaction template. */
public record CreateRecurringTemplateRequest(
    @NotNull BigDecimal amount,
    @Size(max = 500) String description,
    UUID categoryId,
    @NotNull RecurrenceFrequency frequency,
    Integer dayOfMonth,
    @NotNull LocalDate nextDueDate) {}
