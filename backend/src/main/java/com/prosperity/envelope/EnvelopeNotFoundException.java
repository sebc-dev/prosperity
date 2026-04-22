package com.prosperity.envelope;

/** Thrown when an envelope id is not found. Mapped to HTTP 404 by the controller. */
public class EnvelopeNotFoundException extends RuntimeException {

  public EnvelopeNotFoundException(String message) {
    super(message);
  }
}
