package com.prosperity.account;

import jakarta.validation.constraints.NotNull;
import java.util.UUID;

/** DTO for granting or updating a user's access level on an account. */
public record SetAccessRequest(@NotNull UUID userId, @NotNull AccessLevel accessLevel) {}
