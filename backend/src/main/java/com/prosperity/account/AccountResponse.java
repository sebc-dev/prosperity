package com.prosperity.account;

import com.prosperity.shared.AccountType;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

/** DTO for account responses including the current user's access level. */
public record AccountResponse(
    UUID id,
    String name,
    AccountType accountType,
    BigDecimal balance,
    String currency,
    boolean archived,
    Instant createdAt,
    AccessLevel currentUserAccessLevel) {}
