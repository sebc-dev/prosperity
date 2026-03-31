package com.prosperity.auth;

/** Safe user response DTO (excludes password hash). */
public record UserResponse(String displayName, String email, String role) {}
