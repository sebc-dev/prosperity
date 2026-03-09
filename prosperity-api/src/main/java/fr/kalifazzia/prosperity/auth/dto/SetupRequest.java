package fr.kalifazzia.prosperity.auth.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public record SetupRequest(
        @NotBlank @Email String email,
        @NotBlank String displayName,
        @NotBlank String password
) {
}
