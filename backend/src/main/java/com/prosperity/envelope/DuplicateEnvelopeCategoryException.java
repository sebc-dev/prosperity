package com.prosperity.envelope;

/**
 * Thrown when a category is already linked to another envelope on the same account (D-01). Mapped
 * to HTTP 409 Conflict by the controller.
 */
public class DuplicateEnvelopeCategoryException extends RuntimeException {

  public DuplicateEnvelopeCategoryException(String message) {
    super(message);
  }
}
