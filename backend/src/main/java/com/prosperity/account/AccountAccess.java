package com.prosperity.account;

import com.prosperity.auth.User;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.util.UUID;

/** JPA entity linking a user to a bank account with an access level. */
@Entity
@Table(
    name = "account_access",
    uniqueConstraints = @UniqueConstraint(columnNames = {"user_id", "bank_account_id"}))
public class AccountAccess {

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @ManyToOne
  @JoinColumn(name = "user_id", nullable = false)
  private User user;

  @ManyToOne
  @JoinColumn(name = "bank_account_id", nullable = false)
  private Account bankAccount;

  @Enumerated(EnumType.STRING)
  @Column(name = "access_level", nullable = false, length = 20)
  private AccessLevel accessLevel;

  protected AccountAccess() {}

  public AccountAccess(User user, Account bankAccount, AccessLevel accessLevel) {
    this.user = user;
    this.bankAccount = bankAccount;
    this.accessLevel = accessLevel;
  }

  public UUID getId() {
    return id;
  }

  public void setId(UUID id) {
    this.id = id;
  }

  public User getUser() {
    return user;
  }

  public void setUser(User user) {
    this.user = user;
  }

  public Account getBankAccount() {
    return bankAccount;
  }

  public void setBankAccount(Account bankAccount) {
    this.bankAccount = bankAccount;
  }

  public AccessLevel getAccessLevel() {
    return accessLevel;
  }

  public void setAccessLevel(AccessLevel accessLevel) {
    this.accessLevel = accessLevel;
  }
}
