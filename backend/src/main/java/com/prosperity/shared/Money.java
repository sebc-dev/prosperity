package com.prosperity.shared;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

/** Immutable value object representing a monetary amount with precision up to 4 decimal places. */
public record Money(BigDecimal amount) {

  public static final int MAX_SCALE = 4;

  public Money {
    Objects.requireNonNull(amount, "amount must not be null");
    if (amount.scale() > MAX_SCALE) {
      throw new IllegalArgumentException(
          "Money precision cannot exceed " + MAX_SCALE + " decimal places");
    }
    amount = amount.setScale(MAX_SCALE, RoundingMode.HALF_UP);
  }

  public static Money of(String value) {
    return new Money(new BigDecimal(value));
  }

  public static Money zero() {
    return new Money(BigDecimal.ZERO);
  }

  public Money add(Money other) {
    return new Money(this.amount.add(other.amount));
  }

  public Money subtract(Money other) {
    return new Money(this.amount.subtract(other.amount));
  }
}
