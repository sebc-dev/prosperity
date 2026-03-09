package fr.kalifazzia.prosperity.user.dto;

import java.util.UUID;

public record UserDto(
        UUID id,
        String email,
        String displayName,
        String systemRole,
        Object preferences,
        boolean forcePasswordChange
) {
}
