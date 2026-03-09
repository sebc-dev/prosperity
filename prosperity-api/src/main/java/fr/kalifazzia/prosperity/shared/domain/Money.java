package fr.kalifazzia.prosperity.shared.domain;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

/**
 * Value object representing a monetary amount.
 * Uses BigDecimal with scale 4 and RoundingMode.HALF_EVEN (banker's rounding).
 */
public final class Money {

    public static final int SCALE = 4;
    public static final RoundingMode ROUNDING = RoundingMode.HALF_EVEN;
    public static final Money ZERO = new Money(BigDecimal.ZERO.setScale(SCALE, ROUNDING));

    private final BigDecimal value;

    private Money(BigDecimal value) {
        this.value = value;
    }

    public static Money of(BigDecimal amount) {
        Objects.requireNonNull(amount, "amount must not be null");
        return new Money(amount.setScale(SCALE, ROUNDING));
    }

    public static Money of(String amount) {
        Objects.requireNonNull(amount, "amount must not be null");
        return of(new BigDecimal(amount));
    }

    public static Money of(long amount) {
        return of(BigDecimal.valueOf(amount));
    }

    public Money add(Money other) {
        Objects.requireNonNull(other, "other must not be null");
        return new Money(this.value.add(other.value).setScale(SCALE, ROUNDING));
    }

    public Money subtract(Money other) {
        Objects.requireNonNull(other, "other must not be null");
        return new Money(this.value.subtract(other.value).setScale(SCALE, ROUNDING));
    }

    public Money negate() {
        return new Money(this.value.negate().setScale(SCALE, ROUNDING));
    }

    public boolean isPositive() {
        return this.value.compareTo(BigDecimal.ZERO) > 0;
    }

    public boolean isNegative() {
        return this.value.compareTo(BigDecimal.ZERO) < 0;
    }

    public boolean isZero() {
        return this.value.compareTo(BigDecimal.ZERO) == 0;
    }

    public BigDecimal getValue() {
        return value;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        Money money = (Money) o;
        return value.compareTo(money.value) == 0;
    }

    @Override
    public int hashCode() {
        return value.stripTrailingZeros().hashCode();
    }

    @Override
    public String toString() {
        return value.toPlainString();
    }
}
