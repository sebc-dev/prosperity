package com.prosperity.account;

import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/** Spring Data JPA repository for Account entities. All queries filter by user access. */
public interface AccountRepository extends JpaRepository<Account, UUID> {

  /**
   * Returns non-archived accounts accessible by the given user, along with their access level.
   * Each element of the returned list is an Object[] where [0] is Account and [1] is AccessLevel.
   */
  @Query(
      """
      SELECT a, aa.accessLevel FROM Account a
      JOIN AccountAccess aa ON aa.bankAccount = a
      WHERE aa.user.id = :userId
      AND a.archived = false
      ORDER BY a.name ASC
      """)
  List<Object[]> findAllAccessibleByUserId(@Param("userId") UUID userId);

  /**
   * Returns all accounts accessible by the given user (including archived), along with their
   * access level. Each element of the returned list is an Object[] where [0] is Account and [1]
   * is AccessLevel.
   */
  @Query(
      """
      SELECT a, aa.accessLevel FROM Account a
      JOIN AccountAccess aa ON aa.bankAccount = a
      WHERE aa.user.id = :userId
      ORDER BY a.name ASC
      """)
  List<Object[]> findAllAccessibleByUserIdIncludingArchived(@Param("userId") UUID userId);

  /**
   * Returns a single account with its access level for the given user, used for detail/update
   * operations. Returns empty if the user has no access to the account.
   */
  @Query(
      """
      SELECT a, aa.accessLevel FROM Account a
      JOIN AccountAccess aa ON aa.bankAccount = a
      WHERE a.id = :accountId
      AND aa.user.id = :userId
      """)
  Optional<Object[]> findByIdAndUserId(
      @Param("accountId") UUID accountId, @Param("userId") UUID userId);

  /**
   * Returns true if the user has access to the account at one of the given access levels.
   * Used for authorization checks before mutation operations.
   */
  @Query(
      """
      SELECT CASE WHEN COUNT(aa) > 0 THEN true ELSE false END
      FROM AccountAccess aa
      WHERE aa.bankAccount.id = :accountId
      AND aa.user.id = :userId
      AND aa.accessLevel IN :levels
      """)
  boolean hasAccess(
      @Param("accountId") UUID accountId,
      @Param("userId") UUID userId,
      @Param("levels") Collection<AccessLevel> levels);
}
