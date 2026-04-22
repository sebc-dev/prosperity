package com.prosperity.envelope;

import com.prosperity.shared.RolloverPolicy;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.util.Set;
import java.util.UUID;

/**
 * Partial-PATCH update for an envelope. All fields are nullable; service applies only non-null
 * fields (Phase 3 D-08 convention). When {@code categoryIds} is non-null the service replaces the
 * entire set (mutating in place per Pitfall 3).
 */
public record UpdateEnvelopeRequest(
    @Size(max = 100) String name,
    Set<UUID> categoryIds,
    @DecimalMin(value = "0.00", inclusive = true) BigDecimal budget,
    RolloverPolicy rolloverPolicy) {}
