package com.prosperity.category;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Business logic for category CRUD operations.
 *
 * <p>Categories are global to the household (D-01) -- any authenticated user can manage custom
 * categories. System categories (seeded via Flyway) cannot be modified or deleted.
 */
@Service
public class CategoryService {

  private final CategoryRepository categoryRepository;
  private final CategoryUsageChecker categoryUsageChecker;

  public CategoryService(
      CategoryRepository categoryRepository, CategoryUsageChecker categoryUsageChecker) {
    this.categoryRepository = categoryRepository;
    this.categoryUsageChecker = categoryUsageChecker;
  }

  /**
   * Returns all categories with parent information, sorted by name.
   *
   * <p>Uses a JOIN FETCH query to avoid LazyInitializationException on parent access. Category
   * count is small (~30-60), so in-memory parent name resolution is efficient.
   */
  @Transactional(readOnly = true)
  public List<CategoryResponse> getAllCategories() {
    List<Category> categories = categoryRepository.findAllWithParentOrderByNameAsc();
    Map<UUID, String> nameById =
        categories.stream().collect(Collectors.toMap(Category::getId, Category::getName));

    return categories.stream()
        .map(c -> toResponse(c, c.getParent() != null ? nameById.get(c.getParent().getId()) : null))
        .toList();
  }

  /**
   * Creates a custom category with system=false.
   *
   * <p>Validates: parent exists and is a root category (max depth 2), no duplicate name at same
   * level.
   */
  @Transactional
  public CategoryResponse createCategory(CreateCategoryRequest request) {
    Category parent = null;

    if (request.parentId() != null) {
      parent =
          categoryRepository
              .findById(request.parentId())
              .orElseThrow(
                  () ->
                      new CategoryNotFoundException(
                          "Categorie parente introuvable : " + request.parentId()));

      if (parent.getParent() != null) {
        throw new IllegalArgumentException(
            "La categorie parente ne peut pas etre une sous-categorie");
      }
    }

    boolean duplicate =
        request.parentId() != null
            ? categoryRepository.existsByNameAndParentId(request.name(), request.parentId())
            : categoryRepository.existsByNameAndParentIsNull(request.name());

    if (duplicate) {
      throw new DuplicateCategoryNameException("Une categorie avec ce nom existe deja a ce niveau");
    }

    Category category = new Category(request.name());
    category.setParent(parent);
    category.setSystem(false);
    categoryRepository.save(category);

    return toResponse(category, parent != null ? parent.getName() : null);
  }

  /**
   * Renames a custom category. System categories cannot be modified.
   *
   * <p>Validates: category exists, not system, no duplicate name at same level.
   */
  @Transactional
  public CategoryResponse updateCategory(UUID id, UpdateCategoryRequest request) {
    Category category =
        categoryRepository
            .findById(id)
            .orElseThrow(() -> new CategoryNotFoundException("Categorie introuvable : " + id));

    if (category.isSystem()) {
      throw new IllegalArgumentException("Les categories systeme ne peuvent pas etre modifiees");
    }

    UUID parentId = category.getParent() != null ? category.getParent().getId() : null;
    boolean duplicate =
        parentId != null
            ? categoryRepository.existsByNameAndParentId(request.name(), parentId)
            : categoryRepository.existsByNameAndParentIsNull(request.name());

    if (duplicate && !category.getName().equals(request.name())) {
      throw new DuplicateCategoryNameException("Une categorie avec ce nom existe deja a ce niveau");
    }

    category.setName(request.name());
    categoryRepository.save(category);

    String parentName = category.getParent() != null ? category.getParent().getName() : null;
    return toResponse(category, parentName);
  }

  /**
   * Deletes a custom category.
   *
   * <p>Rejects: system categories, categories with children, categories used by transactions.
   */
  @Transactional
  public void deleteCategory(UUID id) {
    Category category =
        categoryRepository
            .findById(id)
            .orElseThrow(() -> new CategoryNotFoundException("Categorie introuvable : " + id));

    if (category.isSystem()) {
      throw new IllegalArgumentException("Les categories systeme ne peuvent pas etre supprimees");
    }

    if (categoryRepository.existsByParentId(id)) {
      throw new CategoryInUseException(
          "Impossible de supprimer une categorie qui contient des sous-categories");
    }

    if (categoryUsageChecker.isCategoryUsed(id)) {
      throw new CategoryInUseException(
          "Cette categorie est utilisee par des transactions et ne peut pas etre supprimee");
    }

    categoryRepository.delete(category);
  }

  private CategoryResponse toResponse(Category category, String parentName) {
    return new CategoryResponse(
        category.getId(),
        category.getName(),
        category.getParent() != null ? category.getParent().getId() : null,
        parentName,
        category.isSystem(),
        category.getPlaidCategoryId(),
        category.getCreatedAt());
  }
}
