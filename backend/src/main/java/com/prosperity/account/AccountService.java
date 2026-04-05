package com.prosperity.account;

import com.prosperity.auth.User;
import com.prosperity.auth.UserRepository;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Business logic for account CRUD and access management.
 *
 * <p>All methods receive {@code userEmail} from the controller layer — this service never touches
 * {@code SecurityContextHolder} directly (pitfall 6 from phase research).
 */
@Service
public class AccountService {

  private final AccountRepository accountRepository;
  private final AccountAccessRepository accountAccessRepository;
  private final UserRepository userRepository;

  public AccountService(
      AccountRepository accountRepository,
      AccountAccessRepository accountAccessRepository,
      UserRepository userRepository) {
    this.accountRepository = accountRepository;
    this.accountAccessRepository = accountAccessRepository;
    this.userRepository = userRepository;
  }

  // ---------------------------------------------------------------------------
  // Account CRUD
  // ---------------------------------------------------------------------------

  /**
   * Creates a new account and automatically assigns ADMIN access to the creator (D-04).
   * Shared accounts do not receive automatic access for other users (D-05).
   */
  @Transactional
  public AccountResponse createAccount(CreateAccountRequest request, String userEmail) {
    User creator = resolveUser(userEmail);
    Account account = new Account(request.name(), request.accountType());
    accountRepository.save(account);

    AccountAccess access = new AccountAccess(creator, account, AccessLevel.ADMIN);
    accountAccessRepository.save(access);

    return toResponse(account, AccessLevel.ADMIN);
  }

  /**
   * Returns accounts accessible by the given user.
   * D-07: archived accounts excluded by default, included when {@code includeArchived} is true.
   */
  @Transactional(readOnly = true)
  public List<AccountResponse> getAccounts(boolean includeArchived, String userEmail) {
    User user = resolveUser(userEmail);
    List<Object[]> results =
        includeArchived
            ? accountRepository.findAllAccessibleByUserIdIncludingArchived(user.getId())
            : accountRepository.findAllAccessibleByUserId(user.getId());

    return results.stream()
        .map(row -> toResponse((Account) row[0], (AccessLevel) row[1]))
        .toList();
  }

  /**
   * Returns a single account for the given user.
   * D-02: throws 403 when account exists but user has no access (avoids leaking existence).
   */
  @Transactional(readOnly = true)
  public AccountResponse getAccount(UUID accountId, String userEmail) {
    User user = resolveUser(userEmail);
    List<Object[]> results = accountRepository.findByIdAndUserId(accountId, user.getId());
    if (results.isEmpty()) {
      if (accountRepository.existsById(accountId)) {
        throw new AccountAccessDeniedException("Access denied to account: " + accountId);
      }
      throw new AccountNotFoundException("Account not found: " + accountId);
    }
    Object[] row = results.get(0);
    return toResponse((Account) row[0], (AccessLevel) row[1]);
  }

  /**
   * Updates an account's mutable fields (partial PATCH semantics — D-08, all fields nullable).
   * Requires at least WRITE access.
   */
  @Transactional
  public AccountResponse updateAccount(
      UUID accountId, UpdateAccountRequest request, String userEmail) {
    User user = resolveUser(userEmail);
    List<Object[]> results = accountRepository.findByIdAndUserId(accountId, user.getId());
    if (results.isEmpty()) {
      if (accountRepository.existsById(accountId)) {
        throw new AccountAccessDeniedException("Access denied to account: " + accountId);
      }
      throw new AccountNotFoundException("Account not found: " + accountId);
    }
    Object[] row = results.get(0);

    AccessLevel accessLevel = (AccessLevel) row[1];
    if (!accessLevel.isAtLeast(AccessLevel.WRITE)) {
      throw new AccountAccessDeniedException(
          "Write access required to update account: " + accountId);
    }

    Account account = (Account) row[0];
    if (request.name() != null) {
      account.setName(request.name());
    }
    if (request.accountType() != null) {
      account.setAccountType(request.accountType());
    }
    if (request.archived() != null) {
      account.setArchived(request.archived());
    }
    account.setUpdatedAt(Instant.now());
    accountRepository.save(account);

    return toResponse(account, accessLevel);
  }

  // ---------------------------------------------------------------------------
  // Access management (ADMIN-only)
  // ---------------------------------------------------------------------------

  /**
   * Returns all access entries for an account. Requires ADMIN access.
   */
  @Transactional(readOnly = true)
  public List<AccountAccessResponse> getAccessEntries(UUID accountId, String userEmail) {
    User user = resolveUser(userEmail);
    if (!accountRepository.hasAccess(accountId, user.getId(), List.of(AccessLevel.ADMIN))) {
      throw new AccountAccessDeniedException(
          "Admin access required to list access entries for account: " + accountId);
    }
    return accountAccessRepository.findByBankAccountId(accountId).stream()
        .map(this::toAccessResponse)
        .toList();
  }

  /**
   * Grants or updates access for a user on an account. Requires ADMIN access.
   * Creates a new entry if none exists; updates the access level otherwise.
   */
  @Transactional
  public AccountAccessResponse setAccess(
      UUID accountId, SetAccessRequest request, String userEmail) {
    User currentUser = resolveUser(userEmail);
    if (!accountRepository.hasAccess(accountId, currentUser.getId(), List.of(AccessLevel.ADMIN))) {
      throw new AccountAccessDeniedException(
          "Admin access required to set access for account: " + accountId);
    }

    User targetUser =
        userRepository
            .findById(request.userId())
            .orElseThrow(
                () -> new RuntimeException("Target user not found: " + request.userId()));

    AccountAccess access =
        accountAccessRepository
            .findByBankAccountIdAndUserId(accountId, request.userId())
            .orElseGet(
                () -> {
                  Account account =
                      accountRepository
                          .findById(accountId)
                          .orElseThrow(
                              () ->
                                  new AccountNotFoundException(
                                      "Account not found: " + accountId));
                  return new AccountAccess(targetUser, account, request.accessLevel());
                });

    access.setAccessLevel(request.accessLevel());
    accountAccessRepository.save(access);

    return toAccessResponse(access);
  }

  /**
   * Removes an access entry from an account. Requires ADMIN access.
   * Prevents removing the last ADMIN to avoid orphaning the account.
   */
  @Transactional
  public void removeAccess(UUID accountId, UUID accessId, String userEmail) {
    User currentUser = resolveUser(userEmail);
    if (!accountRepository.hasAccess(accountId, currentUser.getId(), List.of(AccessLevel.ADMIN))) {
      throw new AccountAccessDeniedException(
          "Admin access required to remove access for account: " + accountId);
    }

    AccountAccess entry =
        accountAccessRepository
            .findById(accessId)
            .orElseThrow(
                () -> new RuntimeException("Access entry not found: " + accessId));

    if (!entry.getBankAccount().getId().equals(accountId)) {
      throw new IllegalArgumentException(
          "Access entry " + accessId + " does not belong to account " + accountId);
    }

    if (entry.getAccessLevel() == AccessLevel.ADMIN) {
      long adminCount =
          accountAccessRepository.countByBankAccountIdAndAccessLevel(
              accountId, AccessLevel.ADMIN);
      if (adminCount <= 1) {
        throw new IllegalStateException("Cannot remove the last admin from an account");
      }
    }

    accountAccessRepository.delete(entry);
  }

  // ---------------------------------------------------------------------------
  // Private helpers
  // ---------------------------------------------------------------------------

  private User resolveUser(String userEmail) {
    return userRepository
        .findByEmail(userEmail)
        .orElseThrow(() -> new RuntimeException("User not found: " + userEmail));
  }

  private AccountResponse toResponse(Account account, AccessLevel accessLevel) {
    return new AccountResponse(
        account.getId(),
        account.getName(),
        account.getAccountType(),
        account.getBalance().amount(),
        account.getCurrency(),
        account.isArchived(),
        account.getCreatedAt(),
        accessLevel);
  }

  private AccountAccessResponse toAccessResponse(AccountAccess access) {
    return new AccountAccessResponse(
        access.getId(),
        access.getUser().getId(),
        access.getUser().getEmail(),
        access.getUser().getDisplayName(),
        access.getAccessLevel());
  }
}
