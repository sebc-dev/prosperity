package com.prosperity.transaction;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

/** Spring Data JPA repository for Transaction entities. */
public interface TransactionRepository extends JpaRepository<Transaction, UUID> {

  boolean existsByCategoryId(UUID categoryId);
}
