package com.prosperity.recurring;

import com.prosperity.shared.RecurrenceFrequency;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.UUID;

/** DTO for updating a recurring template (partial update via PATCH). All fields nullable. */
public record UpdateRecurringTemplateRequest(
    BigDecimal amount,
    @Size(max = 500) String description,
    UUID categoryId,
    Boolean clearCategory,
    RecurrenceFrequency frequency,
    Integer dayOfMonth,
    LocalDate nextDueDate,
    Boolean active) {}
