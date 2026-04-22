package com.prosperity.envelope;

/** Thrown when an envelope allocation (monthly override) id is not found. Mapped to HTTP 404. */
public class EnvelopeAllocationNotFoundException extends RuntimeException {

  public EnvelopeAllocationNotFoundException(String message) {
    super(message);
  }
}
