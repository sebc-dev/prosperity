package com.prosperity.category;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/** DTO for renaming a category. Only name is updatable. */
public record UpdateCategoryRequest(@NotBlank @Size(max = 100) String name) {}
