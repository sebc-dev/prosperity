package com.prosperity.account;

/** Thrown when an account access entry is not found (404). */
public class AccessEntryNotFoundException extends RuntimeException {

  public AccessEntryNotFoundException(String message) {
    super(message);
  }
}
