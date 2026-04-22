package com.prosperity.envelope;

import com.prosperity.shared.RolloverPolicy;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.util.Set;
import java.util.UUID;

/**
 * Create-envelope request body. Note: NO {@code scope} field — scope is DERIVED server-side from
 * the target account's accountType (D-07, Pitfall 4). Account id is taken from the URL path.
 */
public record CreateEnvelopeRequest(
    @NotBlank @Size(max = 100) String name,
    @NotEmpty Set<@NotNull UUID> categoryIds,
    @NotNull @DecimalMin(value = "0.00", inclusive = true) BigDecimal budget,
    @NotNull RolloverPolicy rolloverPolicy) {}
