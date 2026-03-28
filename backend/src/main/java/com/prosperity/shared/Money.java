package com.prosperity.shared;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

/** Immutable value object representing a monetary amount with precision 2. */
public record Money(BigDecimal amount) {

  public Money {
    Objects.requireNonNull(amount, "amount must not be null");
    if (amount.scale() > 2) {
      throw new IllegalArgumentException("Money precision cannot exceed 2 decimal places");
    }
    amount = amount.setScale(2, RoundingMode.HALF_UP);
  }

  public static Money of(String value) {
    return new Money(new BigDecimal(value));
  }

  public static Money ofCents(long cents) {
    return new Money(BigDecimal.valueOf(cents, 2));
  }

  public Money add(Money other) {
    return new Money(this.amount.add(other.amount));
  }

  public Money subtract(Money other) {
    return new Money(this.amount.subtract(other.amount));
  }

  public long toCents() {
    return amount.movePointRight(2).longValueExact();
  }
}
