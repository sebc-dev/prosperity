package com.prosperity.envelope;

import com.prosperity.account.Account;
import com.prosperity.auth.User;
import com.prosperity.shared.EnvelopeScope;
import com.prosperity.shared.Money;
import com.prosperity.shared.MoneyConverter;
import com.prosperity.shared.RolloverPolicy;
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
import java.util.UUID;

/** JPA entity representing a budget envelope linked to a bank account. */
@Entity
@Table(name = "envelopes")
public class Envelope {

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @ManyToOne(optional = false, fetch = FetchType.LAZY)
  @JoinColumn(name = "bank_account_id", nullable = false)
  private Account bankAccount;

  @Column(nullable = false, length = 100)
  private String name;

  @Enumerated(EnumType.STRING)
  @Column(name = "scope", length = 20)
  private EnvelopeScope scope;

  @ManyToOne(fetch = FetchType.LAZY)
  @JoinColumn(name = "owner_id")
  private User owner;

  @Convert(converter = MoneyConverter.class)
  @Column(name = "budget", nullable = false, columnDefinition = "NUMERIC(19,4)")
  private Money budget = Money.zero();

  @Enumerated(EnumType.STRING)
  @Column(name = "rollover_policy", length = 20, nullable = false)
  private RolloverPolicy rolloverPolicy = RolloverPolicy.RESET;

  @Column(name = "created_at", nullable = false, columnDefinition = "TIMESTAMPTZ")
  private Instant createdAt;

  protected Envelope() {}

  public Envelope(Account bankAccount, String name, EnvelopeScope scope, Money budget) {
    this.bankAccount = bankAccount;
    this.name = name;
    this.scope = scope;
    this.budget = budget;
    this.createdAt = Instant.now();
  }

  /** Returns true if the consumed amount exceeds this envelope's budget. */
  public boolean isOverspent(Money consumed) {
    return consumed.amount().compareTo(budget.amount()) > 0;
  }

  /** Returns the rollover amount based on this envelope's rollover policy. */
  public Money rollover(Money remaining) {
    return switch (rolloverPolicy) {
      case RESET -> Money.of("0.00");
      case CARRY_OVER -> remaining;
    };
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

  public String getName() {
    return name;
  }

  public void setName(String name) {
    this.name = name;
  }

  public EnvelopeScope getScope() {
    return scope;
  }

  public void setScope(EnvelopeScope scope) {
    this.scope = scope;
  }

  public User getOwner() {
    return owner;
  }

  public void setOwner(User owner) {
    this.owner = owner;
  }

  public Money getBudget() {
    return budget;
  }

  public void setBudget(Money budget) {
    this.budget = budget;
  }

  public RolloverPolicy getRolloverPolicy() {
    return rolloverPolicy;
  }

  public void setRolloverPolicy(RolloverPolicy rolloverPolicy) {
    this.rolloverPolicy = rolloverPolicy;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public void setCreatedAt(Instant createdAt) {
    this.createdAt = createdAt;
  }
}
