package com.prosperity.shared;

/** State of a transaction in the reconciliation workflow. */
public enum TransactionState {
  MANUAL_UNMATCHED,
  IMPORTED_UNMATCHED,
  MATCHED
}
