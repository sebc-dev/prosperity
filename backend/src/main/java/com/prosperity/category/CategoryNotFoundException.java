package com.prosperity.category;

/** Thrown when a category is not found (404). */
public class CategoryNotFoundException extends RuntimeException {

  public CategoryNotFoundException(String message) {
    super(message);
  }
}
