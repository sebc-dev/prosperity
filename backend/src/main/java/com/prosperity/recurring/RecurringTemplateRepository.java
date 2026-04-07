package com.prosperity.recurring;

import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

/** Spring Data JPA repository for RecurringTemplate entities. */
public interface RecurringTemplateRepository extends JpaRepository<RecurringTemplate, UUID> {

  List<RecurringTemplate> findByBankAccountIdAndActiveTrue(UUID bankAccountId);

  List<RecurringTemplate> findByBankAccountId(UUID bankAccountId);
}
