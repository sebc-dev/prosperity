package fr.kalifazzia.prosperity.account.dto;

import fr.kalifazzia.prosperity.account.AccountType;
import fr.kalifazzia.prosperity.account.PermissionLevel;

import java.math.BigDecimal;
import java.util.UUID;

public record AccountDto(
        UUID id,
        String name,
        String bankName,
        AccountType accountType,
        String currency,
        BigDecimal initialBalance,
        BigDecimal currentBalance,
        String color,
        PermissionLevel permissionLevel
) {
}
