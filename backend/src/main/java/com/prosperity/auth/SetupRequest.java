package com.prosperity.auth;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/** DTO for the initial setup wizard request (admin account creation). */
public record SetupRequest(
    @NotBlank @Email String email,
    @NotBlank
        @Size(min = 12, max = 128)
        @Pattern(
            regexp = "^(?=.*[A-Z])(?=.*\\d)(?=.*[^a-zA-Z0-9]).+$",
            message =
                "Must contain at least 1 uppercase letter, 1 digit, and 1 special character")
        String password,
    @NotBlank @Size(min = 2, max = 100) String displayName) {}
