package fr.kalifazzia.prosperity.user.dto;

import java.util.List;

public record UpdatePreferencesRequest(
        String theme,
        String locale,
        String defaultCurrency,
        List<String> favoriteCategories
) {
}
