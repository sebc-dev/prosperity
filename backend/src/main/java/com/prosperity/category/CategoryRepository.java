package com.prosperity.category;

import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

/** Spring Data JPA repository for Category entities. */
public interface CategoryRepository extends JpaRepository<Category, UUID> {

  List<Category> findByParentIsNullOrderByNameAsc();

  List<Category> findAllByOrderByNameAsc();

  boolean existsByNameAndParentId(String name, UUID parentId);

  boolean existsByNameAndParentIsNull(String name);
}
