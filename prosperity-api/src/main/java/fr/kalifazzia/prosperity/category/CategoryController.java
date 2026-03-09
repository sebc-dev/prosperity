package fr.kalifazzia.prosperity.category;

import fr.kalifazzia.prosperity.category.dto.CreateCategoryRequest;
import fr.kalifazzia.prosperity.shared.security.SecurityUtils;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/categories")
public class CategoryController {

    private final CategoryService categoryService;

    public CategoryController(CategoryService categoryService) {
        this.categoryService = categoryService;
    }

    @GetMapping
    public ResponseEntity<List<CategoryDto>> getCategories() {
        UUID userId = SecurityUtils.extractUserId();
        List<Category> categories = categoryService.getCategories(userId);
        List<CategoryDto> dtos = categories.stream()
                .map(c -> new CategoryDto(c.getId(), c.getNameKey(), c.getIcon(), c.isDefault()))
                .toList();
        return ResponseEntity.ok(dtos);
    }

    @PostMapping
    public ResponseEntity<CategoryDto> createCategory(
            @Valid @RequestBody CreateCategoryRequest body) {
        UUID userId = SecurityUtils.extractUserId();

        Category category = categoryService.createCategory(body.nameKey(), body.icon(), userId);
        CategoryDto dto = new CategoryDto(category.getId(), category.getNameKey(), category.getIcon(), category.isDefault());
        return ResponseEntity.status(HttpStatus.CREATED).body(dto);
    }

    record CategoryDto(UUID id, String nameKey, String icon, boolean isDefault) {
    }
}
