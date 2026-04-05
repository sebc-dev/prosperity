package com.prosperity.account;

import com.prosperity.shared.AccountType;
import com.prosperity.shared.Money;
import com.prosperity.shared.MoneyConverter;
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

/** JPA entity representing a bank account (personal or shared). */
@Entity
@Table(name = "bank_accounts")
public class Account {

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @Column(nullable = false, length = 100)
  private String name;

  @Enumerated(EnumType.STRING)
  @Column(name = "account_type", nullable = false, length = 20)
  private AccountType accountType;

  @Convert(converter = MoneyConverter.class)
  @Column(name = "balance", nullable = false, columnDefinition = "NUMERIC(19,4)")
  private Money balance;

  @Column(nullable = false, length = 3)
  private String currency = "EUR";

  @Column(name = "plaid_account_id", length = 255)
  private String plaidAccountId;

  @Column(name = "created_at", nullable = false, columnDefinition = "TIMESTAMPTZ")
  private Instant createdAt;

  @Column(name = "updated_at", nullable = false, columnDefinition = "TIMESTAMPTZ")
  private Instant updatedAt;

  @Column(nullable = false)
  private boolean archived = false;

  protected Account() {}

  public Account(String name, AccountType accountType) {
    this.name = name;
    this.accountType = accountType;
    this.balance = Money.zero();
    this.createdAt = Instant.now();
    this.updatedAt = Instant.now();
  }

  public UUID getId() {
    return id;
  }

  public void setId(UUID id) {
    this.id = id;
  }

  public String getName() {
    return name;
  }

  public void setName(String name) {
    this.name = name;
  }

  public AccountType getAccountType() {
    return accountType;
  }

  public void setAccountType(AccountType accountType) {
    this.accountType = accountType;
  }

  public Money getBalance() {
    return balance;
  }

  public void setBalance(Money balance) {
    this.balance = balance;
  }

  public String getCurrency() {
    return currency;
  }

  public void setCurrency(String currency) {
    this.currency = currency;
  }

  public String getPlaidAccountId() {
    return plaidAccountId;
  }

  public void setPlaidAccountId(String plaidAccountId) {
    this.plaidAccountId = plaidAccountId;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public void setCreatedAt(Instant createdAt) {
    this.createdAt = createdAt;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }

  public void setUpdatedAt(Instant updatedAt) {
    this.updatedAt = updatedAt;
  }

  public boolean isArchived() {
    return archived;
  }

  public void setArchived(boolean archived) {
    this.archived = archived;
  }
}
