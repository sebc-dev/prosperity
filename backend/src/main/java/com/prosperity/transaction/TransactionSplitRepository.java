package com.prosperity.transaction;

import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

/** Spring Data JPA repository for TransactionSplit entities. */
public interface TransactionSplitRepository extends JpaRepository<TransactionSplit, UUID> {

  List<TransactionSplit> findByTransactionId(UUID transactionId);

  void deleteByTransactionId(UUID transactionId);
}
