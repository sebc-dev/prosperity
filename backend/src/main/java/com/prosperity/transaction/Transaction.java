package com.prosperity.transaction;

import com.prosperity.account.Account;
import com.prosperity.auth.User;
import com.prosperity.category.Category;
import com.prosperity.shared.Money;
import com.prosperity.shared.MoneyConverter;
import com.prosperity.shared.TransactionSource;
import com.prosperity.shared.TransactionState;
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

/** JPA entity representing a financial transaction linked to a bank account. */
@Entity
@Table(name = "transactions")
public class Transaction {

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @ManyToOne(optional = false, fetch = FetchType.LAZY)
  @JoinColumn(name = "bank_account_id", nullable = false)
  private Account bankAccount;

  @Convert(converter = MoneyConverter.class)
  @Column(name = "amount_cents", nullable = false)
  private Money amount;

  @Column(length = 500)
  private String description;

  @ManyToOne(fetch = FetchType.LAZY)
  @JoinColumn(name = "category_id")
  private Category category;

  @Column(name = "transaction_date", nullable = false)
  private LocalDate transactionDate;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 20)
  private TransactionSource source;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 30)
  private TransactionState state = TransactionState.MANUAL_UNMATCHED;

  @Column(name = "plaid_transaction_id", length = 255)
  private String plaidTransactionId;

  @Column(nullable = false)
  private boolean pointed = false;

  @ManyToOne(fetch = FetchType.LAZY)
  @JoinColumn(name = "created_by")
  private User createdBy;

  @Column(name = "created_at", nullable = false, columnDefinition = "TIMESTAMPTZ")
  private Instant createdAt;

  protected Transaction() {}

  public Transaction(
      Account bankAccount, Money amount, LocalDate transactionDate, TransactionSource source) {
    this.bankAccount = bankAccount;
    this.amount = amount;
    this.transactionDate = transactionDate;
    this.source = source;
    this.createdAt = Instant.now();
  }

  public UUID getId() {
    return id;
  }

  public void setId(UUID id) {
    this.id = id;
  }

  public Account getBankAccount() {
    return bankAccount;
  }

  public void setBankAccount(Account bankAccount) {
    this.bankAccount = bankAccount;
  }

  public Money getAmount() {
    return amount;
  }

  public void setAmount(Money amount) {
    this.amount = amount;
  }

  public String getDescription() {
    return description;
  }

  public void setDescription(String description) {
    this.description = description;
  }

  public Category getCategory() {
    return category;
  }

  public void setCategory(Category category) {
    this.category = category;
  }

  public LocalDate getTransactionDate() {
    return transactionDate;
  }

  public void setTransactionDate(LocalDate transactionDate) {
    this.transactionDate = transactionDate;
  }

  public TransactionSource getSource() {
    return source;
  }

  public void setSource(TransactionSource source) {
    this.source = source;
  }

  public TransactionState getState() {
    return state;
  }

  public void setState(TransactionState state) {
    this.state = state;
  }

  public String getPlaidTransactionId() {
    return plaidTransactionId;
  }

  public void setPlaidTransactionId(String plaidTransactionId) {
    this.plaidTransactionId = plaidTransactionId;
  }

  public boolean isPointed() {
    return pointed;
  }

  public void setPointed(boolean pointed) {
    this.pointed = pointed;
  }

  public User getCreatedBy() {
    return createdBy;
  }

  public void setCreatedBy(User createdBy) {
    this.createdBy = createdBy;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public void setCreatedAt(Instant createdAt) {
    this.createdAt = createdAt;
  }
}
