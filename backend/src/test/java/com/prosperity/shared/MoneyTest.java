package com.prosperity.shared;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class MoneyTest {

  @Test
  void ofString_createsMoney_withCorrectBigDecimal() {
    Money money = Money.of("10.50");

    assertThat(money.amount()).isEqualByComparingTo(new BigDecimal("10.50"));
    assertThat(money.amount().scale()).isEqualTo(4);
  }

  @Test
  void zero_createsZeroMoney() {
    Money money = Money.zero();

    assertThat(money.amount()).isEqualByComparingTo(BigDecimal.ZERO);
    assertThat(money.amount().scale()).isEqualTo(4);
  }

  @Test
  void constructor_rejectsNull() {
    assertThatThrownBy(() -> new Money(null)).isInstanceOf(NullPointerException.class);
  }

  @Test
  void constructor_rejectsScaleGreaterThanFour() {
    assertThatThrownBy(() -> new Money(new BigDecimal("10.12345")))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("4 decimal places");
  }

  @Test
  void constructor_acceptsScaleZero() {
    Money money = new Money(new BigDecimal("10"));

    assertThat(money.amount().scale()).isEqualTo(4);
    assertThat(money.amount()).isEqualByComparingTo(new BigDecimal("10.0000"));
  }

  @Test
  void constructor_acceptsScaleTwo() {
    Money money = new Money(new BigDecimal("10.50"));

    assertThat(money.amount().scale()).isEqualTo(4);
    assertThat(money.amount()).isEqualByComparingTo(new BigDecimal("10.50"));
  }

  @Test
  void constructor_acceptsScaleFour() {
    Money money = new Money(new BigDecimal("10.1234"));

    assertThat(money.amount().scale()).isEqualTo(4);
    assertThat(money.amount()).isEqualByComparingTo(new BigDecimal("10.1234"));
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
  void equality_sameAmount_areEqual() {
    Money a = Money.of("42.50");
    Money b = Money.of("42.50");

    assertThat(a).isEqualTo(b);
  }

  @Test
  void equality_differentScale_areEqual_afterNormalization() {
    Money a = new Money(new BigDecimal("5"));
    Money b = Money.of("5.00");

    assertThat(a).isEqualTo(b);
  }
}
