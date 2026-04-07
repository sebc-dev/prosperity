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
          SELECT t FROM Transaction t
          LEFT JOIN FETCH t.category
          WHERE t.bankAccount.id = :accountId
          AND (:dateFrom IS NULL OR t.transactionDate >= :dateFrom)
          AND (:dateTo IS NULL OR t.transactionDate <= :dateTo)
          AND (:amountMin IS NULL OR t.amount >= :amountMin)
          AND (:amountMax IS NULL OR t.amount <= :amountMax)
          AND (:categoryId IS NULL OR t.category.id = :categoryId)
          AND (:search IS NULL OR LOWER(t.description) LIKE LOWER(CONCAT('%', :search, '%')))
          """,
      countQuery =
          """
          SELECT COUNT(t) FROM Transaction t
          WHERE t.bankAccount.id = :accountId
          AND (:dateFrom IS NULL OR t.transactionDate >= :dateFrom)
          AND (:dateTo IS NULL OR t.transactionDate <= :dateTo)
          AND (:amountMin IS NULL OR t.amount >= :amountMin)
          AND (:amountMax IS NULL OR t.amount <= :amountMax)
          AND (:categoryId IS NULL OR t.category.id = :categoryId)
          AND (:search IS NULL OR LOWER(t.description) LIKE LOWER(CONCAT('%', :search, '%')))
          """)
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
