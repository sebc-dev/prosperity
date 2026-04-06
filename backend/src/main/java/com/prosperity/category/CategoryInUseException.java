package com.prosperity.category;

/** Thrown when attempting to delete a category that is used by transactions (409 Conflict). */
public class CategoryInUseException extends RuntimeException {

  public CategoryInUseException(String message) {
    super(message);
  }
}
