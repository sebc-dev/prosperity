package com.prosperity.recurring;

/** Thrown when a recurring template is not found (404). */
public class RecurringTemplateNotFoundException extends RuntimeException {

  public RecurringTemplateNotFoundException(String message) {
    super(message);
  }
}
