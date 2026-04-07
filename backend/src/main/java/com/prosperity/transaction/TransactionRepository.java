package com.prosperity.transaction;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/** Spring Data JPA repository for Transaction entities. */
public interface TransactionRepository extends JpaRepository<Transaction, UUID> {

  boolean existsByCategoryId(UUID categoryId);

  @Query(
      value =
          """
          SELECT t.* FROM transactions t
          LEFT JOIN categories c ON c.id = t.category_id
          WHERE t.bank_account_id = CAST(:accountId AS uuid)
          AND (CAST(:dateFrom AS date) IS NULL OR t.transaction_date >= CAST(:dateFrom AS date))
          AND (CAST(:dateTo AS date) IS NULL OR t.transaction_date <= CAST(:dateTo AS date))
          AND (CAST(:amountMin AS numeric) IS NULL OR t.amount >= CAST(:amountMin AS numeric))
          AND (CAST(:amountMax AS numeric) IS NULL OR t.amount <= CAST(:amountMax AS numeric))
          AND (CAST(:categoryId AS uuid) IS NULL OR t.category_id = CAST(:categoryId AS uuid))
          AND (CAST(:search AS text) IS NULL OR LOWER(t.description) LIKE LOWER('%' || CAST(:search AS text) || '%'))
          """,
      countQuery =
          """
          SELECT COUNT(*) FROM transactions t
          WHERE t.bank_account_id = CAST(:accountId AS uuid)
          AND (CAST(:dateFrom AS date) IS NULL OR t.transaction_date >= CAST(:dateFrom AS date))
          AND (CAST(:dateTo AS date) IS NULL OR t.transaction_date <= CAST(:dateTo AS date))
          AND (CAST(:amountMin AS numeric) IS NULL OR t.amount >= CAST(:amountMin AS numeric))
          AND (CAST(:amountMax AS numeric) IS NULL OR t.amount <= CAST(:amountMax AS numeric))
          AND (CAST(:categoryId AS uuid) IS NULL OR t.category_id = CAST(:categoryId AS uuid))
          AND (CAST(:search AS text) IS NULL OR LOWER(t.description) LIKE LOWER('%' || CAST(:search AS text) || '%'))
          """,
      nativeQuery = true)
  Page<Transaction> findByFilters(
      @Param("accountId") UUID accountId,
      @Param("dateFrom") LocalDate dateFrom,
      @Param("dateTo") LocalDate dateTo,
      @Param("amountMin") BigDecimal amountMin,
      @Param("amountMax") BigDecimal amountMax,
      @Param("categoryId") UUID categoryId,
      @Param("search") String search,
      Pageable pageable);
}
