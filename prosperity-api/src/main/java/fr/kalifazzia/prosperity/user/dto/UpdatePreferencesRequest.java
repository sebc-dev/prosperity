package fr.kalifazzia.prosperity.user.dto;

import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.util.List;

public record UpdatePreferencesRequest(
        @Pattern(regexp = "^(light|dark|system)$", message = "Theme must be 'light', 'dark', or 'system'")
        String theme,
        @Pattern(regexp = "^[a-z]{2}$", message = "Locale must be a 2-letter language code")
        String locale,
        @Pattern(regexp = "^[A-Z]{3}$", message = "Currency must be a 3-letter ISO 4217 code")
        String defaultCurrency,
        List<@Size(max = 100) String> favoriteCategories
) {
}
