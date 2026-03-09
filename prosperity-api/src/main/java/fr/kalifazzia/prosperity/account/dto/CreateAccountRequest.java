package fr.kalifazzia.prosperity.account.dto;

import fr.kalifazzia.prosperity.account.AccountType;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;
import java.util.UUID;

public record CreateAccountRequest(
        @NotBlank @Size(max = 255) String name,
        @Size(max = 255) String bankName,
        @NotNull AccountType accountType,
        @Size(max = 3) @Pattern(regexp = "^[A-Z]{3}$") String currency,
        BigDecimal initialBalance,
        @Size(max = 7) @Pattern(regexp = "^#[0-9a-fA-F]{6}$") String color,
        UUID sharedWithUserId
) {
}
