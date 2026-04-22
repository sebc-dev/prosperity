package com.prosperity.envelope;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.time.YearMonth;

/** Create or update a monthly budget override for an envelope (D-08, D-10). */
public record EnvelopeAllocationRequest(
    @NotNull YearMonth month,
    @NotNull @DecimalMin(value = "0.00", inclusive = true) BigDecimal allocatedAmount) {}
