package fr.kalifazzia.prosperity.account;

import fr.kalifazzia.prosperity.shared.persistence.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.util.UUID;

@Entity
@Table(name = "accounts")
public class Account extends BaseEntity {

    @Column(name = "name", nullable = false)
    private String name;

    @Column(name = "bank_name")
    private String bankName;

    @Enumerated(EnumType.STRING)
    @Column(name = "account_type", nullable = false)
    private AccountType accountType;

    @Column(name = "owner_id", nullable = false)
    private UUID ownerId;

    @Column(name = "currency", length = 3)
    private String currency = "EUR";

    @Column(name = "initial_balance", precision = 19, scale = 4)
    private BigDecimal initialBalance = BigDecimal.ZERO;

    @Column(name = "current_balance", precision = 19, scale = 4)
    private BigDecimal currentBalance = BigDecimal.ZERO;

    @Column(name = "color", length = 7)
    private String color;

    protected Account() {
    }

    public Account(UUID id, String name, String bankName, AccountType accountType,
                   UUID ownerId, String currency, BigDecimal initialBalance, String color) {
        super(id);
        this.name = name;
        this.bankName = bankName;
        this.accountType = accountType;
        this.ownerId = ownerId;
        this.currency = currency != null ? currency : "EUR";
        this.initialBalance = initialBalance != null ? initialBalance : BigDecimal.ZERO;
        this.currentBalance = this.initialBalance;
        this.color = color;
    }

    public String getName() {
        return name;
    }

    public String getBankName() {
        return bankName;
    }

    public AccountType getAccountType() {
        return accountType;
    }

    public UUID getOwnerId() {
        return ownerId;
    }

    public String getCurrency() {
        return currency;
    }

    public BigDecimal getInitialBalance() {
        return initialBalance;
    }

    public BigDecimal getCurrentBalance() {
        return currentBalance;
    }

    public void setCurrentBalance(BigDecimal currentBalance) {
        this.currentBalance = currentBalance;
    }

    public String getColor() {
        return color;
    }
}
