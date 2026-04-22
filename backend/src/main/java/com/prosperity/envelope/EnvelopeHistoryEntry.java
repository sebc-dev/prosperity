package com.prosperity.envelope;

import java.math.BigDecimal;
import java.time.YearMonth;

/**
 * One month's row in the 12-month consumption history (ENVL-06). {@code available} reflects
 * rollover semantics if applicable; {@code ratio} and {@code status} mirror EnvelopeResponse
 * thresholds (denominator = allocatable = effectiveBudget + carryOver, D-13).
 */
public record EnvelopeHistoryEntry(
    YearMonth month,
    BigDecimal effectiveBudget,
    BigDecimal consumed,
    BigDecimal available,
    BigDecimal ratio,
    EnvelopeStatus status) {}
