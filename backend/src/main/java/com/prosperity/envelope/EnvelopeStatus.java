package com.prosperity.envelope;

/**
 * Server-computed envelope status (D-13). Derived from the consumed/allocatable ratio. Frontend
 * maps 1:1 to a PrimeNG p-tag severity (GREEN -> success, YELLOW -> warn, RED -> danger).
 * Thresholds are owned by the service layer (single source of truth) — frontend NEVER recomputes
 * thresholds, it only translates the enum to a severity string.
 *
 * <p>Boundaries (ratio = consumed / (effectiveBudget + carryOver), per D-13):
 *
 * <ul>
 *   <li>{@link #GREEN}: ratio &lt; 0.80
 *   <li>{@link #YELLOW}: 0.80 &le; ratio &le; 1.00
 *   <li>{@link #RED}: ratio &gt; 1.00
 * </ul>
 */
public enum EnvelopeStatus {
  GREEN,
  YELLOW,
  RED
}
