package fr.kalifazzia.prosperity.user.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public record CreateUserRequest(
        @Email @NotBlank String email,
        @NotBlank String displayName,
        @NotBlank String password
) {
}
