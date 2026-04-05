package com.prosperity.account;

/** Thrown when a bank account is not found (404). */
public class AccountNotFoundException extends RuntimeException {

  public AccountNotFoundException(String message) {
    super(message);
  }
}
