package com.prosperity.envelope;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.YearMonth;
import java.util.UUID;

/** Read DTO for a monthly budget override (D-08, D-10). */
public record EnvelopeAllocationResponse(
    UUID id, UUID envelopeId, YearMonth month, BigDecimal allocatedAmount, Instant createdAt) {}
