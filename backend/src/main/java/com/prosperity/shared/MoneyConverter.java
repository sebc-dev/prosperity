package com.prosperity.shared;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;
import java.math.BigDecimal;

/** JPA AttributeConverter that maps Money to NUMERIC(19,4) via BigDecimal. */
@Converter(autoApply = false)
public class MoneyConverter implements AttributeConverter<Money, BigDecimal> {

  @Override
  public BigDecimal convertToDatabaseColumn(Money money) {
    return money == null ? null : money.amount();
  }

  @Override
  public Money convertToEntityAttribute(BigDecimal value) {
    return value == null ? null : new Money(value);
  }
}
