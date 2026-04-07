package com.prosperity.recurring;

import com.prosperity.account.Account;
import com.prosperity.auth.User;
import com.prosperity.category.Category;
import com.prosperity.shared.Money;
import com.prosperity.shared.MoneyConverter;
import com.prosperity.shared.RecurrenceFrequency;
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

/** JPA entity representing a recurring transaction template. */
@Entity
@Table(name = "recurring_templates")
public class RecurringTemplate {

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @ManyToOne(optional = false, fetch = FetchType.LAZY)
  @JoinColumn(name = "account_id", nullable = false)
  private Account bankAccount;

  @Convert(converter = MoneyConverter.class)
  @Column(name = "amount", nullable = false, columnDefinition = "NUMERIC(19,4)")
  private Money amount;

  @Column(length = 500)
  private String description;

  @ManyToOne(fetch = FetchType.LAZY)
  @JoinColumn(name = "category_id")
  private Category category;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 20)
  private RecurrenceFrequency frequency;

  @Column(name = "day_of_month")
  private Integer dayOfMonth;

  @Column(name = "next_due_date", nullable = false)
  private LocalDate nextDueDate;

  @Column(nullable = false)
  private boolean active = true;

  @ManyToOne(fetch = FetchType.LAZY)
  @JoinColumn(name = "created_by")
  private User createdBy;

  @Column(name = "created_at", nullable = false, columnDefinition = "TIMESTAMPTZ")
  private Instant createdAt;

  protected RecurringTemplate() {}

  public RecurringTemplate(
      Account bankAccount, Money amount, RecurrenceFrequency frequency, LocalDate nextDueDate) {
    this.bankAccount = bankAccount;
    this.amount = amount;
    this.frequency = frequency;
    this.nextDueDate = nextDueDate;
    this.active = true;
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

  public RecurrenceFrequency getFrequency() {
    return frequency;
  }

  public void setFrequency(RecurrenceFrequency frequency) {
    this.frequency = frequency;
  }

  public Integer getDayOfMonth() {
    return dayOfMonth;
  }

  public void setDayOfMonth(Integer dayOfMonth) {
    this.dayOfMonth = dayOfMonth;
  }

  public LocalDate getNextDueDate() {
    return nextDueDate;
  }

  public void setNextDueDate(LocalDate nextDueDate) {
    this.nextDueDate = nextDueDate;
  }

  public boolean isActive() {
    return active;
  }

  public void setActive(boolean active) {
    this.active = active;
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
