package com.prosperity.envelope;

import static org.assertj.core.api.Assertions.assertThat;

import com.prosperity.shared.EnvelopeScope;
import com.prosperity.shared.Money;
import com.prosperity.shared.RolloverPolicy;
import org.junit.jupiter.api.Test;

class EnvelopeTest {

  @Test
  void isOverspent_returnsTrueWhenConsumedExceedsBudget() {
    Envelope envelope = createEnvelope(Money.of("100.00"));

    assertThat(envelope.isOverspent(Money.of("150.00"))).isTrue();
  }

  @Test
  void isOverspent_returnsFalseWhenConsumedEqualsBudget() {
    Envelope envelope = createEnvelope(Money.of("100.00"));

    assertThat(envelope.isOverspent(Money.of("100.00"))).isFalse();
  }

  @Test
  void isOverspent_returnsFalseWhenConsumedLessThanBudget() {
    Envelope envelope = createEnvelope(Money.of("100.00"));

    assertThat(envelope.isOverspent(Money.of("50.00"))).isFalse();
  }

  @Test
  void rollover_withResetPolicy_returnsZero() {
    Envelope envelope = createEnvelope(Money.of("100.00"));
    envelope.setRolloverPolicy(RolloverPolicy.RESET);

    Money result = envelope.rollover(Money.of("25.00"));

    assertThat(result.amount()).isEqualByComparingTo(Money.of("0.00").amount());
  }

  @Test
  void rollover_withCarryOverPolicy_returnsRemainingAmount() {
    Envelope envelope = createEnvelope(Money.of("100.00"));
    envelope.setRolloverPolicy(RolloverPolicy.CARRY_OVER);

    Money remaining = Money.of("25.00");
    Money result = envelope.rollover(remaining);

    assertThat(result.amount()).isEqualByComparingTo(remaining.amount());
  }

  @Test
  void rollover_withCarryOverPolicy_preservesExactAmount() {
    Envelope envelope = createEnvelope(Money.of("200.00"));
    envelope.setRolloverPolicy(RolloverPolicy.CARRY_OVER);

    Money remaining = Money.of("73.42");
    Money result = envelope.rollover(remaining);

    assertThat(result.toCents()).isEqualTo(7342L);
  }

  @Test
  void defaultRolloverPolicy_isReset() {
    Envelope envelope = createEnvelope(Money.of("100.00"));

    assertThat(envelope.getRolloverPolicy()).isEqualTo(RolloverPolicy.RESET);
  }

  private Envelope createEnvelope(Money budget) {
    return new Envelope(null, "Test Envelope", EnvelopeScope.PERSONAL, budget);
  }
}
