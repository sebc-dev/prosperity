package com.prosperity.account;

import com.prosperity.shared.AccountType;
import jakarta.validation.constraints.Size;

/** DTO for updating a bank account (partial update via PATCH). All fields nullable. */
public record UpdateAccountRequest(
    @Size(max = 100) String name, AccountType accountType, Boolean archived) {}
