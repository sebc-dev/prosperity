package com.prosperity.account;

import com.prosperity.shared.AccountType;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/** DTO for creating a new bank account. */
public record CreateAccountRequest(
    @NotBlank @Size(max = 100) String name, @NotNull AccountType accountType) {}
