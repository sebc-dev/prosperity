package com.prosperity.account;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.prosperity.auth.User;
import com.prosperity.auth.UserRepository;
import com.prosperity.shared.AccountType;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/** Unit tests for AccountService business logic with mocked dependencies. */
@ExtendWith(MockitoExtension.class)
class AccountServiceTest {

  @Mock private AccountRepository accountRepository;
  @Mock private AccountAccessRepository accountAccessRepository;
  @Mock private UserRepository userRepository;
  @InjectMocks private AccountService accountService;

  // ---------------------------------------------------------------------------
  // Account CRUD (ACCT-01 to ACCT-05)
  // ---------------------------------------------------------------------------

  @Test
  void create_account_saves_account_and_returns_response() {
    User creator = createTestUser("user@test.com");
    when(userRepository.findByEmail("user@test.com")).thenReturn(Optional.of(creator));
    when(accountRepository.save(any(Account.class)))
        .thenAnswer(
            invocation -> {
              Account a = invocation.getArgument(0);
              a.setId(UUID.randomUUID());
              return a;
            });
    when(accountAccessRepository.save(any(AccountAccess.class)))
        .thenAnswer(invocation -> invocation.getArgument(0));

    var result =
        accountService.createAccount(
            new CreateAccountRequest("Compte Courant", AccountType.PERSONAL), "user@test.com");

    assertThat(result.name()).isEqualTo("Compte Courant");
    assertThat(result.accountType()).isEqualTo(AccountType.PERSONAL);
    assertThat(result.archived()).isFalse();
  }

  @Test
  void create_account_grants_admin_access_to_creator() {
    User creator = createTestUser("user@test.com");
    when(userRepository.findByEmail("user@test.com")).thenReturn(Optional.of(creator));
    when(accountRepository.save(any(Account.class)))
        .thenAnswer(
            invocation -> {
              Account a = invocation.getArgument(0);
              a.setId(UUID.randomUUID());
              return a;
            });
    when(accountAccessRepository.save(any(AccountAccess.class)))
        .thenAnswer(invocation -> invocation.getArgument(0));

    accountService.createAccount(
        new CreateAccountRequest("Mon Compte", AccountType.PERSONAL), "user@test.com");

    var accessCaptor = ArgumentCaptor.forClass(AccountAccess.class);
    verify(accountAccessRepository).save(accessCaptor.capture());
    assertThat(accessCaptor.getValue().getAccessLevel()).isEqualTo(AccessLevel.ADMIN);
  }

  @Test
  void get_accounts_returns_only_accessible_non_archived() {
    User user = createTestUser("user@test.com");
    Account account = createTestAccount("Compte A", AccountType.PERSONAL);
    List<AccountWithAccess> rows = List.of(new AccountWithAccess(account, AccessLevel.ADMIN));
    when(userRepository.findByEmail("user@test.com")).thenReturn(Optional.of(user));
    when(accountRepository.findAllAccessibleByUserId(user.getId())).thenReturn(rows);

    var result = accountService.getAccounts(false, "user@test.com");

    assertThat(result).hasSize(1);
    assertThat(result.get(0).name()).isEqualTo("Compte A");
    assertThat(result.get(0).currentUserAccessLevel()).isEqualTo(AccessLevel.ADMIN);
  }

  @Test
  void get_accounts_includes_archived_when_requested() {
    User user = createTestUser("user@test.com");
    Account archived = createTestAccount("Ancien Compte", AccountType.PERSONAL);
    archived.setArchived(true);
    List<AccountWithAccess> rows = List.of(new AccountWithAccess(archived, AccessLevel.WRITE));
    when(userRepository.findByEmail("user@test.com")).thenReturn(Optional.of(user));
    when(accountRepository.findAllAccessibleByUserIdIncludingArchived(user.getId()))
        .thenReturn(rows);

    var result = accountService.getAccounts(true, "user@test.com");

    assertThat(result).hasSize(1);
    assertThat(result.get(0).archived()).isTrue();
  }

  @Test
  void get_account_throws_access_denied_when_no_access() {
    User user = createTestUser("user@test.com");
    UUID accountId = UUID.randomUUID();
    when(userRepository.findByEmail("user@test.com")).thenReturn(Optional.of(user));
    when(accountRepository.findByIdAndUserId(accountId, user.getId())).thenReturn(List.of());
    when(accountRepository.existsById(accountId)).thenReturn(true);

    assertThatThrownBy(() -> accountService.getAccount(accountId, "user@test.com"))
        .isInstanceOf(AccountAccessDeniedException.class);
  }

  @Test
  void get_account_throws_not_found_when_account_missing() {
    User user = createTestUser("user@test.com");
    UUID accountId = UUID.randomUUID();
    when(userRepository.findByEmail("user@test.com")).thenReturn(Optional.of(user));
    when(accountRepository.findByIdAndUserId(accountId, user.getId())).thenReturn(List.of());
    when(accountRepository.existsById(accountId)).thenReturn(false);

    assertThatThrownBy(() -> accountService.getAccount(accountId, "user@test.com"))
        .isInstanceOf(AccountNotFoundException.class);
  }

  @Test
  void update_account_applies_partial_fields() {
    User user = createTestUser("user@test.com");
    UUID accountId = UUID.randomUUID();
    Account account = createTestAccount("Old Name", AccountType.PERSONAL);
    account.setId(accountId);
    when(userRepository.findByEmail("user@test.com")).thenReturn(Optional.of(user));
    when(accountRepository.findByIdAndUserId(accountId, user.getId()))
        .thenReturn(accessRows(account, AccessLevel.WRITE));
    when(accountRepository.save(any(Account.class)))
        .thenAnswer(invocation -> invocation.getArgument(0));

    var result =
        accountService.updateAccount(
            accountId, new UpdateAccountRequest("New Name", null, null), "user@test.com");

    assertThat(result.name()).isEqualTo("New Name");
    assertThat(result.accountType()).isEqualTo(AccountType.PERSONAL);
  }

  @Test
  void update_account_preserves_type_when_not_included_in_patch() {
    User user = createTestUser("user@test.com");
    UUID accountId = UUID.randomUUID();
    Account account = createTestAccount("Old Name", AccountType.SHARED);
    account.setId(accountId);
    when(userRepository.findByEmail("user@test.com")).thenReturn(Optional.of(user));
    when(accountRepository.findByIdAndUserId(accountId, user.getId()))
        .thenReturn(accessRows(account, AccessLevel.WRITE));
    when(accountRepository.save(any(Account.class)))
        .thenAnswer(invocation -> invocation.getArgument(0));

    var result =
        accountService.updateAccount(
            accountId, new UpdateAccountRequest("New Name", null, null), "user@test.com");

    assertThat(result.accountType()).isEqualTo(AccountType.SHARED);
  }

  @Test
  void update_account_throws_not_found_when_account_missing() {
    User user = createTestUser("user@test.com");
    UUID accountId = UUID.randomUUID();
    when(userRepository.findByEmail("user@test.com")).thenReturn(Optional.of(user));
    when(accountRepository.findByIdAndUserId(accountId, user.getId())).thenReturn(List.of());
    when(accountRepository.existsById(accountId)).thenReturn(false);

    assertThatThrownBy(
            () ->
                accountService.updateAccount(
                    accountId, new UpdateAccountRequest("X", null, null), "user@test.com"))
        .isInstanceOf(AccountNotFoundException.class);
  }

  @Test
  void update_account_rejects_read_only_user() {
    User user = createTestUser("user@test.com");
    UUID accountId = UUID.randomUUID();
    Account account = createTestAccount("Compte", AccountType.PERSONAL);
    account.setId(accountId);
    when(userRepository.findByEmail("user@test.com")).thenReturn(Optional.of(user));
    when(accountRepository.findByIdAndUserId(accountId, user.getId()))
        .thenReturn(accessRows(account, AccessLevel.READ));

    assertThatThrownBy(
            () ->
                accountService.updateAccount(
                    accountId, new UpdateAccountRequest("X", null, null), "user@test.com"))
        .isInstanceOf(AccountAccessDeniedException.class);
  }

  // ---------------------------------------------------------------------------
  // Access Management (ACCS-01 to ACCS-04)
  // ---------------------------------------------------------------------------

  @Test
  void get_access_entries_requires_admin_level() {
    User user = createTestUser("user@test.com");
    UUID accountId = UUID.randomUUID();
    when(userRepository.findByEmail("user@test.com")).thenReturn(Optional.of(user));
    when(accountRepository.hasAccess(accountId, user.getId(), List.of(AccessLevel.ADMIN)))
        .thenReturn(false);

    assertThatThrownBy(() -> accountService.getAccessEntries(accountId, "user@test.com"))
        .isInstanceOf(AccountAccessDeniedException.class);
  }

  @Test
  void set_access_creates_new_entry_when_not_exists() {
    User admin = createTestUser("admin@test.com");
    User targetUser = createTestUser("target@test.com");
    UUID accountId = UUID.randomUUID();
    Account account = createTestAccount("Compte", AccountType.PERSONAL);
    account.setId(accountId);
    when(userRepository.findByEmail("admin@test.com")).thenReturn(Optional.of(admin));
    when(accountRepository.hasAccess(accountId, admin.getId(), List.of(AccessLevel.ADMIN)))
        .thenReturn(true);
    when(userRepository.findById(targetUser.getId())).thenReturn(Optional.of(targetUser));
    when(accountAccessRepository.findByBankAccountIdAndUserId(accountId, targetUser.getId()))
        .thenReturn(Optional.empty());
    when(accountRepository.findById(accountId)).thenReturn(Optional.of(account));
    when(accountAccessRepository.save(any(AccountAccess.class)))
        .thenAnswer(
            invocation -> {
              AccountAccess aa = invocation.getArgument(0);
              aa.setId(UUID.randomUUID());
              return aa;
            });

    var result =
        accountService.setAccess(
            accountId,
            new SetAccessRequest(targetUser.getId(), AccessLevel.READ),
            "admin@test.com");

    verify(accountAccessRepository).save(any(AccountAccess.class));
    assertThat(result.accessLevel()).isEqualTo(AccessLevel.READ);
  }

  @Test
  void set_access_updates_existing_entry() {
    User admin = createTestUser("admin@test.com");
    User targetUser = createTestUser("target@test.com");
    UUID accountId = UUID.randomUUID();
    Account account = createTestAccount("Compte", AccountType.PERSONAL);
    account.setId(accountId);
    AccountAccess existing = new AccountAccess(targetUser, account, AccessLevel.READ);
    existing.setId(UUID.randomUUID());
    when(userRepository.findByEmail("admin@test.com")).thenReturn(Optional.of(admin));
    when(accountRepository.hasAccess(accountId, admin.getId(), List.of(AccessLevel.ADMIN)))
        .thenReturn(true);
    when(userRepository.findById(targetUser.getId())).thenReturn(Optional.of(targetUser));
    when(accountAccessRepository.findByBankAccountIdAndUserId(accountId, targetUser.getId()))
        .thenReturn(Optional.of(existing));
    when(accountAccessRepository.save(any(AccountAccess.class)))
        .thenAnswer(invocation -> invocation.getArgument(0));

    var result =
        accountService.setAccess(
            accountId,
            new SetAccessRequest(targetUser.getId(), AccessLevel.WRITE),
            "admin@test.com");

    assertThat(result.accessLevel()).isEqualTo(AccessLevel.WRITE);
  }

  @Test
  void set_access_prevents_demoting_last_admin() {
    User admin = createTestUser("admin@test.com");
    UUID accountId = UUID.randomUUID();
    Account account = createTestAccount("Compte", AccountType.PERSONAL);
    account.setId(accountId);
    AccountAccess existing = new AccountAccess(admin, account, AccessLevel.ADMIN);
    existing.setId(UUID.randomUUID());
    when(userRepository.findByEmail("admin@test.com")).thenReturn(Optional.of(admin));
    when(accountRepository.hasAccess(accountId, admin.getId(), List.of(AccessLevel.ADMIN)))
        .thenReturn(true);
    when(userRepository.findById(admin.getId())).thenReturn(Optional.of(admin));
    when(accountAccessRepository.findByBankAccountIdAndUserId(accountId, admin.getId()))
        .thenReturn(Optional.of(existing));
    when(accountAccessRepository.countByBankAccountIdAndAccessLevel(accountId, AccessLevel.ADMIN))
        .thenReturn(1L);

    assertThatThrownBy(
            () ->
                accountService.setAccess(
                    accountId,
                    new SetAccessRequest(admin.getId(), AccessLevel.READ),
                    "admin@test.com"))
        .isInstanceOf(IllegalStateException.class);
  }

  @Test
  void remove_access_deletes_entry() {
    User admin = createTestUser("admin@test.com");
    User targetUser = createTestUser("target@test.com");
    UUID accountId = UUID.randomUUID();
    Account account = createTestAccount("Compte", AccountType.PERSONAL);
    account.setId(accountId);
    AccountAccess entry = new AccountAccess(targetUser, account, AccessLevel.READ);
    UUID accessId = UUID.randomUUID();
    entry.setId(accessId);
    when(userRepository.findByEmail("admin@test.com")).thenReturn(Optional.of(admin));
    when(accountRepository.hasAccess(accountId, admin.getId(), List.of(AccessLevel.ADMIN)))
        .thenReturn(true);
    when(accountAccessRepository.findById(accessId)).thenReturn(Optional.of(entry));

    accountService.removeAccess(accountId, accessId, "admin@test.com");

    verify(accountAccessRepository).delete(entry);
  }

  @Test
  void remove_access_prevents_removing_last_admin() {
    User admin = createTestUser("admin@test.com");
    UUID accountId = UUID.randomUUID();
    Account account = createTestAccount("Compte", AccountType.PERSONAL);
    account.setId(accountId);
    AccountAccess entry = new AccountAccess(admin, account, AccessLevel.ADMIN);
    UUID accessId = UUID.randomUUID();
    entry.setId(accessId);
    when(userRepository.findByEmail("admin@test.com")).thenReturn(Optional.of(admin));
    when(accountRepository.hasAccess(accountId, admin.getId(), List.of(AccessLevel.ADMIN)))
        .thenReturn(true);
    when(accountAccessRepository.findById(accessId)).thenReturn(Optional.of(entry));
    when(accountAccessRepository.countByBankAccountIdAndAccessLevel(accountId, AccessLevel.ADMIN))
        .thenReturn(1L);

    assertThatThrownBy(() -> accountService.removeAccess(accountId, accessId, "admin@test.com"))
        .isInstanceOf(IllegalStateException.class);
  }

  @Test
  void remove_access_throws_when_access_belongs_to_different_account() {
    User admin = createTestUser("admin@test.com");
    User targetUser = createTestUser("target@test.com");
    UUID accountIdA = UUID.randomUUID();
    Account accountB = createTestAccount("Compte B", AccountType.PERSONAL);
    UUID accessId = UUID.randomUUID();
    AccountAccess entry = new AccountAccess(targetUser, accountB, AccessLevel.READ);
    entry.setId(accessId);
    when(userRepository.findByEmail("admin@test.com")).thenReturn(Optional.of(admin));
    when(accountRepository.hasAccess(accountIdA, admin.getId(), List.of(AccessLevel.ADMIN)))
        .thenReturn(true);
    when(accountAccessRepository.findById(accessId)).thenReturn(Optional.of(entry));

    assertThatThrownBy(() -> accountService.removeAccess(accountIdA, accessId, "admin@test.com"))
        .isInstanceOf(IllegalArgumentException.class);
  }

  // ---------------------------------------------------------------------------
  // Test helpers
  // ---------------------------------------------------------------------------

  private User createTestUser(String email) {
    User user = new User(email, "{bcrypt}hash", email.split("@")[0]);
    user.setId(UUID.randomUUID());
    return user;
  }

  private Account createTestAccount(String name, AccountType type) {
    Account account = new Account(name, type);
    account.setId(UUID.randomUUID());
    return account;
  }

  private List<AccountWithAccess> accessRows(Account account, AccessLevel level) {
    return List.of(new AccountWithAccess(account, level));
  }
}
