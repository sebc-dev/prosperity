package fr.kalifazzia.prosperity.auth.dto;

public record AuthResponse(
        String accessToken,
        String refreshToken
) {
}
