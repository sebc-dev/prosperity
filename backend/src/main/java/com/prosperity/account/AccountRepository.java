package com.prosperity.account;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

/** Spring Data JPA repository for Account entities. */
public interface AccountRepository extends JpaRepository<Account, UUID> {}
