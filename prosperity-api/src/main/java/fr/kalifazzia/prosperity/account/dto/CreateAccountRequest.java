package fr.kalifazzia.prosperity.account.dto;

import fr.kalifazzia.prosperity.account.AccountType;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;

public record CreateAccountRequest(
        @NotBlank @Size(max = 255) String name,
        String bankName,
        @NotNull AccountType accountType,
        String currency,
        BigDecimal initialBalance,
        String color
) {
}
