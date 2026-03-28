package com.prosperity.shared;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

/** JPA AttributeConverter that stores Money as BIGINT cents in the database. */
@Converter(autoApply = false)
public class MoneyConverter implements AttributeConverter<Money, Long> {

  @Override
  public Long convertToDatabaseColumn(Money money) {
    return money == null ? null : money.toCents();
  }

  @Override
  public Money convertToEntityAttribute(Long cents) {
    return cents == null ? null : Money.ofCents(cents);
  }
}
