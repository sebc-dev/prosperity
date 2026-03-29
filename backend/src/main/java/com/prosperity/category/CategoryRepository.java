package com.prosperity.category;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

/** Spring Data JPA repository for Category entities. */
public interface CategoryRepository extends JpaRepository<Category, UUID> {}
