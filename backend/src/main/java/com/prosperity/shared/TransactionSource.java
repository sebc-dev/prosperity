package com.prosperity.shared;

/** Source of a transaction: how it was created. */
public enum TransactionSource {
  MANUAL,
  PLAID,
  RECURRING
}
