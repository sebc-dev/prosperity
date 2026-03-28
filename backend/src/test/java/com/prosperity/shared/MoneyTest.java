package com.prosperity.shared;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class MoneyTest {

  @Test
  void ofString_createsMoney_withCorrectBigDecimal() {
    Money money = Money.of("10.50");

    assertThat(money.amount()).isEqualByComparingTo(new BigDecimal("10.50"));
    assertThat(money.amount().scale()).isEqualTo(2);
  }

  @Test
  void ofCents_createsMoney_withCorrectBigDecimal() {
    Money money = Money.ofCents(1050);

    assertThat(money.amount()).isEqualByComparingTo(new BigDecimal("10.50"));
    assertThat(money.amount().scale()).isEqualTo(2);
  }

  @Test
  void ofCents_zero_createsZeroMoney() {
    Money money = Money.ofCents(0);

    assertThat(money.amount()).isEqualByComparingTo(BigDecimal.ZERO);
  }

  @Test
  void ofCents_negative_createsNegativeMoney() {
    Money money = Money.ofCents(-500);

    assertThat(money.amount()).isEqualByComparingTo(new BigDecimal("-5.00"));
  }

  @Test
  void constructor_rejectsNull() {
    assertThatThrownBy(() -> new Money(null)).isInstanceOf(NullPointerException.class);
  }

  @Test
  void constructor_rejectsScaleGreaterThanTwo() {
    assertThatThrownBy(() -> new Money(new BigDecimal("10.123")))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("2 decimal places");
  }

  @Test
  void constructor_acceptsScaleZero() {
    Money money = new Money(new BigDecimal("10"));

    assertThat(money.amount().scale()).isEqualTo(2);
    assertThat(money.amount()).isEqualByComparingTo(new BigDecimal("10.00"));
  }

  @Test
  void constructor_acceptsScaleOne() {
    Money money = new Money(new BigDecimal("10.5"));

    assertThat(money.amount().scale()).isEqualTo(2);
    assertThat(money.amount()).isEqualByComparingTo(new BigDecimal("10.50"));
  }

  @Test
  void add_returnsSumOfTwoMoneyValues() {
    Money a = Money.of("10.50");
    Money b = Money.of("3.25");

    Money result = a.add(b);

    assertThat(result.amount()).isEqualByComparingTo(new BigDecimal("13.75"));
  }

  @Test
  void subtract_returnsDifferenceOfTwoMoneyValues() {
    Money a = Money.of("10.50");
    Money b = Money.of("3.25");

    Money result = a.subtract(b);

    assertThat(result.amount()).isEqualByComparingTo(new BigDecimal("7.25"));
  }

  @Test
  void toCents_returnsCorrectLongValue() {
    Money money = Money.of("10.50");

    assertThat(money.toCents()).isEqualTo(1050L);
  }

  @Test
  void toCents_negativeAmount_returnsNegativeCents() {
    Money money = Money.of("-5.25");

    assertThat(money.toCents()).isEqualTo(-525L);
  }

  @Test
  void toCents_zero_returnsZero() {
    Money money = Money.of("0.00");

    assertThat(money.toCents()).isEqualTo(0L);
  }

  @Test
  void noOfDoubleFactoryMethod_exists() throws Exception {
    assertThrows(
        NoSuchMethodException.class, () -> Money.class.getDeclaredMethod("of", double.class));
  }

  @Test
  void noOfDoubleFactoryMethod_primitive_exists() throws Exception {
    assertThrows(
        NoSuchMethodException.class, () -> Money.class.getDeclaredMethod("of", Double.class));
  }

  @Test
  void roundTrip_ofCentsAndToCents_areConsistent() {
    long cents = 9999L;

    Money money = Money.ofCents(cents);

    assertThat(money.toCents()).isEqualTo(cents);
  }
}
