package fr.kalifazzia.prosperity.category;

import fr.kalifazzia.prosperity.auth.JwtService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/categories")
public class CategoryController {

    private final CategoryService categoryService;
    private final JwtService jwtService;

    public CategoryController(CategoryService categoryService, JwtService jwtService) {
        this.categoryService = categoryService;
        this.jwtService = jwtService;
    }

    @GetMapping
    public ResponseEntity<List<CategoryDto>> getCategories(HttpServletRequest request) {
        UUID userId = extractUserId(request);
        List<Category> categories = categoryService.getCategories(userId);
        List<CategoryDto> dtos = categories.stream()
                .map(c -> new CategoryDto(c.getId(), c.getNameKey(), c.getIcon(), c.isDefault()))
                .toList();
        return ResponseEntity.ok(dtos);
    }

    @PostMapping
    public ResponseEntity<CategoryDto> createCategory(
            @RequestBody Map<String, String> body,
            HttpServletRequest request) {
        UUID userId = extractUserId(request);
        String nameKey = body.get("nameKey");
        String icon = body.get("icon");

        if (nameKey == null || nameKey.isBlank()) {
            throw new IllegalArgumentException("nameKey is required");
        }

        Category category = categoryService.createCategory(nameKey, icon, userId);
        CategoryDto dto = new CategoryDto(category.getId(), category.getNameKey(), category.getIcon(), category.isDefault());
        return ResponseEntity.status(HttpStatus.CREATED).body(dto);
    }

    private UUID extractUserId(HttpServletRequest request) {
        String authHeader = request.getHeader("Authorization");
        if (authHeader == null || !authHeader.startsWith("Bearer ")) {
            throw new IllegalStateException("Missing Authorization header");
        }
        String token = authHeader.substring(7);
        return jwtService.getUserIdFromToken(token);
    }

    record CategoryDto(UUID id, String nameKey, String icon, boolean isDefault) {
    }
}
