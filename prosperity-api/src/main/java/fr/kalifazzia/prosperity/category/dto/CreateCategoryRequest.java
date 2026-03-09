package fr.kalifazzia.prosperity.category.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateCategoryRequest(
        @NotBlank @Size(max = 100) String nameKey,
        @Size(max = 50) String icon
) {
}
