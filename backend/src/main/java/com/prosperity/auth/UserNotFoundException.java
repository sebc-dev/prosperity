package com.prosperity.auth;

/** Thrown when a user is not found by email or ID (404). */
public class UserNotFoundException extends RuntimeException {

  public UserNotFoundException(String message) {
    super(message);
  }
}
