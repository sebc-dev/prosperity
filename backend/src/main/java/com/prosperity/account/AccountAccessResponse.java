package com.prosperity.account;

import java.util.UUID;

/** DTO for account access entries (who has access to an account and at what level). */
public record AccountAccessResponse(
    UUID id, UUID userId, String userEmail, String userDisplayName, AccessLevel accessLevel) {}
