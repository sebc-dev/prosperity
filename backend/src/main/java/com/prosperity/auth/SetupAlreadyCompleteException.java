package com.prosperity.auth;

/** Thrown when setup wizard is invoked but an admin user already exists. */
public class SetupAlreadyCompleteException extends RuntimeException {

  public SetupAlreadyCompleteException() {
    super("Setup already complete: admin user exists");
  }
}
