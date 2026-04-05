package com.prosperity.category;

import java.time.Instant;
import java.util.UUID;

/** DTO for category responses including parent information. */
public record CategoryResponse(
    UUID id,
    String name,
    UUID parentId,
    String parentName,
    boolean system,
    String plaidCategoryId,
    Instant createdAt) {}
