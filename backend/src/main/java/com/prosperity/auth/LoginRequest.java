package com.prosperity.auth;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

/** DTO for login requests. */
public record LoginRequest(@NotBlank @Email String email, @NotBlank String password) {}
