package com.prosperity.transaction;

/** Thrown when a transaction is not found (404). */
public class TransactionNotFoundException extends RuntimeException {

  public TransactionNotFoundException(String message) {
    super(message);
  }
}
