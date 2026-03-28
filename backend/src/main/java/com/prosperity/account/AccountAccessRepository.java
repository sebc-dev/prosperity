package com.prosperity.account;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

/** Spring Data JPA repository for AccountAccess entities. */
public interface AccountAccessRepository extends JpaRepository<AccountAccess, UUID> {}
