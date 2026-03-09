package fr.kalifazzia.prosperity.shared.security;

import fr.kalifazzia.prosperity.auth.JwtService;
import jakarta.servlet.http.HttpServletRequest;

import java.util.UUID;

public final class SecurityUtils {

    private SecurityUtils() {
    }

    public static UUID extractUserId(HttpServletRequest request, JwtService jwtService) {
        String authHeader = request.getHeader("Authorization");
        if (authHeader == null || !authHeader.startsWith("Bearer ")) {
            throw new UnauthenticatedUserException("Missing Authorization header");
        }
        String token = authHeader.substring(7);
        return jwtService.getUserIdFromToken(token);
    }
}
