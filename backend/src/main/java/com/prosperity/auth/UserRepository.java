package com.prosperity.auth;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

/** Spring Data JPA repository for User entities. */
public interface UserRepository extends JpaRepository<User, UUID> {}
