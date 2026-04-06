package com.prosperity.category;

/**
 * Thrown when attempting to create or rename a category with a name that already exists at the same
 * level (409 Conflict).
 */
public class DuplicateCategoryNameException extends RuntimeException {

  public DuplicateCategoryNameException(String message) {
    super(message);
  }
}
