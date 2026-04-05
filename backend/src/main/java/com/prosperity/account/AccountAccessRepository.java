package com.prosperity.account;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

/** Spring Data JPA repository for AccountAccess entities. */
public interface AccountAccessRepository extends JpaRepository<AccountAccess, UUID> {

  /** Returns all access entries for a given account (used in access management). */
  List<AccountAccess> findByBankAccountId(UUID bankAccountId);

  /** Returns the access entry for a specific user on a given account, if it exists. */
  Optional<AccountAccess> findByBankAccountIdAndUserId(UUID bankAccountId, UUID userId);

  /**
   * Counts the number of access entries with the given access level on an account.
   * Used to prevent removing the last admin from an account.
   */
  long countByBankAccountIdAndAccessLevel(UUID bankAccountId, AccessLevel accessLevel);
}
