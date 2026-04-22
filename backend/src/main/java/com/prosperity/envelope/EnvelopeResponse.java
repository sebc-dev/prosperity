package com.prosperity.envelope;

import com.prosperity.shared.EnvelopeScope;
import com.prosperity.shared.RolloverPolicy;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/**
 * Envelope read DTO. All monetary fields are non-negative BigDecimals except {@code available},
 * which is signed (negative = overspent). The frontend uses {@code status} + {@code ratio} directly
 * (D-13 thresholds owned server-side).
 *
 * @param defaultBudget envelope's default monthly budget (Envelope.budget)
 * @param effectiveBudget budget actually applied this month (override if present, else default)
 * @param consumed non-negative amount spent in linked categories this month
 * @param available {@code effectiveBudget + carryOver - consumed} (signed; negative = overspent)
 * @param ratio {@code consumed / (effectiveBudget + carryOver)} (D-13 literal denominator =
 *     allocatable total for the period; &gt;1.0 means overspent; 0.0 when allocatable &le; 0)
 * @param hasMonthlyOverride true when an EnvelopeAllocation row exists for this month
 */
public record EnvelopeResponse(
    UUID id,
    UUID bankAccountId,
    String bankAccountName,
    String name,
    EnvelopeScope scope,
    UUID ownerId,
    List<EnvelopeCategoryRef> categories,
    RolloverPolicy rolloverPolicy,
    BigDecimal defaultBudget,
    BigDecimal effectiveBudget,
    BigDecimal consumed,
    BigDecimal available,
    BigDecimal ratio,
    EnvelopeStatus status,
    boolean hasMonthlyOverride,
    boolean archived,
    Instant createdAt) {

  /** Lightweight inner record for category id+name pairs (avoids returning full Category DTO). */
  public record EnvelopeCategoryRef(UUID id, String name) {}
}
