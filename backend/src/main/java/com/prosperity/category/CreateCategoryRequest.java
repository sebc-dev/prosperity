package com.prosperity.category;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.UUID;

/** DTO for creating a new category. parentId is nullable (null means root category). */
public record CreateCategoryRequest(
    @NotBlank @Size(max = 100) String name, UUID parentId) {}
