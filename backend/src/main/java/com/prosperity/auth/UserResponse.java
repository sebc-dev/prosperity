package com.prosperity.auth;

import java.util.UUID;

/** Safe user response DTO (excludes password hash). */
public record UserResponse(UUID id, String displayName, String email, String role) {}
