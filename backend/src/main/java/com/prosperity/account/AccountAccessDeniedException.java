package com.prosperity.account;

/** Thrown when the current user lacks the required access level on an account (403). */
public class AccountAccessDeniedException extends RuntimeException {

  public AccountAccessDeniedException(String message) {
    super(message);
  }
}
